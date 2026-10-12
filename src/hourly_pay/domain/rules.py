from decimal import Decimal

from hourly_pay.domain.enums import WorkType
from hourly_pay.domain.models import WorkloadItem

AUDITORY_WORK_TYPES = frozenset({WorkType.LECTURE, WorkType.PRACTICE, WorkType.LAB})
HOURS_PER_RATE = Decimal("900")
MAX_HOURLY_HOURS = Decimal("300")


def is_idpo_group(group_name: str | None) -> bool:
    return bool(group_name and group_name.strip().startswith("ИДПО_"))


def is_even_hours(value: Decimal) -> bool:
    return value % Decimal("2") == 0


def counts_toward_plan(item: WorkloadItem) -> bool:
    """Some detail columns are explicitly outside the XLSX row's plan total."""
    return item.raw_context.get("outside_row_total") is not True
