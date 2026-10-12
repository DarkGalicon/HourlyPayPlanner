from decimal import Decimal

from hourly_pay.domain.errors import InvalidCalculationError
from hourly_pay.domain.models import HourlyCalculation
from hourly_pay.domain.rules import HOURS_PER_RATE, MAX_HOURLY_HOURS

ZERO = Decimal("0")


def calculate_hourly_limit(
    *,
    effective_rate: Decimal,
    fact_hours: Decimal,
    idpo_hours: Decimal,
    eligible_hours: Decimal,
) -> HourlyCalculation:
    """Calculate the distributable hourly-pay limit from confirmed input values."""
    values = {
        "effective_rate": effective_rate,
        "fact_hours": fact_hours,
        "idpo_hours": idpo_hours,
        "eligible_hours": eligible_hours,
    }
    for name, value in values.items():
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} должен быть Decimal, получено {type(value).__name__}")
        if value < ZERO:
            raise InvalidCalculationError(f"{name} не может быть отрицательным: {value}")

    norm_hours = effective_rate * HOURS_PER_RATE
    net_hours = fact_hours - idpo_hours
    excess_hours = max(ZERO, net_hours - norm_hours)
    hourly_limit = min(excess_hours, MAX_HOURLY_HOURS, eligible_hours)

    return HourlyCalculation(
        effective_rate=effective_rate,
        norm_hours=norm_hours,
        fact_hours=fact_hours,
        idpo_hours=idpo_hours,
        net_hours=net_hours,
        excess_hours=excess_hours,
        eligible_auditory_hours=eligible_hours,
        hourly_limit=hourly_limit,
    )
