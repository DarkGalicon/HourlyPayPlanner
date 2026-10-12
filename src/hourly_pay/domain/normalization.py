from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from hourly_pay.domain.enums import StudyForm, WorkType
from hourly_pay.domain.models import WorkloadItem
from hourly_pay.domain.rules import AUDITORY_WORK_TYPES, counts_toward_plan


@dataclass(frozen=True, slots=True)
class WorkloadBreakdown:
    total_hours: Decimal
    full_time_hours: Decimal
    correspondence_hours: Decimal
    semester_1_hours: Decimal
    semester_2_hours: Decimal
    semester_unassigned_hours: Decimal
    idpo_hours: Decimal
    eligible_auditory_hours: Decimal
    hours_by_work_type: dict[WorkType, Decimal]


def summarize_workload(items: Iterable[WorkloadItem]) -> WorkloadBreakdown:
    materialized = tuple(item for item in items if counts_toward_plan(item))
    by_work_type: defaultdict[WorkType, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in materialized:
        by_work_type[item.work_type] += item.hours

    return WorkloadBreakdown(
        total_hours=_sum(item.hours for item in materialized),
        full_time_hours=_sum(
            item.hours for item in materialized if item.study_form is StudyForm.FULL_TIME
        ),
        correspondence_hours=_sum(
            item.hours
            for item in materialized
            if item.study_form is StudyForm.CORRESPONDENCE
        ),
        semester_1_hours=_sum(item.hours for item in materialized if item.semester == 1),
        semester_2_hours=_sum(item.hours for item in materialized if item.semester == 2),
        semester_unassigned_hours=_sum(
            item.hours for item in materialized if item.semester is None
        ),
        idpo_hours=_sum(item.hours for item in materialized if item.is_idpo),
        eligible_auditory_hours=_sum(
            item.hours
            for item in materialized
            if item.work_type in AUDITORY_WORK_TYPES and not item.is_idpo
        ),
        hours_by_work_type=dict(by_work_type),
    )


def _sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, start=Decimal("0"))
