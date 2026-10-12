from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from hourly_pay.application.allocate_months import allocate_selection_months
from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.domain.allocation import MonthlyAllocationPlan
from hourly_pay.domain.errors import InvalidMonthlyAllocationError
from hourly_pay.domain.models import (
    AcademicYear,
    HourlySelection,
    MonthlyAllocation,
    Teacher,
    WorkloadItem,
)


class PlanningSelectionRepository(Protocol):
    def list_for_teacher_year(
        self, teacher_id: int, academic_year_id: int
    ) -> tuple[HourlySelection, ...]: ...


class PlanningAllocationRepository(Protocol):
    def list_for_selection(self, selection_id: int) -> tuple[MonthlyAllocation, ...]: ...

    def replace_plans(
        self, plans: tuple[tuple[int, tuple[MonthlyAllocation, ...]], ...]
    ) -> None: ...

    def clear_for_selections(self, selection_ids: tuple[int, ...]) -> None: ...


@dataclass(frozen=True, slots=True)
class MonthlyPlanningRow:
    selection: HourlySelection
    item: WorkloadItem
    allocations: tuple[MonthlyAllocation, ...]


@dataclass(frozen=True, slots=True)
class MonthlyPlanningSnapshot:
    academic_year: AcademicYear
    rows: tuple[MonthlyPlanningRow, ...]
    stored_allocation_count: int


@dataclass(frozen=True, slots=True)
class MonthlyRowDraft:
    hours_by_month: Mapping[int, Decimal]
    include_january: bool = False
    semester_override: int | None = None


class MonthlyPlanningService:
    def __init__(
        self,
        calculations: TeacherCalculationService,
        selections: PlanningSelectionRepository,
        allocations: PlanningAllocationRepository,
    ) -> None:
        self._calculations = calculations
        self._selections = selections
        self._allocations = allocations

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._calculations.list_teachers()

    def list_years(self, teacher_id: int) -> tuple[AcademicYear, ...]:
        return self._calculations.list_years(teacher_id)

    def load(self, teacher_id: int, academic_year_id: int) -> MonthlyPlanningSnapshot:
        calculation = self._calculations.calculate(teacher_id, academic_year_id)
        items = {item.id: item for item in calculation.eligible_items}
        selections = self._selections.list_for_teacher_year(teacher_id, academic_year_id)
        stored = {
            selection.id: self._allocations.list_for_selection(selection.id)
            for selection in selections
            if selection.id is not None
        }
        rows = tuple(
            MonthlyPlanningRow(
                selection=selection,
                item=items[selection.workload_item_id],
                allocations=stored.get(selection.id, ()),
            )
            for selection in selections
            if selection.workload_item_id in items
        )
        return MonthlyPlanningSnapshot(
            academic_year=calculation.academic_year,
            rows=rows,
            stored_allocation_count=sum(len(entries) for entries in stored.values()),
        )

    def clear(self, teacher_id: int, academic_year_id: int) -> None:
        selection_ids = tuple(
            selection.id
            for selection in self._selections.list_for_teacher_year(teacher_id, academic_year_id)
            if selection.id is not None
        )
        self._allocations.clear_for_selections(selection_ids)

    def save(
        self,
        teacher_id: int,
        academic_year_id: int,
        drafts: Mapping[int, MonthlyRowDraft],
    ) -> tuple[MonthlyAllocationPlan, ...]:
        snapshot = self.load(teacher_id, academic_year_id)
        rows = {
            row.selection.id: row
            for row in snapshot.rows
            if row.selection.id is not None
        }
        if set(drafts) != set(rows):
            raise InvalidMonthlyAllocationError(
                "План изменился. Обновите таблицу и сохраните все выбранные строки."
            )
        plans = tuple(
            allocate_selection_months(
                selection=row.selection,
                item=row.item,
                academic_year=snapshot.academic_year,
                monthly_hours=drafts[selection_id].hours_by_month,
                include_january=drafts[selection_id].include_january,
                semester_override=drafts[selection_id].semester_override,
            )
            for selection_id, row in rows.items()
        )
        self._allocations.replace_plans(
            tuple(
                (selection_id, plan.allocations)
                for selection_id, plan in zip(rows, plans, strict=True)
            )
        )
        return plans
