"""Application boundary for exporting the whole academic-year hourly plan."""

from collections.abc import Mapping
from pathlib import Path

from hourly_pay.application.monthly_planning import MonthlyPlanningService, MonthlyPlanningSnapshot
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.domain.models import AcademicYear, Teacher
from hourly_pay.exporters.distribution_xlsx import DistributionExportResult, export_distribution


class DistributionExportService:
    def __init__(
        self, planning: MonthlyPlanningService, teachers: TeacherSettingsService
    ) -> None:
        self._planning = planning
        self._teachers = teachers

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._planning.list_teachers()

    def list_years(self, teacher_id: int) -> tuple[AcademicYear, ...]:
        return self._planning.list_years(teacher_id)

    def load(self, teacher_id: int, academic_year_id: int) -> MonthlyPlanningSnapshot:
        return self._planning.load(teacher_id, academic_year_id)

    def export(
        self, teacher_id: int, academic_year_id: int, output_directory: Path,
        funding_by_selection: Mapping[int, str],
    ) -> DistributionExportResult:
        snapshot = self.load(teacher_id, academic_year_id)
        teacher = self._teachers.get_profile(teacher_id).teacher
        return export_distribution(
            output_directory,
            teacher=teacher,
            academic_year=snapshot.academic_year,
            rows=snapshot.rows,
            funding_by_selection=funding_by_selection,
        )
