from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from hourly_pay.app import create_main_window
from hourly_pay.application.availability_settings import AvailabilitySettingsService
from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.application.import_workload import ImportWorkloadService
from hourly_pay.application.monthly_planning import MonthlyPlanningService
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.repositories import (
    CalendarOverrideRepository,
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    ScheduleRepository,
    WorkloadRepository,
)
from hourly_pay.ui.main_window import NAVIGATION_TITLES, MainWindow
from hourly_pay.ui.pages.import_page import ImportPage


def _service(tmp_path: Path) -> tuple[ImportWorkloadService, WorkloadRepository]:
    database_path = tmp_path / "ui.db"
    upgrade_database(database_path)
    repository = WorkloadRepository(
        create_session_factory(create_sqlite_engine(database_path))
    )
    return ImportWorkloadService(repository), repository


def test_main_window_exposes_documented_navigation(qtbot, tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    calculation = TeacherCalculationService(repository)
    factory = create_session_factory(create_sqlite_engine(tmp_path / "ui.db"))
    selections = HourlySelectionRepository(factory)
    window = MainWindow(
        service,
        TeacherSettingsService(repository),
        calculation,
        SelectionService(calculation, selections),
        MonthlyPlanningService(calculation, selections, MonthlyAllocationRepository(factory)),
        AvailabilitySettingsService(repository, ScheduleRepository(factory)),
        CalendarSettingsService(CalendarOverrideRepository(factory)),
    )
    qtbot.addWidget(window)
    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == list(
        NAVIGATION_TITLES
    )
    assert window.tabs.currentWidget() is window.import_page
    assert window.tabs.widget(0) is window.import_page
    assert window.header_title.text() == "Импорт"
    assert window.step_badge.text() == "ШАГ 01 / 06"
    qtbot.mouseClick(window.next_button, Qt.MouseButton.LeftButton)
    assert window.tabs.currentWidget() is window.teacher_page
    assert window.header_description.text().startswith("Подтвердите ставку")


def test_documents_form_keeps_readable_fields_in_small_window(qtbot, tmp_path: Path) -> None:
    window = create_main_window(tmp_path / "appearance.db")
    qtbot.addWidget(window)
    window.resize(1030, 680)
    window.show()
    window.tabs.setCurrentWidget(window.documents_tabs)
    window.documents_tabs.setCurrentWidget(window.documents_page)
    qtbot.waitExposed(window)

    assert window.documents_page.template_edit.height() >= 30
    assert window.documents_page.output_edit.height() >= 30
    assert window.documents_page.export_button.isVisible()
    assert window.step_badge.text() == "ШАГ 06 / 06"
    assert not window.next_button.isVisible()
    window.database_engine.dispose()


def test_import_preview_and_confirmation_flow(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository = _service(tmp_path)
    page = ImportPage(service)
    qtbot.addWidget(page)

    page.load_files([synthetic_workbook])
    assert page.model.rowCount() == 1
    assert page.model.data(page.model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "Тестов Т.Т."
    assert page.model.data(page.model.index(0, 3), Qt.ItemDataRole.DisplayRole) == "0.5"
    assert "строка 5" in page.warning_details.toPlainText()
    assert "Неизвестный вид контроля" in page.warning_details.toPlainText()
    assert repository.known_hashes() == set()
    assert page.confirm_button.isEnabled()

    qtbot.mouseClick(page.confirm_button, Qt.MouseButton.LeftButton)
    assert page.model.rowCount() == 0
    assert repository.known_hashes()
    assert page.status_label.text() == "Импортировано файлов: 1."


def test_duplicate_preview_disables_confirmation(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository = _service(tmp_path)
    first = service.preview_files([synthetic_workbook]).previews[0]
    repository.save_import(first.result)
    page = ImportPage(service)
    qtbot.addWidget(page)

    page.load_files([synthetic_workbook])
    assert not page.confirm_button.isEnabled()
    assert "Повторно" in page.status_label.text()


def test_old_parser_import_can_be_reimported_as_new_version(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository = _service(tmp_path)
    old_result = service.preview_files([synthetic_workbook]).previews[0].result
    old_result.source.parser_version = "nagr_xlsx_v1"
    repository.save_import(old_result)
    page = ImportPage(service)
    qtbot.addWidget(page)

    page.load_files([synthetic_workbook])
    assert page.model.previews[0].is_upgrade
    assert not page.model.previews[0].is_duplicate
    assert page.confirm_button.isEnabled()
    assert "старой версии" in page.status_label.text()

    qtbot.mouseClick(page.confirm_button, Qt.MouseButton.LeftButton)
    assert repository.source_count() == 2
    assert repository.parser_versions_by_hash()[old_result.source.file_sha256] == {
        "nagr_xlsx_v1",
        "nagr_xlsx_v2",
    }

    page.load_files([synthetic_workbook])
    assert not page.confirm_button.isEnabled()


def test_duplicate_files_in_same_batch_cannot_be_saved(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, repository = _service(tmp_path)
    page = ImportPage(service)
    qtbot.addWidget(page)

    page.load_files([synthetic_workbook, synthetic_workbook])
    assert page.model.rowCount() == 2
    assert not page.confirm_button.isEnabled()
    assert repository.known_hashes() == set()


def test_preview_keeps_integer_trailing_zeros(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    service, _ = _service(tmp_path)
    page = ImportPage(service)
    qtbot.addWidget(page)
    page.load_files([synthetic_workbook])
    page.model.previews[0].result.source.reported_total_hours = Decimal("10")
    assert page.model.data(page.model.index(0, 4), Qt.ItemDataRole.DisplayRole) == "10"


def test_bad_file_shows_controlled_message(qtbot, tmp_path: Path, monkeypatch) -> None:
    service, _ = _service(tmp_path)
    page = ImportPage(service)
    qtbot.addWidget(page)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(message),
    )
    invalid = tmp_path / "broken.xlsx"
    invalid.write_text("not an xlsx", encoding="utf-8")

    page.load_files([invalid])
    assert page.model.rowCount() == 0
    assert not page.confirm_button.isEnabled()
    assert messages and "Формат файла не распознан" in messages[0]
