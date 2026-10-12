from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from hourly_pay.application.calculate_teacher import TeacherCalculation, TeacherCalculationService
from hourly_pay.application.select_hourly import select_hourly_workload
from hourly_pay.domain.models import AcademicYear, HourlySelection, Teacher
from hourly_pay.domain.selection import SelectionPlan


class SelectionRepository(Protocol):
    def list_for_teacher_year(
        self, teacher_id: int, academic_year_id: int
    ) -> tuple[HourlySelection, ...]: ...

    def replace_for_teacher_year(
        self, teacher_id: int, academic_year_id: int, selections: tuple[HourlySelection, ...],
        allow_limit_excess: bool = False,
    ) -> None: ...

    def get_allow_limit_excess(self, teacher_id: int, academic_year_id: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class SelectionSnapshot:
    calculation: TeacherCalculation
    saved_hours: dict[int, Decimal]
    evening_item_ids: frozenset[int]
    excluded_saved_count: int
    allow_limit_excess: bool


class SelectionService:
    def __init__(
        self, calculation_service: TeacherCalculationService, repository: SelectionRepository
    ) -> None:
        self._calculation_service = calculation_service
        self._repository = repository

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._calculation_service.list_teachers()

    def list_years(self, teacher_id: int) -> tuple[AcademicYear, ...]:
        return self._calculation_service.list_years(teacher_id)

    def load(self, teacher_id: int, academic_year_id: int) -> SelectionSnapshot:
        calculation = self._calculation_service.calculate(teacher_id, academic_year_id)
        available_ids = {item.id for item in calculation.eligible_items}
        saved = self._repository.list_for_teacher_year(teacher_id, academic_year_id)
        return SelectionSnapshot(
            calculation=calculation,
            saved_hours={
                selection.workload_item_id: selection.selected_hours
                for selection in saved
                if selection.workload_item_id in available_ids
            },
            evening_item_ids=frozenset(
                selection.workload_item_id for selection in saved
                if selection.prefer_evening and selection.workload_item_id in available_ids
            ),
            excluded_saved_count=sum(
                selection.workload_item_id not in available_ids for selection in saved
            ),
            allow_limit_excess=self._repository.get_allow_limit_excess(
                teacher_id, academic_year_id
            ),
        )

    def save(
        self, teacher_id: int, academic_year_id: int, requested_hours: Mapping[int, Decimal],
        evening_item_ids: frozenset[int] = frozenset(),
        allow_limit_excess: bool = False,
    ) -> SelectionPlan:
        calculation = self._calculation_service.calculate(teacher_id, academic_year_id)
        plan = select_hourly_workload(
            items=calculation.eligible_items,
            requested_hours=requested_hours,
            hourly_limit=calculation.values.hourly_limit,
            teacher_id=teacher_id,
            evening_item_ids=evening_item_ids,
            allow_limit_excess=allow_limit_excess,
        )
        self._repository.replace_for_teacher_year(
            teacher_id, academic_year_id, plan.selections, allow_limit_excess
        )
        return plan
