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
from hourly_pay.application.monthly_planning import MonthlyPlanningService, MonthlyRowDraft
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.domain.enums import SessionPeriod, StudyForm
from hourly_pay.domain.errors import InvalidMonthlyAllocationError
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.orm_models import GenerationBatchRecord, LessonRecord
from hourly_pay.persistence.repositories import (
    CalendarOverrideRepository,
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    ScheduleRepository,
    WorkloadRepository,
)
from hourly_pay.ui.main_window import MainWindow


def _services(tmp_path: Path):
    database_path = tmp_path / "monthly.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    imports = WorkloadRepository(factory)
    selections = HourlySelectionRepository(factory)
    allocations = MonthlyAllocationRepository(factory)
    calculations = TeacherCalculationService(imports)
    return imports, selections, allocations, calculations, MonthlyPlanningService(
        calculations, selections, allocations
    )


def _saved_selection(imports, selections, calculations, synthetic_workbook: Path, *, zaoc=False):
    result = NagrXlsxV1Importer().import_file(synthetic_workbook)
    if zaoc:
        item = next(item for item in result.items if not item.is_idpo)
        item.semester = None
        item.study_form = StudyForm.CORRESPONDENCE
        item.session_period = SessionPeriod.WINTER
    saved = imports.save_import(result)
    settings = TeacherSettingsService(imports)
    settings.confirm_effective_rate(saved.teacher_id, Decimal("0"))
    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: True})
    selection_service = SelectionService(calculations, selections)
    item = selection_service.load(
        saved.teacher_id, saved.academic_year_id
    ).calculation.eligible_items[0]
    assert item.id is not None
    selection_service.save(saved.teacher_id, saved.academic_year_id, {item.id: Decimal("2")})
    return saved


