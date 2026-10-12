from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from hourly_pay.application.calculate_hourly import calculate_hourly_limit
from hourly_pay.domain.errors import InvalidCalculationError
from hourly_pay.domain.models import (
    AcademicYear,
    HourlyCalculation,
    ImportWarning,
    Teacher,
    WorkloadItem,
)
from hourly_pay.domain.normalization import summarize_workload
from hourly_pay.domain.rules import AUDITORY_WORK_TYPES
from hourly_pay.importers.base import ImportResult
from hourly_pay.importers.nagr_xlsx_v1 import PARSER_VERSION
from hourly_pay.persistence.repositories import TeacherSourceSummary


class CalculationRepository(Protocol):
    def list_teachers(self) -> tuple[Teacher, ...]: ...

    def list_teacher_sources(self, teacher_id: int) -> tuple[TeacherSourceSummary, ...]: ...

    def get_import(self, source_id: int) -> ImportResult | None: ...


@dataclass(frozen=True, slots=True)
class CalculationWarning:
    source_name: str
    sheet_name: str | None
    row_number: int | None
    message: str
    row_items: tuple[WorkloadItem, ...]


@dataclass(frozen=True, slots=True)
class TeacherCalculation:
    teacher: Teacher
    academic_year: AcademicYear
    values: HourlyCalculation
    included_source_count: int
    warnings: tuple[CalculationWarning, ...]
    eligible_items: tuple[WorkloadItem, ...]


class TeacherCalculationService:
    def __init__(self, repository: CalculationRepository) -> None:
        self._repository = repository

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._repository.list_teachers()

    def list_years(self, teacher_id: int) -> tuple[AcademicYear, ...]:
        years = {
            entry.academic_year.id: entry.academic_year
            for entry in self._repository.list_teacher_sources(teacher_id)
        }
        return tuple(sorted(years.values(), key=lambda year: year.name))

    def calculate(self, teacher_id: int, academic_year_id: int) -> TeacherCalculation:
        teacher = next(
            (item for item in self._repository.list_teachers() if item.id == teacher_id),
            None,
        )
        if teacher is None:
            raise InvalidCalculationError("Преподаватель не найден.")
        if teacher.effective_rate is None:
            raise InvalidCalculationError(
                "Подтвердите эффективную ставку в карточке преподавателя."
            )

        year_sources = tuple(
            entry
            for entry in self._repository.list_teacher_sources(teacher_id)
            if entry.academic_year.id == academic_year_id
        )
        if not year_sources:
            raise InvalidCalculationError("Для выбранного учебного года нет источников нагрузки.")
        unresolved = [
            entry.source.original_filename
            for entry in year_sources
            if entry.source.include_in_fact is None
        ]
        if unresolved:
            raise InvalidCalculationError(
                "Для каждого источника выберите «Учитывать» или «Не учитывать»: "
                + ", ".join(unresolved)
            )

        included = tuple(entry for entry in year_sources if entry.source.include_in_fact is True)
        outdated = [
            entry.source.original_filename
            for entry in included
            if entry.source.parser_version != PARSER_VERSION
        ]
        if outdated:
            raise InvalidCalculationError(
                "Эти источники прочитаны старой версией и могут давать неверные часы: "
                + ", ".join(outdated)
                + ". Импортируйте исходные XLSX заново, затем исключите старые источники."
            )
        imported = tuple(self._load_import(entry) for entry in included)
        items = (item for result in imported for item in result.items)
        breakdown = summarize_workload(items)
        values = calculate_hourly_limit(
            effective_rate=teacher.effective_rate,
            fact_hours=breakdown.total_hours,
            idpo_hours=breakdown.idpo_hours,
            eligible_hours=breakdown.eligible_auditory_hours,
        )
        warnings = tuple(
            _calculation_warning(result, warning)
            for result in imported
            for warning in result.warnings
        )
        return TeacherCalculation(
            teacher=teacher,
            academic_year=year_sources[0].academic_year,
            values=values,
            included_source_count=len(included),
            warnings=warnings,
            eligible_items=tuple(
                item
                for result in imported
                for item in result.items
                if item.work_type in AUDITORY_WORK_TYPES and not item.is_idpo
            ),
        )

    def _load_import(self, entry: TeacherSourceSummary) -> ImportResult:
        source_id = entry.source.id
        result = self._repository.get_import(source_id) if source_id is not None else None
        if result is None:
            raise InvalidCalculationError(
                f"Не удалось прочитать импортированный источник: {entry.source.original_filename}."
            )
        return result


def _calculation_warning(result: ImportResult, warning: ImportWarning) -> CalculationWarning:
    row_items = _matching_items(
        result.items,
        sheet_name=warning.sheet_name,
        row_number=warning.source_row_number,
    )
    return CalculationWarning(
        source_name=result.source.original_filename,
        sheet_name=warning.sheet_name,
        row_number=warning.source_row_number,
        message=warning.message,
        row_items=row_items,
    )


def _matching_items(
    items: Sequence[WorkloadItem], *, sheet_name: str | None, row_number: int | None
) -> tuple[WorkloadItem, ...]:
    if sheet_name is None or row_number is None:
        return ()
    return tuple(
        item
        for item in items
        if item.source_row_number == row_number and item.raw_context.get("sheet") == sheet_name
    )
