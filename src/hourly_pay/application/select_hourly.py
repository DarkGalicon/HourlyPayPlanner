from collections.abc import Iterable, Mapping
from decimal import Decimal

from hourly_pay.domain.models import WorkloadItem
from hourly_pay.domain.selection import SelectionPlan, build_selection_plan


def select_hourly_workload(
    *,
    items: Iterable[WorkloadItem],
    requested_hours: Mapping[int, Decimal],
    hourly_limit: Decimal,
    teacher_id: int | None = None,
    evening_item_ids: frozenset[int] = frozenset(),
    allow_limit_excess: bool = False,
) -> SelectionPlan:
    return build_selection_plan(
        items=items,
        requested_hours=requested_hours,
        hourly_limit=hourly_limit,
        teacher_id=teacher_id,
        evening_item_ids=evening_item_ids,
        allow_limit_excess=allow_limit_excess,
    )
