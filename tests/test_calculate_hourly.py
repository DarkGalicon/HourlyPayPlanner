from decimal import Decimal

import pytest

from hourly_pay.application.calculate_hourly import calculate_hourly_limit
from hourly_pay.domain.errors import InvalidCalculationError


@pytest.mark.parametrize(
    ("rate", "expected_norm"),
    [
        (Decimal("1"), Decimal("900")),
        (Decimal("0.5"), Decimal("450.0")),
    ],
)
def test_norm_is_900_hours_per_rate(rate: Decimal, expected_norm: Decimal) -> None:
    result = calculate_hourly_limit(
        effective_rate=rate,
        fact_hours=Decimal("0"),
        idpo_hours=Decimal("0"),
        eligible_hours=Decimal("0"),
    )
    assert result.norm_hours == expected_norm


def test_negative_excess_is_clamped_to_zero() -> None:
    result = calculate_hourly_limit(
        effective_rate=Decimal("1"),
        fact_hours=Decimal("800"),
        idpo_hours=Decimal("0"),
        eligible_hours=Decimal("500"),
    )
    assert result.excess_hours == Decimal("0")
    assert result.hourly_limit == Decimal("0")


def test_idpo_is_subtracted_before_excess() -> None:
    result = calculate_hourly_limit(
        effective_rate=Decimal("1"),
        fact_hours=Decimal("1100"),
        idpo_hours=Decimal("40"),
        eligible_hours=Decimal("500"),
    )
    assert result.net_hours == Decimal("1060")
    assert result.excess_hours == Decimal("160")
    assert result.hourly_limit == Decimal("160")


def test_limit_is_capped_at_300_hours() -> None:
    result = calculate_hourly_limit(
        effective_rate=Decimal("0"),
        fact_hours=Decimal("500"),
        idpo_hours=Decimal("0"),
        eligible_hours=Decimal("500"),
    )
    assert result.hourly_limit == Decimal("300")


def test_limit_is_capped_by_eligible_auditory_hours() -> None:
    result = calculate_hourly_limit(
        effective_rate=Decimal("0.5"),
        fact_hours=Decimal("700"),
        idpo_hours=Decimal("0"),
        eligible_hours=Decimal("180"),
    )
    assert result.excess_hours == Decimal("250.0")
    assert result.hourly_limit == Decimal("180")


def test_decimal_arithmetic_has_no_float_drift() -> None:
    result = calculate_hourly_limit(
        effective_rate=Decimal("0.33"),
        fact_hours=Decimal("500.10"),
        idpo_hours=Decimal("3.72"),
        eligible_hours=Decimal("250.05"),
    )
    assert result.norm_hours == Decimal("297.00")
    assert result.net_hours == Decimal("496.38")
    assert result.excess_hours == Decimal("199.38")
    assert result.hourly_limit == Decimal("199.38")


@pytest.mark.parametrize("field", ["effective_rate", "fact_hours", "idpo_hours", "eligible_hours"])
def test_negative_inputs_are_rejected(field: str) -> None:
    values = {
        "effective_rate": Decimal("1"),
        "fact_hours": Decimal("900"),
        "idpo_hours": Decimal("0"),
        "eligible_hours": Decimal("100"),
    }
    values[field] = Decimal("-1")
    with pytest.raises(InvalidCalculationError, match="не может быть отрицательным"):
        calculate_hourly_limit(**values)


def test_float_inputs_are_rejected() -> None:
    with pytest.raises(TypeError, match="должен быть Decimal"):
        calculate_hourly_limit(
            effective_rate=1.0,  # type: ignore[arg-type]
            fact_hours=Decimal("900"),
            idpo_hours=Decimal("0"),
            eligible_hours=Decimal("100"),
        )
