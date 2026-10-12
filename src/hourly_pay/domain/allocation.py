import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from hourly_pay.domain.errors import InvalidMonthlyAllocationError
from hourly_pay.domain.models import (
    AcademicYear,
    HourlySelection,
    MonthlyAllocation,
    WorkloadItem,
)
from hourly_pay.domain.rules import is_even_hours

_ACADEMIC_YEAR_RE = re.compile(r"^(20\d{2})-(20\d{2})$")
_SEMESTER_1_MONTHS = frozenset({9, 10, 11, 12})
_SEMESTER_2_MONTHS = frozenset({2, 3, 4, 5})
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MonthlyAllocationPlan:
    allocations: tuple[MonthlyAllocation, ...]
    semester: int
    selected_hours: Decimal
    allocated_hours: Decimal


def build_monthly_allocation_plan(
    *,
    selection: HourlySelection,
    item: WorkloadItem,
    academic_year: AcademicYear,
    monthly_hours: Mapping[int, Decimal],
    include_january: bool = False,
    semester_override: int | None = None,
) -> MonthlyAllocationPlan:
    if selection.id is None:
        raise InvalidMonthlyAllocationError(
            "Сначала сохраните выбор нагрузки, затем распределяйте его по месяцам."
        )
    if item.id != selection.workload_item_id:
        raise InvalidMonthlyAllocationError("Выбор не соответствует строке нагрузки.")

    semester = semester_override if semester_override is not None else item.semester
    if semester not in (1, 2):
        raise InvalidMonthlyAllocationError(
            "Для строки без семестра требуется явно указать semester_override=1 или 2."
        )
    start_year, end_year = _parse_academic_year(academic_year.name)
    allowed_months = _allowed_months(semester, include_january=include_january)

    allocations: list[MonthlyAllocation] = []
    for month, hours in monthly_hours.items():
        if month not in allowed_months:
            raise InvalidMonthlyAllocationError(
                f"Месяц {month} недоступен для {semester}-го семестра."
            )
        _validate_month_hours(month, hours)
        year = start_year if semester == 1 else end_year
        allocations.append(
            MonthlyAllocation(
                hourly_selection_id=selection.id,
                month=month,
                year=year,
                hours=hours,
            )
        )

    allocations.sort(key=lambda allocation: (allocation.year, allocation.month))
    allocated_hours = sum(
        (allocation.hours for allocation in allocations), start=Decimal("0")
    )
    if allocated_hours != selection.selected_hours:
        raise InvalidMonthlyAllocationError(
            "Сумма по месяцам должна совпадать с выбранными часами: "
            f"выбрано {selection.selected_hours}, распределено {allocated_hours}."
        )
    return MonthlyAllocationPlan(
        allocations=tuple(allocations),
        semester=semester,
        selected_hours=selection.selected_hours,
        allocated_hours=allocated_hours,
    )


def _parse_academic_year(name: str) -> tuple[int, int]:
    match = _ACADEMIC_YEAR_RE.fullmatch(name.strip())
    if match is None:
        raise InvalidMonthlyAllocationError(f"Некорректный учебный год: {name!r}.")
    start_year, end_year = (int(value) for value in match.groups())
    if end_year != start_year + 1:
        raise InvalidMonthlyAllocationError(
            f"Учебный год должен состоять из последовательных лет: {name!r}."
        )
    return start_year, end_year


def _allowed_months(semester: int, *, include_january: bool) -> frozenset[int]:
    if semester == 1:
        return _SEMESTER_1_MONTHS
    if include_january:
        return _SEMESTER_2_MONTHS | {1}
    return _SEMESTER_2_MONTHS


def _validate_month_hours(month: int, hours: Decimal) -> None:
    if not isinstance(hours, Decimal):
        raise TypeError(
            f"Часы месяца {month} должны быть Decimal, получено {type(hours).__name__}."
        )
    if hours < ZERO:
        raise InvalidMonthlyAllocationError(
            f"Часы месяца {month} не могут быть отрицательными."
        )
    if not is_even_hours(hours):
        raise InvalidMonthlyAllocationError(
            f"Часы месяца {month} должны быть кратны 2: получено {hours}."
        )
