from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from hourly_pay.domain.errors import InvalidSelectionError
from hourly_pay.domain.models import HourlySelection, WorkloadItem
from hourly_pay.domain.rules import AUDITORY_WORK_TYPES, MAX_HOURLY_HOURS, is_even_hours

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SelectionPlan:
    selections: tuple[HourlySelection, ...]
    selected_total: Decimal
    hourly_limit: Decimal
    remaining_hours: Decimal


def build_selection_plan(
    *,
    items: Iterable[WorkloadItem],
    requested_hours: Mapping[int, Decimal],
    hourly_limit: Decimal,
    teacher_id: int | None = None,
    evening_item_ids: frozenset[int] = frozenset(),
    allow_limit_excess: bool = False,
) -> SelectionPlan:
    _validate_decimal("hourly_limit", hourly_limit)
    if hourly_limit < ZERO:
        raise InvalidSelectionError("Лимит почасовки не может быть отрицательным.")

    items_by_id: dict[int, WorkloadItem] = {}
    for item in items:
        if item.id is None:
            continue
        if item.id in items_by_id:
            raise InvalidSelectionError(f"Строка нагрузки {item.id} передана дважды.")
        items_by_id[item.id] = item

    selections: list[HourlySelection] = []
    for workload_item_id, selected_hours in requested_hours.items():
        item = items_by_id.get(workload_item_id)
        if item is None:
            raise InvalidSelectionError(f"Строка нагрузки {workload_item_id} не найдена.")
        _validate_selected_hours(item, selected_hours)
        selections.append(
            HourlySelection(
                workload_item_id=workload_item_id,
                selected_hours=selected_hours,
                teacher_id=teacher_id,
                prefer_evening=workload_item_id in evening_item_ids,
            )
        )

    if evening_item_ids - requested_hours.keys():
        raise InvalidSelectionError("Вечерний приоритет задан для невыбранной строки нагрузки.")

    selected_total = sum(
        (selection.selected_hours for selection in selections), start=Decimal("0")
    )
    if selected_total > MAX_HOURLY_HOURS:
        raise InvalidSelectionError(
            f"Выбрано {selected_total} ч., что превышает максимум {MAX_HOURLY_HOURS} ч."
        )
    if selected_total > hourly_limit and not allow_limit_excess:
        raise InvalidSelectionError(
            f"Выбрано {selected_total} ч., что превышает лимит {hourly_limit} ч."
        )

    return SelectionPlan(
        selections=tuple(selections),
        selected_total=selected_total,
        hourly_limit=hourly_limit,
        remaining_hours=hourly_limit - selected_total,
    )


def _validate_selected_hours(item: WorkloadItem, selected_hours: Decimal) -> None:
    _validate_decimal("selected_hours", selected_hours)
    if selected_hours < ZERO:
        raise InvalidSelectionError("Выбранные часы не могут быть отрицательными.")
    if not is_even_hours(selected_hours):
        raise InvalidSelectionError(
            f"Выбранные часы должны быть кратны 2: получено {selected_hours}."
        )
    if selected_hours > item.hours:
        raise InvalidSelectionError(
            f"Нельзя выбрать {selected_hours} ч.: доступно {item.hours} ч."
        )
    if selected_hours > ZERO and item.is_idpo:
        raise InvalidSelectionError("Часы ИДПО нельзя повторно включать в обычную почасовку.")
    if selected_hours > ZERO and item.work_type not in AUDITORY_WORK_TYPES:
        raise InvalidSelectionError(
            f"Вид нагрузки {item.work_type.value} не допускается в почасовку."
        )


def _validate_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} должен быть Decimal, получено {type(value).__name__}")
