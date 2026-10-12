from collections import defaultdict
from collections.abc import Collection, Iterable
from decimal import Decimal

from hourly_pay.domain.enums import WarningCode, WarningSeverity
from hourly_pay.domain.models import ImportWarning, WorkloadItem
from hourly_pay.domain.rules import AUDITORY_WORK_TYPES, counts_toward_plan, is_even_hours


def detect_workload_anomalies(
    items: Iterable[WorkloadItem],
    *,
    known_control_kinds: Collection[str] = ("Эк", "Зч"),
) -> list[ImportWarning]:
    """Validate normalized items without depending on their XLSX representation."""
    materialized = tuple(items)
    known_controls = {_normalize(value) for value in known_control_kinds}
    warnings: list[ImportWarning] = []
    rows: dict[tuple[str | None, int], list[WorkloadItem]] = defaultdict(list)

    for item in materialized:
        sheet_name = _sheet_name(item)
        rows[(sheet_name, item.source_row_number)].append(item)
        if item.control_type and _normalize(item.control_type) not in known_controls:
            warnings.append(
                _warning(
                    item,
                    WarningCode.UNKNOWN_CONTROL_KIND,
                    f"Неизвестный вид контроля: {item.control_type}.",
                    raw_value=item.control_type,
                )
            )
        if item.work_type in AUDITORY_WORK_TYPES and not is_even_hours(item.hours):
            warnings.append(
                _warning(
                    item,
                    WarningCode.NON_EVEN_AUDITORY_HOURS,
                    f"Аудиторные часы ({item.hours}) не кратны 2.",
                    raw_value=str(item.hours),
                )
            )

    for row_items in rows.values():
        first = row_items[0]
        if not first.group_name:
            warnings.append(
                _warning(
                    first,
                    WarningCode.MISSING_GROUP,
                    "Есть часы нагрузки, но не указана группа.",
                )
            )
        if not first.discipline:
            warnings.append(
                _warning(
                    first,
                    WarningCode.MISSING_DISCIPLINE,
                    "Есть часы нагрузки, но не указана дисциплина.",
                )
            )
        row_total = first.row_total_hours
        mapped_total = sum(
            (item.hours for item in row_items if counts_toward_plan(item)),
            start=Decimal("0"),
        )
        if row_total is not None and row_total != mapped_total:
            difference = row_total - mapped_total
            warnings.append(
                _warning(
                    first,
                    WarningCode.UNEXPLAINED_TOTAL_DIFF,
                    f"Итого строки отличается от суммы распознанных часов на {difference}.",
                    raw_value=str(difference),
                )
            )

    return warnings


def _warning(
    item: WorkloadItem,
    code: WarningCode,
    message: str,
    *,
    raw_value: str | None = None,
) -> ImportWarning:
    return ImportWarning(
        code=code,
        severity=WarningSeverity.WARNING,
        message=message,
        source_row_number=item.source_row_number,
        raw_value=raw_value,
        sheet_name=_sheet_name(item),
    )


def _sheet_name(item: WorkloadItem) -> str | None:
    value = item.raw_context.get("sheet")
    return str(value) if value is not None else None


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()
