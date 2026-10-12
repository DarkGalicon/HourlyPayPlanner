from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from hourly_pay.application.availability_settings import AvailabilitySettingsService
from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.application.import_workload import ImportWorkloadService
from hourly_pay.application.monthly_planning import MonthlyPlanningService
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.teacher_settings import TeacherPersonalData, TeacherSettingsService
from hourly_pay.domain.errors import InvalidTeacherSettingsError
from hourly_pay.domain.models import HourlySelection
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.repositories import (
    CalendarOverrideRepository,
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    ScheduleRepository,
    WorkloadRepository,
)
from hourly_pay.ui.main_window import MainWindow
from hourly_pay.ui.pages.teacher_page import TeacherPage


def _saved_teacher(
    tmp_path: Path, synthetic_workbook: Path
) -> tuple[TeacherSettingsService, WorkloadRepository, int, int]:
    database_path = tmp_path / "teacher.db"
    upgrade_database(database_path)
    repository = WorkloadRepository(create_session_factory(create_sqlite_engine(database_path)))
    saved = repository.save_import(NagrXlsxV1Importer().import_file(synthetic_workbook))
    return TeacherSettingsService(repository), repository, saved.teacher_id, saved.source_id


def test_rate_is_unset_until_explicit_confirmation_and_source_state_is_tristate(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository, teacher_id, source_id = _saved_teacher(tmp_path, synthetic_workbook)
    profile = service.get_profile(teacher_id)
    assert profile.teacher.effective_rate is None
    assert profile.sources[0].source.reported_rate == Decimal("0.5")
    assert profile.sources[0].source.include_in_fact is None

    service.confirm_effective_rate(teacher_id, Decimal("1.25"))
    service.save_source_inclusions(teacher_id, {source_id: True})
    restored = service.get_profile(teacher_id)
    assert restored.teacher.effective_rate == Decimal("1.2500")
    assert restored.sources[0].source.reported_rate == Decimal("0.5000")
    assert restored.sources[0].source.include_in_fact is True

    service.save_source_inclusions(teacher_id, {source_id: False})
    assert repository.list_teacher_sources(teacher_id)[0].source.include_in_fact is False
    service.save_source_inclusions(teacher_id, {source_id: None})
    assert repository.list_teacher_sources(teacher_id)[0].source.include_in_fact is None


@pytest.mark.parametrize(
    "rate",
    [Decimal("-0.1"), Decimal("NaN"), Decimal("0.12345"), Decimal("1e100")],
)
def test_invalid_effective_rate_is_not_saved(
    tmp_path: Path, synthetic_workbook: Path, rate: Decimal
) -> None:
    service, _, teacher_id, _ = _saved_teacher(tmp_path, synthetic_workbook)
    with pytest.raises(InvalidTeacherSettingsError):
        service.confirm_effective_rate(teacher_id, rate)
    assert service.get_profile(teacher_id).teacher.effective_rate is None


def test_personal_data_is_saved_and_reimport_uses_original_name(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository, teacher_id, _ = _saved_teacher(tmp_path, synthetic_workbook)
    service.save_personal_data(teacher_id, TeacherPersonalData(
        full_name="Исправленное Имя Отчество", degree="к.н.",
        birth_date=date(1980, 4, 15), address="ул. Тестовая, 1",
        passport_series="1234", passport_number="567890",
        passport_issued_by="Отдел МВД", passport_issue_date=date(2001, 5, 6),
        snils="123-456-789 00", inn="123456789012",
    ))
    restored = service.get_profile(teacher_id).teacher
    assert restored.full_name == "Исправленное Имя Отчество"
    assert restored.birth_date == date(1980, 4, 15)
    assert restored.passport_number == "567890"
    assert restored.inn == "123456789012"
    repository.save_import(
        NagrXlsxV1Importer().import_file(synthetic_workbook), allow_duplicate=True
    )
    assert len(service.list_teachers()) == 1
    assert service.list_teachers()[0].full_name == restored.full_name


def test_personal_data_validation_does_not_change_saved_profile(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, _, teacher_id, _ = _saved_teacher(tmp_path, synthetic_workbook)
    with pytest.raises(InvalidTeacherSettingsError, match="ФИО"):
        service.save_personal_data(teacher_id, TeacherPersonalData(full_name="  "))
    with pytest.raises(InvalidTeacherSettingsError, match="слишком длинное"):
        service.save_personal_data(teacher_id, TeacherPersonalData(
            full_name="Тестов Т.Т.", passport_number="1" * 31,
        ))
    assert service.get_profile(teacher_id).teacher.full_name == "Тестов Т.Т."


def test_source_choices_roll_back_if_any_source_is_invalid(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, _, teacher_id, source_id = _saved_teacher(tmp_path, synthetic_workbook)
    with pytest.raises(InvalidTeacherSettingsError, match="не принадлежит"):
        service.save_source_inclusions(teacher_id, {source_id: True, 999_999: False})
    assert service.get_profile(teacher_id).sources[0].source.include_in_fact is None


def test_delete_source_requires_no_saved_selection(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository, teacher_id, source_id = _saved_teacher(tmp_path, synthetic_workbook)
    database_path = tmp_path / "teacher.db"
    factory = create_session_factory(create_sqlite_engine(database_path))
    selections = HourlySelectionRepository(factory)
    item_id = next(
        item.id for item in repository.get_import(source_id).items
        if item.work_type.value == "LECTURE" and not item.is_idpo
    )
    assert item_id is not None
    with pytest.raises(InvalidTeacherSettingsError, match="не найден"):
        service.delete_source(teacher_id, 999_999)
    selections.replace_for_teacher_year(
        teacher_id, repository.get_import(source_id).academic_year.id,
        (HourlySelection(workload_item_id=item_id, selected_hours=Decimal("2"),
                         teacher_id=teacher_id),),
    )
    with pytest.raises(InvalidTeacherSettingsError, match="используется"):
        service.delete_source(teacher_id, source_id)
    assert repository.get_import(source_id) is not None
    selections.replace_for_teacher_year(
        teacher_id, repository.get_import(source_id).academic_year.id, (),
        allow_limit_excess=True,
    )
    year_id = repository.get_import(source_id).academic_year.id
    assert selections.get_allow_limit_excess(teacher_id, year_id)
    service.delete_source(teacher_id, source_id)
    assert repository.get_import(source_id) is None
    assert service.get_profile(teacher_id).sources == ()
    assert repository.known_hashes() == set()
    assert not selections.get_allow_limit_excess(teacher_id, year_id)


def test_teacher_page_refreshes_after_import_and_saves_user_choices(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    database_path = tmp_path / "screen.db"
    upgrade_database(database_path)
    repository = WorkloadRepository(create_session_factory(create_sqlite_engine(database_path)))
    calculation = TeacherCalculationService(repository)
    factory = create_session_factory(create_sqlite_engine(database_path))
    selections = HourlySelectionRepository(factory)
    window = MainWindow(
        ImportWorkloadService(repository),
        TeacherSettingsService(repository),
        calculation,
        SelectionService(calculation, selections),
        MonthlyPlanningService(calculation, selections, MonthlyAllocationRepository(factory)),
        AvailabilitySettingsService(repository, ScheduleRepository(factory)),
        CalendarSettingsService(CalendarOverrideRepository(factory)),
    )
    qtbot.addWidget(window)
    window.show()
    window.tabs.setCurrentWidget(window.import_page)
    assert window.teacher_page.teacher_box.count() == 0

    window.import_page.load_files([synthetic_workbook])
    qtbot.mouseClick(window.import_page.confirm_button, Qt.MouseButton.LeftButton)
    page = window.teacher_page
    assert page.teacher_box.count() == 1
    assert page.teacher_box.currentText() == "Тестов Т.Т."
    assert page.year_box.currentText() == "2026-2027"
    assert page.rate_input.text() == ""
    assert page.sources_table.rowCount() == 1
    assert page.sources_table.cellWidget(0, 0).currentText() == "Не решено"

    window.tabs.setCurrentWidget(page)
    page.rate_input.setText("0,75")
    qtbot.mouseClick(page.confirm_rate_button, Qt.MouseButton.LeftButton)
    page.sources_table.cellWidget(0, 0).setCurrentIndex(1)
    qtbot.mouseClick(page.save_sources_button, Qt.MouseButton.LeftButton)
    profile = TeacherSettingsService(repository).get_profile(page.teacher_box.currentData())
    assert profile.teacher.effective_rate == Decimal("0.7500")
    assert profile.sources[0].source.include_in_fact is True


def test_teacher_page_rejects_non_numeric_rate(
    qtbot, tmp_path: Path, synthetic_workbook: Path, monkeypatch
) -> None:
    service, repository, teacher_id, _ = _saved_teacher(tmp_path, synthetic_workbook)
    page = TeacherPage(service)
    qtbot.addWidget(page)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: messages.append(message)
    )
    page.rate_input.setText("abc")
    qtbot.mouseClick(page.confirm_rate_button, Qt.MouseButton.LeftButton)
    assert messages == ["Введите ставку числом, например 0,5."]
    assert repository.list_teachers()[0].id == teacher_id
    assert repository.list_teachers()[0].effective_rate is None


def test_teacher_page_saves_personal_data(qtbot, tmp_path: Path, synthetic_workbook: Path) -> None:
    service, _, teacher_id, _ = _saved_teacher(tmp_path, synthetic_workbook)
    page = TeacherPage(service)
    qtbot.addWidget(page)
    page.personal_inputs["full_name"].setText("Тестов Тест Тестович")
    page.personal_inputs["birth_date"].setText("15.04.1980")
    page.personal_inputs["inn"].setText("123456789012")
    qtbot.mouseClick(page.save_personal_button, Qt.MouseButton.LeftButton)
    teacher = service.get_profile(teacher_id).teacher
    assert teacher.full_name == "Тестов Тест Тестович"
    assert teacher.birth_date == date(1980, 4, 15)
    assert teacher.inn == "123456789012"
    assert page.teacher_box.currentText() == teacher.full_name


def test_teacher_page_scrolls_as_one_form_on_small_window(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, _, _, _ = _saved_teacher(tmp_path, synthetic_workbook)
    page = TeacherPage(service)
    qtbot.addWidget(page)
    page.resize(900, 520)
    page.show()
    qtbot.waitExposed(page)

    scrollbar = page.scroll_area.verticalScrollBar()
    assert scrollbar.maximum() > 0
    assert page.personal_inputs["full_name"].isVisible()
    assert page.personal_inputs["inn"].isVisible()
    assert page.sources_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    page.scroll_area.ensureWidgetVisible(page.save_sources_button)
    assert scrollbar.value() > 0
    assert page.save_sources_button.isVisible()


def test_teacher_page_deletes_selected_source_after_confirmation(
    qtbot, tmp_path: Path, synthetic_workbook: Path, monkeypatch
) -> None:
    service, repository, _, source_id = _saved_teacher(tmp_path, synthetic_workbook)
    page = TeacherPage(service)
    qtbot.addWidget(page)
    page.sources_table.selectRow(0)
    assert page.delete_source_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    qtbot.mouseClick(page.delete_source_button, Qt.MouseButton.LeftButton)
    assert repository.get_import(source_id) is not None
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    qtbot.mouseClick(page.delete_source_button, Qt.MouseButton.LeftButton)
    assert repository.get_import(source_id) is None
    assert page.sources_table.rowCount() == 0
