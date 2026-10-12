from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PySide6.QtCore import QDate, Qt
from sqlalchemy import inspect, select

from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import CalendarOverride, HourlySelection, MonthlyAllocation
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.orm_models import GenerationBatchRecord, LessonRecord, TimeSlotRecord
from hourly_pay.persistence.repositories import (
    CalendarOverrideRepository,
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    WorkloadRepository,
)
from hourly_pay.ui.pages.calendar_page import CalendarPage


def _calendar(tmp_path: Path):
    database_path = tmp_path / "calendar.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    repository = CalendarOverrideRepository(factory)
    return CalendarSettingsService(repository), repository, factory


def test_existing_database_upgrades_to_calendar_table_without_losing_slots(tmp_path: Path) -> None:
    database_path = tmp_path / "upgrade.db"
    config = Config()
    migrations = Path(__file__).resolve().parents[1] / "src/hourly_pay/persistence/migrations"
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "0004_scheduler")
    engine = create_sqlite_engine(database_path)
    with create_session_factory(engine)() as session:
        assert len(tuple(session.scalars(select(TimeSlotRecord.id)))) == 7
    engine.dispose()

    upgrade_database(database_path)
    upgraded = create_sqlite_engine(database_path)
    assert "calendar_overrides" in inspect(upgraded).get_table_names()
    with create_session_factory(upgraded)() as session:
        assert len(tuple(session.scalars(select(TimeSlotRecord.id)))) == 7
    upgraded.dispose()


def test_explicit_calendar_overrides_base_holidays_and_rejects_invalid_dates(
    tmp_path: Path,
) -> None:
    service, repository, _ = _calendar(tmp_path)
    holiday = date(2027, 1, 1)
    excluded = date(2027, 3, 1)
    assert holiday in service.base_holidays(2027)
    original = service.policy_for_years([2027])
    assert not original.is_working_date(holiday)
    assert original.is_working_date(excluded)

    saved = service.save(
        (CalendarOverride(holiday, True), CalendarOverride(excluded, False))
    )
    policy = service.policy_for_years([2027])
    assert policy.is_working_date(holiday)
    assert not policy.is_working_date(excluded)
    assert not policy.is_working_date(date(2027, 1, 2))
    assert repository.list_overrides() == saved

    with pytest.raises(InvalidScheduleError, match="несколько раз"):
        service.save((CalendarOverride(holiday, True), CalendarOverride(holiday, False)))
    with pytest.raises(InvalidScheduleError, match="Выходной"):
        service.save((CalendarOverride(date(2027, 1, 2), True),))
    assert repository.list_overrides() == saved


def test_calendar_page_saves_rules_and_shows_base_holiday_effect(
    qtbot, tmp_path: Path
) -> None:
    service, repository, _ = _calendar(tmp_path)
    page = CalendarPage(service)
    qtbot.addWidget(page)
    page.show()
    page.year_box.setValue(2027)
    january_first = next(
        row
        for row in range(page.holiday_table.rowCount())
        if page.holiday_table.item(row, 0).text() == "01.01.2027"
    )
    assert page.holiday_table.item(january_first, 1).text() == "Нерабочий"

    qtbot.mouseClick(page.add_working_button, Qt.MouseButton.LeftButton)
    page.override_table.cellWidget(0, 0).setDate(QDate(2027, 1, 1))
    qtbot.mouseClick(page.add_nonworking_button, Qt.MouseButton.LeftButton)
    page.override_table.cellWidget(1, 0).setDate(QDate(2027, 3, 1))
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Календарь сохранён."
    assert page.holiday_table.item(january_first, 1).text() == "Рабочий по исключению"
    assert len(repository.list_overrides()) == 2

    qtbot.mouseClick(page.add_nonworking_button, Qt.MouseButton.LeftButton)
    page.override_table.cellWidget(2, 0).setDate(QDate(2027, 3, 1))
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert "несколько раз" in page.status_label.text()
    assert len(repository.list_overrides()) == 2


def test_calendar_cannot_exclude_a_date_with_saved_lesson(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository, factory = _calendar(tmp_path)
    imports = WorkloadRepository(factory)
    saved = imports.save_import(NagrXlsxV1Importer().import_file(synthetic_workbook))
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
        service.save((CalendarOverride(date(2026, 9, 7), False),))
    assert repository.list_overrides() == ()
