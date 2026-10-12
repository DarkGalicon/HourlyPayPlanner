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
from hourly_pay.domain.errors import InvalidSelectionError
from hourly_pay.domain.models import MonthlyAllocation
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
from hourly_pay.ui.pages.selection_page import SelectionPage


def _setup(tmp_path: Path):
    database_path = tmp_path / "selection.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    imports = WorkloadRepository(factory)
    selections = HourlySelectionRepository(factory)
    calculations = TeacherCalculationService(imports)
    return imports, selections, MonthlyAllocationRepository(factory), SelectionService(
        calculations, selections
    )


def _confirmed_import(
    imports: WorkloadRepository, synthetic_workbook: Path, *, year_name: str | None = None
):
    result = NagrXlsxV1Importer().import_file(synthetic_workbook)
    if year_name is not None:
        result.academic_year.name = year_name
    saved = imports.save_import(result, allow_duplicate=year_name is not None)
    settings = TeacherSettingsService(imports)
    settings.confirm_effective_rate(saved.teacher_id, Decimal("0"))
    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: True})
    return saved


def test_selection_is_validated_and_saved_from_included_rows(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, _, service = _setup(tmp_path)
    saved = _confirmed_import(imports, synthetic_workbook)
    snapshot = service.load(saved.teacher_id, saved.academic_year_id)
    assert snapshot.calculation.values.hourly_limit == Decimal("2")
    assert len(snapshot.calculation.eligible_items) == 1
    item_id = snapshot.calculation.eligible_items[0].id
    assert item_id is not None

    with pytest.raises(InvalidSelectionError, match="доступно"):
        service.save(saved.teacher_id, saved.academic_year_id, {item_id: Decimal("4")})
    assert selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id) == ()

    plan = service.save(saved.teacher_id, saved.academic_year_id, {item_id: Decimal("2")})
    assert plan.selected_total == Decimal("2")
    assert service.load(saved.teacher_id, saved.academic_year_id).saved_hours == {
        item_id: Decimal("2")
    }


