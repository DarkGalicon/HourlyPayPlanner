from pathlib import Path

from hourly_pay.application.schedule_month import ScheduleMonth, ScheduleMonthService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.domain.errors import InvalidDocumentExportError
from hourly_pay.domain.models import AcademicYear, Teacher
from hourly_pay.exporters.hourly_docx import (
    DocxExportOptions,
    DocxExportResult,
    export_hourly_statement,
)


class StatementExportService:
    def __init__(
        self, schedules: ScheduleMonthService, teachers: TeacherSettingsService
    ) -> None:
        self._schedules = schedules
        self._teachers = teachers

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._schedules.list_teachers()

    def list_years(self, teacher_id: int) -> tuple[AcademicYear, ...]:
        return self._schedules.list_years(teacher_id)

    def available_months(self, teacher_id: int, academic_year_id: int) -> tuple[ScheduleMonth, ...]:
        return self._schedules.available_months(teacher_id, academic_year_id)

    def export(
        self,
        teacher_id: int,
        academic_year_id: int,
        year: int,
        month: int,
        template_path: Path,
        output_directory: Path,
        options: DocxExportOptions,
    ) -> DocxExportResult:
        planned = next(
            (
                entry for entry in self.available_months(teacher_id, academic_year_id)
                if (entry.year, entry.month) == (year, month)
            ),
            None,
        )
        if planned is None:
            raise InvalidDocumentExportError("Месяц не относится к выбранному помесячному плану.")
        self._schedules.validate_existing(teacher_id, academic_year_id, year, month)
        rows = self._schedules.list_lessons(teacher_id, year, month)
        if len(rows) != planned.lesson_count:
            raise InvalidDocumentExportError(
                "Количество занятий не совпадает с помесячным планом. Перегенерируйте месяц."
            )
        teacher = self._teachers.get_profile(teacher_id).teacher
        return export_hourly_statement(
            template_path,
            output_directory,
            teacher=teacher,
            lessons=tuple(row.lesson for row in rows),
            time_slots=self._schedules.list_time_slots(),
            year=year,
            month=month,
            options=options,
        )
