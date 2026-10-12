from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from hourly_pay.app import create_main_window
from hourly_pay.application.availability_settings import AvailabilitySettingsService
from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import HourlySelection, MonthlyAllocation
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.orm_models import GenerationBatchRecord, LessonRecord
from hourly_pay.persistence.repositories import (
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    ScheduleRepository,
    WorkloadRepository,
)
from hourly_pay.ui.pages.availability_page import AvailabilityPage
from hourly_pay.ui.theme import apply_application_appearance


def _saved_teacher(tmp_path: Path, synthetic_workbook: Path):
    database_path = tmp_path / "availability.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    imports = WorkloadRepository(factory)
    saved = imports.save_import(NagrXlsxV1Importer().import_file(synthetic_workbook))
    schedules = ScheduleRepository(factory)
    return saved, imports, schedules, factory


def test_availability_rules_are_validated_and_persisted(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, imports, schedules, _ = _saved_teacher(tmp_path, synthetic_workbook)
    service = AvailabilitySettingsService(imports, schedules)
    closed = date(2026, 9, 2)
    special = date(2026, 9, 3)
    rules = service.save(
        saved.teacher_id,
        weekdays={0: {1, 3}, 4: {7}},
        excluded_dates={closed},
        per_date={special: {2}},
    )
    assert service.load(saved.teacher_id).availability == rules
    assert rules.allowed_slots(closed) == frozenset()
    assert rules.allowed_slots(special) == frozenset({2})
    assert rules.allowed_slots(date(2026, 9, 7)) == frozenset({1, 3})

    with pytest.raises(InvalidScheduleError, match="одновременно"):
        service.save(
            saved.teacher_id,
            weekdays={},
            excluded_dates={closed},
            per_date={closed: {1}},
        )
    with pytest.raises(InvalidScheduleError, match="выходного"):
        service.save(
            saved.teacher_id,
            weekdays={},
            excluded_dates=(),
            per_date={date(2026, 9, 5): {1}},
        )
    with pytest.raises(InvalidScheduleError, match="неизвестные"):
        service.save(
            saved.teacher_id,
            weekdays={0: {999}},
            excluded_dates=(),
            per_date={},
        )
    assert schedules.get_availability(saved.teacher_id) == rules


def test_availability_page_saves_grid_and_date_exceptions(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, imports, schedules, _ = _saved_teacher(tmp_path, synthetic_workbook)
    page = AvailabilityPage(AvailabilitySettingsService(imports, schedules))
    qtbot.addWidget(page)
    page.show()
    assert page.teacher_box.currentData() == saved.teacher_id
    assert page.week_table.rowCount() == 7

    page.week_table.cellWidget(0, 0).setChecked(True)
    page.week_table.cellWidget(2, 0).setChecked(True)
    qtbot.mouseClick(page.add_exclusion_button, Qt.MouseButton.LeftButton)
    page.exception_table.cellWidget(0, 1).setDate(QDate(2026, 9, 2))
    qtbot.mouseClick(page.add_date_slots_button, Qt.MouseButton.LeftButton)
    page.exception_table.cellWidget(1, 1).setDate(QDate(2026, 9, 3))
    page.exception_table.cellWidget(1, 3).setChecked(True)
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert page.status_label.text() == "Доступность сохранена."
    restored = schedules.get_availability(saved.teacher_id)
    assert restored.weekday_allowed_slots[0] == frozenset({1, 3})
    assert restored.excluded_dates == frozenset({date(2026, 9, 2)})
    assert restored.per_date_allowed_slots[date(2026, 9, 3)] == frozenset({2})
    assert page.exception_table.rowCount() == 2

    qtbot.mouseClick(page.add_exclusion_button, Qt.MouseButton.LeftButton)
    page.exception_table.cellWidget(2, 1).setDate(QDate(2026, 9, 2))
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert "несколько раз" in page.status_label.text()
    assert schedules.get_availability(saved.teacher_id) == restored


def test_dark_system_palette_keeps_dropdowns_and_slot_times_readable(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    _saved_teacher(tmp_path, synthetic_workbook)
    application = QApplication.instance()
    original_palette = application.palette()
    original_stylesheet = application.styleSheet()
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Base, QColor("#202020"))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor("#2867cb"))
    application.setPalette(dark_palette)
    try:
        apply_application_appearance(application)
        window = create_main_window(tmp_path / "availability.db")
        qtbot.addWidget(window)
        window.show()
        window.tabs.setCurrentWidget(window.schedule_tabs)
        window.schedule_tabs.setCurrentWidget(window.availability_page)
        application.processEvents()

        popup_palette = window.availability_page.teacher_box.view().palette()
        assert popup_palette.color(QPalette.ColorRole.Base) == QColor("#ffffff")
        assert popup_palette.color(QPalette.ColorRole.Text) == QColor("#23344a")
        assert popup_palette.color(QPalette.ColorRole.HighlightedText) == QColor("#183a62")

        table = window.availability_page.week_table
        assert table.rowCount() == 7
        assert table.verticalHeader().isVisible()
        assert table.verticalHeaderItem(0).text()
        assert table.verticalHeader().width() > 80
    finally:
        if "window" in locals():
            window.close()
            window.database_engine.dispose()
        application.setStyleSheet(original_stylesheet)
        application.setPalette(original_palette)


def test_availability_change_cannot_invalidate_saved_lesson(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    saved, imports, schedules, factory = _saved_teacher(tmp_path, synthetic_workbook)
    service = AvailabilitySettingsService(imports, schedules)
    service.save(saved.teacher_id, weekdays={0: {1}}, excluded_dates=(), per_date={})
    restored = imports.get_import(saved.source_id)
    assert restored is not None
    item = next(item for item in restored.items if not item.is_idpo)
    assert item.id is not None
    selections = HourlySelectionRepository(factory)
    selections.replace_for_teacher_year(
        saved.teacher_id,
        saved.academic_year_id,
        (HourlySelection(item.id, Decimal("2"), teacher_id=saved.teacher_id),),
    )
    selection_id = selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id)[0].id
    assert selection_id is not None
    allocations = MonthlyAllocationRepository(factory)
    allocations.replace_plans(
        ((selection_id, (MonthlyAllocation(selection_id, 9, 2026, Decimal("2")),)),)
    )
    allocation_id = allocations.list_for_selection(selection_id)[0].id
    assert allocation_id is not None
    with factory.begin() as session:
        batch = GenerationBatchRecord(teacher_id=saved.teacher_id, year=2026, month=9)
        session.add(batch)
        session.flush()
        session.add(
            LessonRecord(
                teacher_id=saved.teacher_id,
                monthly_allocation_id=allocation_id,
                lesson_date=date(2026, 9, 7),
                time_slot_id=1,
                group_name="ГРУППА",
                discipline="Дисциплина",
                work_type="LECTURE",
                hours=Decimal("2"),
                generation_batch_id=batch.id,
            )
        )

    with pytest.raises(InvalidScheduleError, match="уже сохранённые занятия"):
        service.save(saved.teacher_id, weekdays={0: set()}, excluded_dates=(), per_date={})
    assert schedules.get_availability(saved.teacher_id).weekday_allowed_slots[0] == frozenset({1})