def test_limit_excess_permission_is_saved_for_teacher_year(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, _, _, service = _setup(tmp_path)
    saved = _confirmed_import(imports, synthetic_workbook)
    TeacherSettingsService(imports).confirm_effective_rate(saved.teacher_id, Decimal("1"))
    snapshot = service.load(saved.teacher_id, saved.academic_year_id)
    assert snapshot.calculation.values.hourly_limit == Decimal("0")
    assert snapshot.allow_limit_excess is False
    item_id = snapshot.calculation.eligible_items[0].id
    assert item_id is not None

    with pytest.raises(InvalidSelectionError, match="превышает лимит"):
        service.save(saved.teacher_id, saved.academic_year_id, {item_id: Decimal("2")})
    service.save(
        saved.teacher_id, saved.academic_year_id, {item_id: Decimal("2")},
        allow_limit_excess=True,
    )
    assert service.load(saved.teacher_id, saved.academic_year_id).allow_limit_excess
    with pytest.raises(InvalidSelectionError, match="превышает лимит"):
        service.save(saved.teacher_id, saved.academic_year_id, {item_id: Decimal("2")})
    assert service.load(saved.teacher_id, saved.academic_year_id).allow_limit_excess


def test_selection_page_checkbox_allows_calculated_limit_excess(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, _, service = _setup(tmp_path)
    saved = _confirmed_import(imports, synthetic_workbook)
    TeacherSettingsService(imports).confirm_effective_rate(saved.teacher_id, Decimal("1"))
    page = SelectionPage(service)
    qtbot.addWidget(page)
    page.table.cellWidget(0, 0).setChecked(True)
    assert not page.save_button.isEnabled()
    page.allow_excess_check.setChecked(True)
    assert page.save_button.isEnabled()
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id)
    assert page.allow_excess_check.isChecked()


def test_save_is_scoped_to_year_and_preserves_unchanged_selection_ids(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, allocations, service = _setup(tmp_path)
    first = _confirmed_import(imports, synthetic_workbook)
    second = _confirmed_import(imports, synthetic_workbook, year_name="2027-2028")
    first_item = service.load(
        first.teacher_id, first.academic_year_id
    ).calculation.eligible_items[0]
    second_item = service.load(
        second.teacher_id, second.academic_year_id
    ).calculation.eligible_items[0]
    assert first_item.id is not None and second_item.id is not None
    service.save(first.teacher_id, first.academic_year_id, {first_item.id: Decimal("2")})
    service.save(second.teacher_id, second.academic_year_id, {second_item.id: Decimal("2")})
    first_selection = selections.list_for_teacher_year(first.teacher_id, first.academic_year_id)[0]
    assert first_selection.id is not None
    allocations.replace_for_selection(
        first_selection.id,
        (MonthlyAllocation(first_selection.id, 9, 2026, Decimal("2")),),
    )

    service.save(first.teacher_id, first.academic_year_id, {first_item.id: Decimal("2")})
    assert selections.list_for_teacher_year(first.teacher_id, first.academic_year_id)[0].id == (
        first_selection.id
    )
    with pytest.raises(InvalidSelectionError, match="помесячное распределение"):
        service.save(first.teacher_id, first.academic_year_id, {})
    assert service.load(first.teacher_id, first.academic_year_id).saved_hours == {
        first_item.id: Decimal("2")
    }
    assert service.load(second.teacher_id, second.academic_year_id).saved_hours == {
        second_item.id: Decimal("2")
    }


def test_excluded_source_selection_is_visible_and_can_be_cleared(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, _, service = _setup(tmp_path)
    saved = _confirmed_import(imports, synthetic_workbook)
    item_id = service.load(
        saved.teacher_id, saved.academic_year_id
    ).calculation.eligible_items[0].id
    assert item_id is not None
    service.save(saved.teacher_id, saved.academic_year_id, {item_id: Decimal("2")})
    TeacherSettingsService(imports).save_source_inclusions(
        saved.teacher_id, {saved.source_id: False}
    )
    snapshot = service.load(saved.teacher_id, saved.academic_year_id)
    assert snapshot.calculation.eligible_items == ()
    assert snapshot.excluded_saved_count == 1
    service.save(saved.teacher_id, saved.academic_year_id, {})
    assert selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id) == ()


def test_selection_page_filters_and_persists_manual_choice(
    qtbot, tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, _, service = _setup(tmp_path)
    saved = _confirmed_import(imports, synthetic_workbook)
    calculations = TeacherCalculationService(imports)
    window = MainWindow(
        ImportWorkloadService(imports),
        TeacherSettingsService(imports),
        calculations,
        service,
        MonthlyPlanningService(
            calculations,
            selections,
            MonthlyAllocationRepository(
                create_session_factory(create_sqlite_engine(tmp_path / "selection.db"))
            ),
        ),
        AvailabilitySettingsService(
            imports,
            ScheduleRepository(
                create_session_factory(create_sqlite_engine(tmp_path / "selection.db"))
            ),
        ),
        CalendarSettingsService(
            CalendarOverrideRepository(
                create_session_factory(create_sqlite_engine(tmp_path / "selection.db"))
            )
        ),
    )
    qtbot.addWidget(window)
    window.show()
    page = window.selection_page
    window.tabs.setCurrentWidget(window.plan_tabs)
    window.plan_tabs.setCurrentWidget(page)
    assert page.table.rowCount() == 1
    assert "Лимит: 2" in page.summary_label.text()

    page.discipline_filter.setText("несуществующая")
    assert page.table.isRowHidden(0)
    page.discipline_filter.clear()
    assert not page.table.isRowHidden(0)
    page.table.cellWidget(0, 0).setChecked(True)
    assert page.table.cellWidget(0, 8).value() == 2
    assert "Выбрано: 2" in page.summary_label.text()
    page.table.cellWidget(0, 8).setValue(1)
    assert not page.save_button.isEnabled()
    page.table.cellWidget(0, 8).setValue(2)
    page.table.cellWidget(0, 9).setChecked(True)
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    saved_selection = selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id)
    assert len(saved_selection) == 1
    assert saved_selection[0].prefer_evening
    page.refresh()
    assert page.table.cellWidget(0, 0).isChecked()
    assert page.table.cellWidget(0, 8).value() == 2
    assert page.table.cellWidget(0, 9).isChecked()

    TeacherSettingsService(imports).save_source_inclusions(
        saved.teacher_id, {saved.source_id: False}
    )
    page.refresh()
    assert page.table.rowCount() == 0
    assert page.save_button.isEnabled()
    assert "исключённых источников" in page.status_label.text()
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id) == ()
