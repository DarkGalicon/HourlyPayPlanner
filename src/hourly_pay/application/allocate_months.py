from collections.abc import Mapping
from decimal import Decimal

from hourly_pay.domain.allocation import (
    MonthlyAllocationPlan,
    build_monthly_allocation_plan,
)
from hourly_pay.domain.models import AcademicYear, HourlySelection, WorkloadItem


def allocate_selection_months(
    *,
    selection: HourlySelection,
    item: WorkloadItem,
    academic_year: AcademicYear,
    monthly_hours: Mapping[int, Decimal],
    include_january: bool = False,
    semester_override: int | None = None,
) -> MonthlyAllocationPlan:
    return build_monthly_allocation_plan(
        selection=selection,
        item=item,
        academic_year=academic_year,
        monthly_hours=monthly_hours,
        include_january=include_january,
        semester_override=semester_override,
    )
