from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import select

from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.application.monthly_planning import MonthlyPlanningService, MonthlyRowDraft
from hourly_pay.application.schedule_month import ScheduleMonthService
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.semester_settings import SemesterSettingsService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.domain.enums import WorkType
from hourly_pay.domain.errors import InvalidScheduleError, ScheduleCapacityError
from hourly_pay.domain.models import CalendarOverride
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.orm_models import LessonRecord
from hourly_pay.persistence.repositories import (
    CalendarOverrideRepository,
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    ScheduleRepository,
    SemesterStartRepository,
    WorkloadRepository,
)
from hourly_pay.scheduler.availability import TeacherAvailability
from hourly_pay.ui.pages.schedule_page import SchedulePage


def _scenario(
    tmp_path: Path,
    synthetic_workbook: Path,
    *,
    selected_hours: Decimal = Decimal("2"),
    complete_plan: bool = True,
    missing_metadata: bool = False,
    work_type: WorkType | None = None,
):
    database_path = tmp_path / "schedule.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    imports = WorkloadRepository(factory)
    parsed = NagrXlsxV1Importer().import_file(synthetic_workbook)
    item = next(item for item in parsed.items if not item.is_idpo)
    item.hours = selected_hours
    if work_type is not None:
        item.work_type = work_type
    if not missing_metadata:
        item.group_name = "ГРУППА"
        item.discipline = "Дисциплина"
    saved = imports.save_import(parsed)
    settings = TeacherSettingsService(imports)
    settings.confirm_effective_rate(saved.teacher_id, Decimal("0"))
    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: True})
    calculations = TeacherCalculationService(imports)
    selections = HourlySelectionRepository(factory)
    selection_service = SelectionService(calculations, selections)
    item_id = selection_service.load(
        saved.teacher_id, saved.academic_year_id
    ).calculation.eligible_items[0].id
    assert item_id is not None
    selection_service.save(
        saved.teacher_id, saved.academic_year_id, {item_id: selected_hours}
    )
    allocations = MonthlyAllocationRepository(factory)
    planning = MonthlyPlanningService(calculations, selections, allocations)
    if complete_plan:
        selection_id = planning.load(saved.teacher_id, saved.academic_year_id).rows[0].selection.id
        assert selection_id is not None
        planning.save(
            saved.teacher_id,
            saved.academic_year_id,
            {selection_id: MonthlyRowDraft({9: selected_hours})},
        )
    schedules = ScheduleRepository(factory)
    calendar = CalendarSettingsService(CalendarOverrideRepository(factory))
    service = ScheduleMonthService(
        planning, schedules, calendar,
        SemesterSettingsService(SemesterStartRepository(factory)),
    )
    return saved, schedules, calendar, service, factory


def test_generates_persists_and_validates_month_without_overwriting(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, calendar, service, _ = _scenario(tmp_path, synthetic_workbook)
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1}) for day in range(5)}),
    )
    calendar.save((CalendarOverride(date(2026, 9, 7), False),))
    assert [(month.year, month.month, month.lesson_count) for month in service.available_months(
        saved.teacher_id, saved.academic_year_id
    )] == [(2026, 9, 1)]

    result = service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=42)
    assert len(result.lessons) == 1
    assert result.lessons[0].lesson_date != date(2026, 9, 7)
    assert result.lessons[0].time_slot_id == 1
    assert len(service.list_lessons(saved.teacher_id, 2026, 9)) == 1
    service.validate_existing(saved.teacher_id, saved.academic_year_id, 2026, 9)
    with pytest.raises(InvalidScheduleError, match="Перегенерировать"):
        service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9)
    assert service.generate(
        saved.teacher_id, saved.academic_year_id, 2026, 9,
        replace_existing=True, seed=43,
    ).batch.seed == 43


def test_semester_date_cannot_invalidate_saved_practice(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, factory = _scenario(tmp_path, synthetic_workbook)
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1}) for day in range(5)}),
    )
    lesson = service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=42).lessons[0]
    with factory.begin() as session:
        record = session.query(LessonRecord).one()
        record.work_type = WorkType.PRACTICE.value
    settings = SemesterSettingsService(SemesterStartRepository(factory))
    with pytest.raises(InvalidScheduleError, match="противоречит"):
        settings.save(saved.academic_year_id, 1, lesson.lesson_date + timedelta(days=1))
    settings.save(saved.academic_year_id, 1, lesson.lesson_date)
    with pytest.raises(InvalidScheduleError, match="противоречит"):
        settings.save(saved.academic_year_id, 1, None)


def test_month_service_uses_unified_semester_date_for_practice(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, factory = _scenario(
        tmp_path, synthetic_workbook, work_type=WorkType.PRACTICE
    )
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1}) for day in range(5)}),
    )
    with pytest.raises(InvalidScheduleError, match="Укажите первую допустимую дату"):
        service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9)
    settings = SemesterSettingsService(SemesterStartRepository(factory))
    settings.save(saved.academic_year_id, 1, date(2026, 9, 14))
    result = service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=42)
    assert result.lessons[0].lesson_date >= date(2026, 9, 14)
    service.validate_existing(saved.teacher_id, saved.academic_year_id, 2026, 9)


