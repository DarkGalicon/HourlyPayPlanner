from decimal import Decimal

import pytest

from hourly_pay.application.allocate_months import allocate_selection_months
from hourly_pay.domain.enums import StudyForm, WorkType
from hourly_pay.domain.errors import InvalidMonthlyAllocationError
from hourly_pay.domain.models import AcademicYear, HourlySelection, WorkloadItem


def _item(*, semester: int | None, item_id: int = 10) -> WorkloadItem:
    return WorkloadItem(
        id=item_id,
        study_form=(
            StudyForm.CORRESPONDENCE if semester is None else StudyForm.FULL_TIME
        ),
        semester=semester,
        source_row_number=1,
        group_name="ГРУППА",
        discipline="Дисциплина",
        work_type=WorkType.LECTURE,
        hours=Decimal("20"),
    )


def _selection(*, selected: str = "10", item_id: int = 10) -> HourlySelection:
    return HourlySelection(
        id=20,
        teacher_id=1,
        workload_item_id=item_id,
        selected_hours=Decimal(selected),
    )


def test_first_semester_uses_september_through_december_of_start_year() -> None:
    result = allocate_selection_months(
        selection=_selection(),
        item=_item(semester=1),
        academic_year=AcademicYear("2026-2027"),
        monthly_hours={9: Decimal("2"), 10: Decimal("8")},
    )
    assert [(value.year, value.month, value.hours) for value in result.allocations] == [
        (2026, 9, Decimal("2")),
        (2026, 10, Decimal("8")),
    ]


def test_first_semester_rejects_second_semester_month() -> None:
    with pytest.raises(InvalidMonthlyAllocationError, match="недоступен"):
        allocate_selection_months(
            selection=_selection(),
            item=_item(semester=1),
            academic_year=AcademicYear("2026-2027"),
            monthly_hours={2: Decimal("10")},
        )


def test_second_semester_rejects_january_without_explicit_flag() -> None:
    with pytest.raises(InvalidMonthlyAllocationError, match="недоступен"):
        allocate_selection_months(
            selection=_selection(),
            item=_item(semester=2),
            academic_year=AcademicYear("2026-2027"),
            monthly_hours={1: Decimal("10")},
        )


def test_second_semester_allows_january_with_explicit_flag() -> None:
    result = allocate_selection_months(
        selection=_selection(),
        item=_item(semester=2),
        academic_year=AcademicYear("2026-2027"),
        monthly_hours={1: Decimal("2"), 5: Decimal("8")},
        include_january=True,
    )
    assert {(value.year, value.month) for value in result.allocations} == {
        (2027, 1),
        (2027, 5),
    }


def test_correspondence_requires_manual_semester_override() -> None:
    with pytest.raises(InvalidMonthlyAllocationError, match="semester_override"):
        allocate_selection_months(
            selection=_selection(),
            item=_item(semester=None),
            academic_year=AcademicYear("2026-2027"),
            monthly_hours={9: Decimal("10")},
        )


def test_correspondence_can_be_allocated_after_manual_override() -> None:
    result = allocate_selection_months(
        selection=_selection(),
        item=_item(semester=None),
        academic_year=AcademicYear("2026-2027"),
        monthly_hours={3: Decimal("10")},
        semester_override=2,
    )
    assert result.semester == 2
    assert result.allocations[0].year == 2027


def test_month_sum_must_equal_selected_hours() -> None:
    with pytest.raises(InvalidMonthlyAllocationError, match="Сумма по месяцам"):
        allocate_selection_months(
            selection=_selection(selected="10"),
            item=_item(semester=1),
            academic_year=AcademicYear("2026-2027"),
            monthly_hours={9: Decimal("2"), 10: Decimal("6")},
        )


@pytest.mark.parametrize("hours", [Decimal("-2"), Decimal("3"), Decimal("1.5")])
def test_each_month_must_be_non_negative_and_even(hours: Decimal) -> None:
    with pytest.raises(InvalidMonthlyAllocationError):
        allocate_selection_months(
            selection=_selection(selected="10"),
            item=_item(semester=1),
            academic_year=AcademicYear("2026-2027"),
            monthly_hours={9: hours, 10: Decimal("10") - hours},
        )


def test_zero_selection_with_empty_months_is_valid() -> None:
    result = allocate_selection_months(
        selection=_selection(selected="0"),
        item=_item(semester=1),
        academic_year=AcademicYear("2026-2027"),
        monthly_hours={},
    )
    assert result.allocations == ()
    assert result.allocated_hours == Decimal("0")


def test_invalid_academic_year_is_rejected() -> None:
    with pytest.raises(InvalidMonthlyAllocationError, match="учебный год"):
        allocate_selection_months(
            selection=_selection(),
            item=_item(semester=1),
            academic_year=AcademicYear("2026"),
            monthly_hours={9: Decimal("10")},
        )


def test_unsaved_selection_is_rejected() -> None:
    selection = _selection()
    selection.id = None
    with pytest.raises(InvalidMonthlyAllocationError, match="Сначала сохраните"):
        allocate_selection_months(
            selection=selection,
            item=_item(semester=1),
            academic_year=AcademicYear("2026-2027"),
            monthly_hours={9: Decimal("10")},
        )
