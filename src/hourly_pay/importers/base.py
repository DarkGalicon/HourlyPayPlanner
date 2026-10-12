from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from hourly_pay.domain.models import (
    AcademicYear,
    ImportWarning,
    Teacher,
    WorkloadItem,
    WorkloadSource,
)
from hourly_pay.domain.rules import counts_toward_plan


@dataclass(slots=True)
class ImportTotals:
    full_time: Decimal | None = None
    correspondence: Decimal | None = None
    overall: Decimal | None = None


@dataclass(slots=True)
class ImportResult:
    teacher: Teacher
    academic_year: AcademicYear
    source: WorkloadSource
    items: list[WorkloadItem]
    warnings: list[ImportWarning]
    summary_totals: ImportTotals

    @property
    def normalized_hours(self) -> Decimal:
        return sum(
            (item.hours for item in self.items if counts_toward_plan(item)),
            start=Decimal("0"),
        )

    @property
    def idpo_hours(self) -> Decimal:
        return sum(
            (
                item.hours
                for item in self.items
                if item.is_idpo and counts_toward_plan(item)
            ),
            start=Decimal("0"),
        )


class WorkloadImporter(Protocol):
    def import_file(
        self, path: Path, *, known_hashes: set[str] | frozenset[str] = frozenset()
    ) -> ImportResult: ...