def test_manual_move_validates_rules_and_keeps_monthly_plan(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, calendar, service, _ = _scenario(
        tmp_path, synthetic_workbook, selected_hours=Decimal("4")
    )
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1, 2}) for day in range(5)}),
    )
    calendar.save((CalendarOverride(date(2026, 9, 7), False),))
    service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=42)
    lessons = service.list_lessons(saved.teacher_id, 2026, 9)
    first = lessons[0].lesson
    assert first.id is not None
    assert not service.move_lesson(
        saved.teacher_id, saved.academic_year_id, 2026, 9,
        first.id, first.lesson_date, first.time_slot_id,
    )
    for invalid_date, message in (
        (date(2026, 9, 7), "недоступна"),
        (date(2026, 9, 5), "недоступна"),
        (date(2026, 10, 1), "внутри выбранного месяца"),
    ):
        with pytest.raises(InvalidScheduleError, match=message):
            service.move_lesson(
                saved.teacher_id, saved.academic_year_id, 2026, 9,
                first.id, invalid_date, 1,
            )
    target = date(2026, 9, 1)
    if any(row.lesson.lesson_date == target and row.lesson.time_slot_id == 2 for row in lessons):
        target = date(2026, 9, 2)
    assert service.move_lesson(
        saved.teacher_id, saved.academic_year_id, 2026, 9, first.id, target, 2
    )
    moved = next(row.lesson for row in service.list_lessons(saved.teacher_id, 2026, 9)
                 if row.lesson.id == first.id)
    assert (moved.lesson_date, moved.time_slot_id, moved.manual_override) == (target, 2, True)
    assert service.has_manual_changes(saved.teacher_id, 2026, 9)
    service.validate_existing(saved.teacher_id, saved.academic_year_id, 2026, 9)
    assert service.available_months(saved.teacher_id, saved.academic_year_id)[0].lesson_count == 2


def test_first_course_cannot_be_moved_after_1600(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, _ = _scenario(tmp_path, synthetic_workbook)
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({4, 5}) for day in range(5)}),
    )
    lesson = service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=2).lessons[0]
    saved_lesson = service.list_lessons(saved.teacher_id, 2026, 9)[0].lesson
    assert saved_lesson.id is not None
    assert lesson.time_slot_id == 4
    with pytest.raises(InvalidScheduleError, match="первого курса"):
        service.move_lesson(
            saved.teacher_id, saved.academic_year_id, 2026, 9,
            saved_lesson.id, saved_lesson.lesson_date, 5,
        )


def test_manual_move_rejects_occupied_slot_and_early_practice(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, factory = _scenario(
        tmp_path, synthetic_workbook, selected_hours=Decimal("4"),
        work_type=WorkType.PRACTICE,
    )
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1}) for day in range(5)}),
    )
    SemesterSettingsService(SemesterStartRepository(factory)).save(
        saved.academic_year_id, 1, date(2026, 9, 14)
    )
    service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=42)
    first, second = (row.lesson for row in service.list_lessons(saved.teacher_id, 2026, 9))
    assert first.id is not None
    with pytest.raises(InvalidScheduleError, match="раньше"):
        service.move_lesson(
            saved.teacher_id, saved.academic_year_id, 2026, 9,
            first.id, date(2026, 9, 11), 1,
        )
    with pytest.raises(InvalidScheduleError, match="повтор"):
        service.move_lesson(
            saved.teacher_id, saved.academic_year_id, 2026, 9,
            first.id, second.lesson_date, second.time_slot_id,
        )
    assert not service.has_manual_changes(saved.teacher_id, 2026, 9)


def test_clear_month_removes_lessons_but_not_allocation(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, _ = _scenario(tmp_path, synthetic_workbook)
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1}) for day in range(5)}),
    )
    service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9, seed=42)
    assert service.clear_month(saved.teacher_id, saved.academic_year_id, 2026, 9) == 1
    assert service.list_lessons(saved.teacher_id, 2026, 9) == ()
    assert service.available_months(saved.teacher_id, saved.academic_year_id)[0].lesson_count == 1
    assert service.clear_month(saved.teacher_id, saved.academic_year_id, 2026, 9) == 0
    assert len(service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9).lessons) == 1


def test_missing_plan_and_metadata_do_not_create_lessons(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, _ = _scenario(
        tmp_path, synthetic_workbook, complete_plan=False
    )
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={0: frozenset({1})}),
    )
    with pytest.raises(InvalidScheduleError, match="не полностью"):
        service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9)
    assert service.list_lessons(saved.teacher_id, 2026, 9) == ()

    other_path = tmp_path / "missing"
    other_path.mkdir()
    saved2, schedules2, _, service2, _ = _scenario(
        other_path, synthetic_workbook, missing_metadata=True
    )
    schedules2.replace_availability(
        saved2.teacher_id,
        TeacherAvailability(weekday_allowed_slots={0: frozenset({1})}),
    )
    with pytest.raises(InvalidScheduleError, match="нет группы или дисциплины"):
        service2.generate(saved2.teacher_id, saved2.academic_year_id, 2026, 9)
    assert service2.list_lessons(saved2.teacher_id, 2026, 9) == ()