def test_monthly_plan_requires_exact_sum_and_persists_academic_year(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, allocations, calculations, service = _services(tmp_path)
    saved = _saved_selection(imports, selections, calculations, synthetic_workbook)
    row = service.load(saved.teacher_id, saved.academic_year_id).rows[0]
    assert row.selection.id is not None

    with pytest.raises(InvalidMonthlyAllocationError, match="Сумма по месяцам"):
        service.save(
            saved.teacher_id,
            saved.academic_year_id,
            {row.selection.id: MonthlyRowDraft({})},
        )
    with pytest.raises(InvalidMonthlyAllocationError, match="недоступен"):
        service.save(
            saved.teacher_id,
            saved.academic_year_id,
            {row.selection.id: MonthlyRowDraft({2: Decimal("2")})},
        )
    assert allocations.list_for_selection(row.selection.id) == ()

    service.save(
        saved.teacher_id,
        saved.academic_year_id,
        {row.selection.id: MonthlyRowDraft({9: Decimal("2")})},
    )
    restored = service.load(saved.teacher_id, saved.academic_year_id).rows[0]
    assert [(entry.month, entry.year, entry.hours) for entry in restored.allocations] == [
        (9, 2026, Decimal("2"))
    ]


def test_correspondence_requires_explicit_semester_and_january_choice(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, allocations, calculations, service = _services(tmp_path)
    saved = _saved_selection(imports, selections, calculations, synthetic_workbook, zaoc=True)
    row = service.load(saved.teacher_id, saved.academic_year_id).rows[0]
    assert row.item.semester is None
    assert row.selection.id is not None

    with pytest.raises(InvalidMonthlyAllocationError, match="semester_override"):
        service.save(
            saved.teacher_id,
            saved.academic_year_id,
            {row.selection.id: MonthlyRowDraft({2: Decimal("2")})},
        )
    with pytest.raises(InvalidMonthlyAllocationError, match="недоступен"):
        service.save(
            saved.teacher_id,
            saved.academic_year_id,
            {row.selection.id: MonthlyRowDraft({1: Decimal("2")}, semester_override=2)},
        )
    service.save(
        saved.teacher_id,
        saved.academic_year_id,
        {
            row.selection.id: MonthlyRowDraft(
                {1: Decimal("2")}, include_january=True, semester_override=2
            )
        },
    )
    stored = allocations.list_for_selection(row.selection.id)
    assert [(entry.month, entry.year) for entry in stored] == [(1, 2027)]


def test_monthly_resave_preserves_lessons_and_blocks_reallocation(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    imports, selections, allocations, calculations, service = _services(tmp_path)
    saved = _saved_selection(imports, selections, calculations, synthetic_workbook)
    row = service.load(saved.teacher_id, saved.academic_year_id).rows[0]
    assert row.selection.id is not None
    september = MonthlyRowDraft({9: Decimal("2")})
    service.save(saved.teacher_id, saved.academic_year_id, {row.selection.id: september})
    allocation = allocations.list_for_selection(row.selection.id)[0]
    assert allocation.id is not None
    factory = create_session_factory(create_sqlite_engine(tmp_path / "monthly.db"))
    with factory.begin() as session:
        batch = GenerationBatchRecord(teacher_id=saved.teacher_id, year=2026, month=9)
        session.add(batch)
        session.flush()
        session.add(
            LessonRecord(
                teacher_id=saved.teacher_id,
                monthly_allocation_id=allocation.id,
                lesson_date=date(2026, 9, 1),
                time_slot_id=1,
                group_name="ГРУППА",
                discipline="Дисциплина",
                work_type="LECTURE",
                hours=Decimal("2"),
                generation_batch_id=batch.id,
            )
        )

    service.save(saved.teacher_id, saved.academic_year_id, {row.selection.id: september})
    assert allocations.list_for_selection(row.selection.id)[0].id == allocation.id
    with pytest.raises(InvalidMonthlyAllocationError, match="уже созданы занятия"):
        service.save(
            saved.teacher_id,
            saved.academic_year_id,
            {row.selection.id: MonthlyRowDraft({10: Decimal("2")})},
        )
    assert allocations.list_for_selection(row.selection.id)[0].month == 9
    with pytest.raises(InvalidMonthlyAllocationError, match="уже созданы занятия"):
        service.clear(saved.teacher_id, saved.academic_year_id)
    assert allocations.list_for_selection(row.selection.id)[0].id == allocation.id


def test_monthly_page_saves_and_restores_manual_grid(
    qtbot, tmp_path: Path, synthetic_workbook: Path, monkeypatch
) -> None:
    imports, selections, allocations, calculations, service = _services(tmp_path)
    saved = _saved_selection(imports, selections, calculations, synthetic_workbook, zaoc=True)
    window = MainWindow(
        ImportWorkloadService(imports),
        TeacherSettingsService(imports),
        calculations,
        SelectionService(calculations, selections),
        service,
        AvailabilitySettingsService(
            imports,
            ScheduleRepository(
                create_session_factory(create_sqlite_engine(tmp_path / "monthly.db"))
            ),
        ),
        CalendarSettingsService(
            CalendarOverrideRepository(
                create_session_factory(create_sqlite_engine(tmp_path / "monthly.db"))
            )
        ),
    )
    qtbot.addWidget(window)
    window.show()
    window.tabs.setCurrentWidget(window.plan_tabs)
    page = window.monthly_page
    window.plan_tabs.setCurrentWidget(page)
    assert page.table.rowCount() == 1
    assert page.table.cellWidget(0, 3).currentData() is None
    assert not page.save_button.isEnabled()

    page.table.cellWidget(0, 3).setCurrentIndex(2)
    assert not page.table.cellWidget(0, 10).isEnabled()
    page.table.cellWidget(0, 4).setChecked(True)
    assert page.table.cellWidget(0, 10).isEnabled()
    page.table.cellWidget(0, 10).setValue(2)
    assert page.table.cellWidget(0, 15).text() == "0"
    assert page.save_button.isEnabled()
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert "сохранён" in page.status_label.text()
    assert page.table.cellWidget(0, 3).currentData() == 2
    assert page.table.cellWidget(0, 4).isChecked()
    assert page.table.cellWidget(0, 10).value() == 2
    selection_id = selections.list_for_teacher_year(saved.teacher_id, saved.academic_year_id)[0].id
    assert selection_id is not None
    assert allocations.list_for_selection(selection_id)[0].year == 2027
    page.table.cellWidget(0, 4).setChecked(False)
    assert page.table.cellWidget(0, 10).isEnabled()
    assert not page.save_button.isEnabled()
    page.table.cellWidget(0, 10).setValue(0)
    page.table.cellWidget(0, 11).setValue(2)
    assert page.save_button.isEnabled()
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert allocations.list_for_selection(selection_id)[0].month == 2
    assert page.clear_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    qtbot.mouseClick(page.clear_button, Qt.MouseButton.LeftButton)
    assert allocations.list_for_selection(selection_id) == ()
    assert "очищен" in page.status_label.text()
