from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hourly_pay.domain.enums import WarningCode, WarningSeverity
from hourly_pay.domain.errors import DomainError, DuplicateImportError
from hourly_pay.domain.models import ImportWarning
from hourly_pay.importers.base import ImportResult
from hourly_pay.importers.nagr_xlsx_v1 import PARSER_VERSION, NagrXlsxV1Importer
from hourly_pay.persistence.repositories import SavedImport


class WorkloadImportRepository(Protocol):
    def known_hashes(self) -> set[str]: ...

    def parser_versions_by_hash(self) -> dict[str, set[str]]: ...

    def save_import(
        self, result: ImportResult, *, allow_duplicate: bool = False
    ) -> SavedImport: ...


@dataclass(frozen=True, slots=True)
class WorkloadImportPreview:
    path: Path
    result: ImportResult

    @property
    def is_duplicate(self) -> bool:
        return any(warning.code is WarningCode.DUPLICATE_IMPORT for warning in self.result.warnings)

    @property
    def is_upgrade(self) -> bool:
        return any(warning.code is WarningCode.PARSER_UPGRADE for warning in self.result.warnings)


@dataclass(frozen=True, slots=True)
class WorkloadImportFailure:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class WorkloadPreviewBatch:
    previews: tuple[WorkloadImportPreview, ...]
    failures: tuple[WorkloadImportFailure, ...]


class ImportWorkloadService:
    def __init__(self, repository: WorkloadImportRepository) -> None:
        self._repository = repository

    def preview_files(self, paths: Sequence[Path]) -> WorkloadPreviewBatch:
        known_versions = self._repository.parser_versions_by_hash()
        known_hashes = set(known_versions)
        previews: list[WorkloadImportPreview] = []
        failures: list[WorkloadImportFailure] = []
        for path in paths:
            source_path = Path(path)
            try:
                result = preview_workload(source_path, known_hashes=known_hashes)
            except (DomainError, OSError) as error:
                failures.append(WorkloadImportFailure(source_path, str(error)))
                continue
            file_hash = result.source.file_sha256
            if file_hash in known_hashes and PARSER_VERSION not in known_versions.get(
                file_hash, set()
            ):
                result.warnings = [
                    warning
                    for warning in result.warnings
                    if warning.code is not WarningCode.DUPLICATE_IMPORT
                ]
                result.warnings.append(
                    ImportWarning(
                        code=WarningCode.PARSER_UPGRADE,
                        severity=WarningSeverity.INFO,
                        message=(
                            "Этот файл был прочитан старой версией. Можно импортировать "
                            "его заново; затем исключите прежний источник из расчёта."
                        ),
                    )
                )
            previews.append(WorkloadImportPreview(source_path, result))
            known_hashes.add(file_hash)
            known_versions.setdefault(file_hash, set()).add(PARSER_VERSION)
        return WorkloadPreviewBatch(tuple(previews), tuple(failures))

    def confirm_imports(
        self, previews: Sequence[WorkloadImportPreview]
    ) -> tuple[SavedImport, ...]:
        duplicate = next((preview for preview in previews if preview.is_duplicate), None)
        if duplicate is not None:
            raise DuplicateImportError(duplicate.result.source.file_sha256)
        return tuple(
            self._repository.save_import(
                preview.result, allow_duplicate=preview.is_upgrade
            )
            for preview in previews
        )


def preview_workload(
    path: Path,
    *,
    known_hashes: Collection[str] = (),
) -> ImportResult:
    return NagrXlsxV1Importer().import_file(path, known_hashes=frozenset(known_hashes))