def test_capacity_error_keeps_database_unchanged(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, schedules, _, service, _ = _scenario(
        tmp_path, synthetic_workbook, selected_hours=Decimal("4")
    )
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(per_date_allowed_slots={date(2026, 9, 1): frozenset({1})}),
    )
    with pytest.raises(ScheduleCapacityError) as error:
        service.generate(saved.teacher_id, saved.academic_year_id, 2026, 9)
    assert error.value.needed_lessons == 2
    assert error.value.available_slots == 1
    assert service.list_lessons(saved.teacher_id, 2026, 9) == ()


def test_schedule_page_requires_confirmation_for_regeneration(
    qtbot, tmp_path: Path, synthetic_workbook: Path, monkeypatch
) -> None:
    saved, schedules, _, service, factory = _scenario(tmp_path, synthetic_workbook)
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1}) for day in range(5)}),
    )
    page = SchedulePage(service)
    qtbot.addWidget(page)
    page.show()
    assert page.month_box.currentData() == (2026, 9)
    assert page.generate_button.isEnabled()
    qtbot.mouseClick(page.generate_button, Qt.MouseButton.LeftButton)
    assert page.table.rowCount() == 1
    assert page.regenerate_button.isEnabled()
    assert not page.generate_button.isEnabled()
    qtbot.mouseClick(page.validate_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Конфликтов не найдено."

    questions: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, message: (
            questions.append(message) or QMessageBox.StandardButton.No
        ),
    )
    qtbot.mouseClick(page.regenerate_button, Qt.MouseButton.LeftButton)
    assert questions and "заменит" in questions[0]
    assert page.table.rowCount() == 1

    with factory.begin() as session:
        lesson = session.scalar(select(LessonRecord))
        assert lesson is not None
        lesson.manual_override = True
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, message: (
            questions.append(message) or QMessageBox.StandardButton.Yes
        ),
    )
    qtbot.mouseClick(page.regenerate_button, Qt.MouseButton.LeftButton)
    assert "ручные изменения" in questions[-1]
    assert page.table.rowCount() == 1
    assert not service.has_manual_changes(saved.teacher_id, 2026, 9)


def test_schedule_page_moves_selected_lesson_and_confirms_clear(
    qtbot, tmp_path: Path, synthetic_workbook: Path, monkeypatch
) -> None:
    saved, schedules, _, service, _ = _scenario(tmp_path, synthetic_workbook)
    schedules.replace_availability(
        saved.teacher_id,
        TeacherAvailability(weekday_allowed_slots={day: frozenset({1, 2}) for day in range(5)}),
    )
    page = SchedulePage(service)
    qtbot.addWidget(page)
    page.show()
    qtbot.mouseClick(page.generate_button, Qt.MouseButton.LeftButton)
    page.table.selectRow(0)
    assert page.edit_button.isEnabled()
    original = service.list_lessons(saved.teacher_id, 2026, 9)[0].lesson
    target = date(2026, 9, 1) if original.lesson_date != date(2026, 9, 1) else date(2026, 9, 2)
    page.edit_date.setDate(QDate(target.year, target.month, target.day))
    page.edit_slot.setCurrentIndex(page.edit_slot.findData(2))
    qtbot.mouseClick(page.edit_button, Qt.MouseButton.LeftButton)
    moved = service.list_lessons(saved.teacher_id, 2026, 9)[0].lesson
    assert (moved.lesson_date, moved.time_slot_id, moved.manual_override) == (target, 2, True)
    assert page.table.item(0, 6).text() == "Да"

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    qtbot.mouseClick(page.clear_button, Qt.MouseButton.LeftButton)
    assert page.table.rowCount() == 1
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    qtbot.mouseClick(page.clear_button, Qt.MouseButton.LeftButton)
    assert page.table.rowCount() == 0
    assert page.generate_button.isEnabled()
    assert not page.clear_button.isEnabled()
    assert "удалено занятий 1" in page.status_label.text()


def test_schedule_page_shows_missing_rate_instead_of_generic_month_message(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    database_path = tmp_path / "unconfirmed.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    imports = WorkloadRepository(factory)
    imports.save_import(NagrXlsxV1Importer().import_file(synthetic_workbook))
    calculations = TeacherCalculationService(imports)
    planning = MonthlyPlanningService(
        calculations, HourlySelectionRepository(factory), MonthlyAllocationRepository(factory)
    )
    service = ScheduleMonthService(
        planning,
        ScheduleRepository(factory),
        CalendarSettingsService(CalendarOverrideRepository(factory)),
    )
    page = SchedulePage(service)
    qtbot.addWidget(page)
    assert "Подтвердите эффективную ставку" in page.status_label.text()
    assert not page.generate_button.isEnabled()
