from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.application.distribution_export import DistributionExportService
from hourly_pay.application.monthly_planning import MonthlyPlanningService, MonthlyRowDraft
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import create_session_factory, create_sqlite_engine, upgrade_database
from hourly_pay.persistence.repositories import (
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    WorkloadRepository,
)


def test_export_uses_saved_monthly_plan_not_generated_lessons(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    database_path = tmp_path / "distribution.db"
    upgrade_database(database_path)
    factory = create_session_factory(create_sqlite_engine(database_path))
    imports = WorkloadRepository(factory)
    saved = imports.save_import(NagrXlsxV1Importer().import_file(synthetic_workbook))
    settings = TeacherSettingsService(imports)
    settings.confirm_effective_rate(saved.teacher_id, Decimal("0"))
    settings.save_source_inclusions(saved.teacher_id, {saved.source_id: True})
    calculation = TeacherCalculationService(imports)
    selections = HourlySelectionRepository(factory)
    selection_service = SelectionService(calculation, selections)
    item = selection_service.load(
        saved.teacher_id, saved.academic_year_id
    ).calculation.eligible_items[0]
    assert item.id is not None
    selection_service.save(
        saved.teacher_id, saved.academic_year_id, {item.id: Decimal("2")}
    )
    selection_id = selections.list_for_teacher_year(
        saved.teacher_id, saved.academic_year_id
    )[0].id
    assert selection_id is not None
    planning = MonthlyPlanningService(
        calculation, selections, MonthlyAllocationRepository(factory)
    )
    planning.save(
        saved.teacher_id, saved.academic_year_id,
        {selection_id: MonthlyRowDraft({9: Decimal("2")})},
    )
    service = DistributionExportService(planning, settings)
    result = service.export(
        saved.teacher_id, saved.academic_year_id, tmp_path / "out",
        {selection_id: "commercial"},
    )
    sheet = load_workbook(result.output_path).active
    assert sheet["H11"].value == 2
    assert sheet["G11"].value is None
    assert result.hours_sum == Decimal("2")
