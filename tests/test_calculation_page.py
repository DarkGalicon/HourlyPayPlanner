from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from hourly_pay.application.availability_settings import AvailabilitySettingsService
from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.application.import_workload import ImportWorkloadService
from hourly_pay.application.monthly_planning import MonthlyPlanningService
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.domain.errors import InvalidCalculationError
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


def _services(
    tmp_path: Path,
) -> tuple[WorkloadRepository, TeacherSettingsService, TeacherCalculationService]:
    database_path = tmp_path / "calculation.db"
    upgrade_database(database_path)
    repository = WorkloadRepository(create_session_factory(create_sqlite_engine(database_path)))
    return repository, TeacherSettingsService(repository), TeacherCalculationService(repository)


def test_calculation_requires_confirmed_rate_and_source_choice(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    repository, settings, calculations = _services(tmp_path)
    saved = repository.save_import(NagrXlsxV1Importer().import_file(synthetic_workbook))
    year_id = calculations.list_years(saved.teacher_id)[0].id
    assert year_id is not None

    with pytest.raises(InvalidCalculationError, match="Подтвердите эффективную ставку"):
        calculations.calculate(saved.teacher_id, year_id)

    settings.confirm_effective_rate(saved.teacher_id, Decimal("0"))
    with pytest.raises(InvalidCalculationError, match="Для каждого источника выберите"):
        calculations.calculate(saved.teacher_id, year_id)

    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: True})
    result = calculations.calculate(saved.teacher_id, year_id)
    assert result.included_source_count == 1
    assert result.values.fact_hours == Decimal("8")
    assert result.values.idpo_hours == Decimal("6")
    assert result.values.eligible_auditory_hours == Decimal("2")
    assert result.values.hourly_limit == Decimal("2")
    assert any(
        warning.sheet_name == "AutumnOch" and warning.row_number == 5
        for warning in result.warnings
    )
    assert any(warning.row_items for warning in result.warnings)

    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: False})
    excluded = calculations.calculate(saved.teacher_id, year_id)
    assert excluded.included_source_count == 0
    assert excluded.values.fact_hours == Decimal("0")
    assert excluded.values.hourly_limit == Decimal("0")
    assert excluded.warnings == ()


def test_calculation_page_refreshes_after_teacher_settings_are_saved(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    repository, settings, calculations = _services(tmp_path)
    factory = create_session_factory(create_sqlite_engine(tmp_path / "calculation.db"))
    selections = HourlySelectionRepository(factory)
    window = MainWindow(
        ImportWorkloadService(repository),
        settings,
        calculations,
        SelectionService(calculations, selections),
        MonthlyPlanningService(calculations, selections, MonthlyAllocationRepository(factory)),
        AvailabilitySettingsService(repository, ScheduleRepository(factory)),
        CalendarSettingsService(CalendarOverrideRepository(factory)),
    )
    qtbot.addWidget(window)
    window.show()

    window.import_page.load_files([synthetic_workbook])
    qtbot.mouseClick(window.import_page.confirm_button, Qt.MouseButton.LeftButton)
    page = window.calculation_page
    assert page.teacher_box.currentText() == "Тестов Т.Т."
    assert "Подтвердите эффективную ставку" in page.status_label.text()

    window.tabs.setCurrentWidget(window.teacher_page)
    teacher_page = window.teacher_page
    teacher_page.rate_input.setText("0")
    qtbot.mouseClick(teacher_page.confirm_rate_button, Qt.MouseButton.LeftButton)
    assert "Для каждого источника выберите" in page.status_label.text()
    teacher_page.sources_table.cellWidget(0, 0).setCurrentIndex(1)
    qtbot.mouseClick(teacher_page.save_sources_button, Qt.MouseButton.LeftButton)

    window.tabs.setCurrentWidget(page)
    assert page.value_labels["fact_hours"].text() == "8"
    assert page.value_labels["idpo_hours"].text() == "6"
    assert page.value_labels["hourly_limit"].text() == "2"
    assert page.warning_table.rowCount() > 0
    page._show_warning(0, 0)
    assert "synthetic.xlsx" in page.warning_details.toPlainText()
    assert "AutumnOch" in page.warning_details.toPlainText()


def test_calculation_rejects_included_legacy_import(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    repository, settings, calculations = _services(tmp_path)
    old_result = NagrXlsxV1Importer().import_file(synthetic_workbook)
    old_result.source.parser_version = "nagr_xlsx_v1"
    saved = repository.save_import(old_result)
    settings.confirm_effective_rate(saved.teacher_id, Decimal("1"))
    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: True})

    with pytest.raises(InvalidCalculationError, match="Импортируйте исходные XLSX заново"):
        calculations.calculate(saved.teacher_id, saved.academic_year_id)
