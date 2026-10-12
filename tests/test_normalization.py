from decimal import Decimal

from hourly_pay.application.normalize_workload import normalize_workload
from hourly_pay.domain.enums import StudyForm, WarningCode, WorkType
from hourly_pay.domain.models import WorkloadItem
from hourly_pay.domain.normalization import summarize_workload


def _item(
    *,
    hours: str,
    work_type: WorkType,
    row: int,
    study_form: StudyForm = StudyForm.FULL_TIME,
    semester: int | None = 1,
    group: str | None = "ГРУППА",
    discipline: str | None = "Дисциплина",
    row_total: str | None = None,
    control_type: str | None = None,
) -> WorkloadItem:
    return WorkloadItem(
        study_form=study_form,
        semester=semester,
        source_row_number=row,
        group_name=group,
        discipline=discipline,
        work_type=work_type,
        control_type=control_type,
        hours=Decimal(hours),
        row_total_hours=Decimal(row_total) if row_total is not None else None,
        is_idpo=bool(group and group.startswith("ИДПО_")),
        raw_context={"sheet": "Test"},
    )


def test_workload_breakdown_uses_decimal_and_keeps_unassigned_correspondence() -> None:
    items = [
        _item(hours="10", work_type=WorkType.LECTURE, row=1),
        _item(hours="3.72", work_type=WorkType.CONTROL, row=2, semester=2),
        _item(
            hours="4",
            work_type=WorkType.PRACTICE,
            row=3,
            study_form=StudyForm.CORRESPONDENCE,
            semester=None,
            group="ИДПО_TEST",
        ),
    ]

    result = summarize_workload(items)

    assert result.total_hours == Decimal("17.72")
    assert result.full_time_hours == Decimal("13.72")
    assert result.correspondence_hours == Decimal("4")
    assert result.semester_1_hours == Decimal("10")
    assert result.semester_2_hours == Decimal("3.72")
    assert result.semester_unassigned_hours == Decimal("4")
    assert result.idpo_hours == Decimal("4")
    assert result.eligible_auditory_hours == Decimal("10")


def test_anomalies_are_grouped_by_source_row() -> None:
    items = [
        _item(
            hours="3",
            work_type=WorkType.LECTURE,
            row=7,
            group=None,
            discipline=None,
            row_total="6",
        ),
        _item(
            hours="1",
            work_type=WorkType.CONTROL,
            row=7,
            group=None,
            discipline=None,
            row_total="6",
            control_type="Неизвестный",
        ),
    ]

    result = normalize_workload(items)
    codes = [warning.code for warning in result.warnings]

    assert codes.count(WarningCode.MISSING_GROUP) == 1
    assert codes.count(WarningCode.MISSING_DISCIPLINE) == 1
    assert codes.count(WarningCode.UNEXPLAINED_TOTAL_DIFF) == 1
    assert codes.count(WarningCode.NON_EVEN_AUDITORY_HOURS) == 1
    assert codes.count(WarningCode.UNKNOWN_CONTROL_KIND) == 1


def test_known_exam_and_credit_are_not_anomalies() -> None:
    items = [
        _item(
            hours="2",
            work_type=WorkType.CONTROL,
            row=1,
            row_total="2",
            control_type="Эк",
        ),
        _item(
            hours="2",
            work_type=WorkType.CONTROL,
            row=2,
            row_total="2",
            control_type="Зч",
        ),
    ]

    result = normalize_workload(items)
    assert WarningCode.UNKNOWN_CONTROL_KIND not in {warning.code for warning in result.warnings}
