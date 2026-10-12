from decimal import Decimal

import pytest

from hourly_pay.application.select_hourly import select_hourly_workload
from hourly_pay.domain.enums import StudyForm, WorkType
from hourly_pay.domain.errors import InvalidSelectionError
from hourly_pay.domain.models import WorkloadItem


def _item(
    item_id: int,
    *,
    hours: str = "10",
    work_type: WorkType = WorkType.LECTURE,
    is_idpo: bool = False,
) -> WorkloadItem:
    return WorkloadItem(
        id=item_id,
        study_form=StudyForm.FULL_TIME,
        semester=1,
        source_row_number=item_id,
        group_name="ИДПО_TEST" if is_idpo else "ГРУППА",
        discipline="Дисциплина",
        work_type=work_type,
        hours=Decimal(hours),
        is_idpo=is_idpo,
    )


def test_zero_selection_is_allowed() -> None:
    result = select_hourly_workload(
        items=[_item(1)],
        requested_hours={1: Decimal("0")},
        hourly_limit=Decimal("100"),
    )
    assert result.selected_total == Decimal("0")
    assert result.remaining_hours == Decimal("100")


def test_partial_even_selection_is_allowed() -> None:
    result = select_hourly_workload(
        items=[_item(1, hours="10")],
        requested_hours={1: Decimal("6")},
        hourly_limit=Decimal("20"),
        teacher_id=7,
    )
    assert result.selected_total == Decimal("6")
    assert result.selections[0].teacher_id == 7


@pytest.mark.parametrize("selected", [Decimal("1"), Decimal("3"), Decimal("3.5")])
def test_odd_or_fractional_selection_is_rejected(selected: Decimal) -> None:
    with pytest.raises(InvalidSelectionError, match="кратны 2"):
        select_hourly_workload(
            items=[_item(1)],
            requested_hours={1: selected},
            hourly_limit=Decimal("100"),
        )


def test_selection_cannot_exceed_item_hours() -> None:
    with pytest.raises(InvalidSelectionError, match="доступно 10"):
        select_hourly_workload(
            items=[_item(1)],
            requested_hours={1: Decimal("12")},
            hourly_limit=Decimal("100"),
        )


def test_total_cannot_exceed_hourly_limit() -> None:
    with pytest.raises(InvalidSelectionError, match="превышает лимит"):
        select_hourly_workload(
            items=[_item(1), _item(2)],
            requested_hours={1: Decimal("8"), 2: Decimal("8")},
            hourly_limit=Decimal("14"),
        )


def test_explicit_permission_allows_excess_but_not_more_than_300() -> None:
    plan = select_hourly_workload(
        items=[_item(1, hours="20")],
        requested_hours={1: Decimal("20")},
        hourly_limit=Decimal("10"),
        allow_limit_excess=True,
    )
    assert plan.selected_total == Decimal("20")
    assert plan.remaining_hours == Decimal("-10")

    with pytest.raises(InvalidSelectionError, match="максимум 300"):
        select_hourly_workload(
            items=[_item(1, hours="302")],
            requested_hours={1: Decimal("302")},
            hourly_limit=Decimal("10"),
            allow_limit_excess=True,
        )


@pytest.mark.parametrize(
    "item",
    [
        _item(1, work_type=WorkType.CONTROL),
        _item(1, work_type=WorkType.COURSEWORK),
        _item(1, is_idpo=True),
    ],
)
def test_non_eligible_or_idpo_hours_cannot_be_selected(item: WorkloadItem) -> None:
    with pytest.raises(InvalidSelectionError):
        select_hourly_workload(
            items=[item],
            requested_hours={1: Decimal("2")},
            hourly_limit=Decimal("100"),
        )


def test_unknown_item_is_rejected() -> None:
    with pytest.raises(InvalidSelectionError, match="не найдена"):
        select_hourly_workload(
            items=[_item(1)],
            requested_hours={999: Decimal("2")},
            hourly_limit=Decimal("100"),
        )


def test_float_selection_is_rejected() -> None:
    with pytest.raises(TypeError, match="должен быть Decimal"):
        select_hourly_workload(
            items=[_item(1)],
            requested_hours={1: 2.0},  # type: ignore[dict-item]
            hourly_limit=Decimal("100"),
        )
