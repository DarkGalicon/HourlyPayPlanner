from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PySide6.QtCore import Qt
from sqlalchemy import inspect

from hourly_pay.application.semester_settings import SemesterSettingsService, semester_for_month
from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import AcademicYear
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.orm_models import AcademicYearRecord
from hourly_pay.persistence.repositories import SemesterStartRepository
from hourly_pay.ui.pages.semester_page import SemesterPage


def _service(tmp_path: Path) -> tuple[SemesterSettingsService, int]:
    database_path = tmp_path / "semester.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    with factory.begin() as session:
        record = AcademicYearRecord(name="2026-2027", is_active=True)
        session.add(record)
        session.flush()
        year_id = record.id
    return SemesterSettingsService(SemesterStartRepository(factory)), year_id


def test_existing_database_upgrades_without_losing_academic_year(tmp_path: Path) -> None:
    database_path = tmp_path / "upgrade.db"
    config = Config()
    migrations = Path(__file__).resolve().parents[1] / "src/hourly_pay/persistence/migrations"
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "0005_calendar_overrides")
    factory = create_session_factory(create_sqlite_engine(database_path))
    with factory.begin() as session:
        session.add(AcademicYearRecord(name="2026-2027", is_active=True))
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    assert "semester_practice_starts" in inspect(engine).get_table_names()
    assert SemesterSettingsService(SemesterStartRepository(
        create_session_factory(engine)
    )).list_years()[0].name == "2026-2027"


def test_semester_dates_are_explicit_and_persisted(tmp_path: Path) -> None:
    service, year_id = _service(tmp_path)
    assert service.list_years() == (AcademicYear("2026-2027", True, year_id),)
    assert service.get(year_id, 1) is None
    assert service.get(year_id, 2) is None
    service.save(year_id, 1, date(2026, 9, 14))
    service.save(year_id, 2, date(2027, 2, 8))
    assert service.get(year_id, 1) == date(2026, 9, 14)
    assert service.get(year_id, 2) == date(2027, 2, 8)
    service.save(year_id, 1, None)
    assert service.get(year_id, 1) is None
    assert service.get(year_id, 2) == date(2027, 2, 8)


@pytest.mark.parametrize("semester, value", [
    (1, date(2026, 8, 31)),
    (1, date(2027, 9, 1)),
    (2, date(2026, 12, 1)),
    (2, date(2027, 6, 1)),
])
def test_date_must_belong_to_selected_semester(
    tmp_path: Path, semester: int, value: date
) -> None:
    service, year_id = _service(tmp_path)
    with pytest.raises(InvalidScheduleError, match="Дата допуска"):
        service.save(year_id, semester, value)
    assert service.get(year_id, semester) is None


def test_semester_months_follow_academic_year_without_assuming_start_week() -> None:
    assert [semester_for_month(month) for month in (9, 12, 1, 2, 5)] == [1, 1, 2, 2, 2]
    with pytest.raises(InvalidScheduleError, match="не входит"):
        semester_for_month(8)


def test_semester_page_saves_explicit_dates(qtbot, tmp_path: Path) -> None:
    service, year_id = _service(tmp_path)
    page = SemesterPage(service)
    qtbot.addWidget(page)
    assert page.year_box.currentData() == year_id
    assert page.start_inputs[1].text() == ""
    page.start_inputs[1].setText("14.09.2026")
    page.start_inputs[2].setText("08.02.2027")
    qtbot.mouseClick(page.save_buttons[1], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(page.save_buttons[2], Qt.MouseButton.LeftButton)
    assert service.get(year_id, 1) == date(2026, 9, 14)
    assert service.get(year_id, 2) == date(2027, 2, 8)
    assert "сохранена" in page.status_label.text()
