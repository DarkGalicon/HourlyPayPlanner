from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Protocol

from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.application.monthly_planning import MonthlyPlanningService
from hourly_pay.application.semester_settings import SemesterSettingsService, semester_for_month
from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import AcademicYear, Lesson, Teacher, TimeSlot
from hourly_pay.scheduler.availability import TeacherAvailability
from hourly_pay.scheduler.generator import (
    ScheduledAllocation,
    ScheduleGenerationResult,
    generate_schedule,
    validate_lessons,
)


class ScheduleStore(Protocol):
    def get_availability(self, teacher_id: int) -> TeacherAvailability: ...

    def list_time_slots(self) -> tuple[TimeSlot, ...]: ...

    def list_month_lessons(
        self, *, teacher_id: int, year: int, month: int
    ) -> tuple[Lesson, ...]: ...

    def replace_month_schedule(
        self, result: ScheduleGenerationResult, *, allow_replace_manual: bool = False
    ) -> int: ...

    def clear_month_schedule(self, *, teacher_id: int, year: int, month: int) -> int: ...

    def move_lesson(
        self, *, teacher_id: int, year: int, month: int,
        lesson_id: int, lesson_date: date, time_slot_id: int,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ScheduleMonth:
    year: int
    month: int
    lesson_count: int


@dataclass(frozen=True, slots=True)
class ScheduleLessonRow:
    lesson: Lesson
    time_slot: TimeSlot


class ScheduleMonthService:
    def __init__(
        self,
        planning: MonthlyPlanningService,
        schedules: ScheduleStore,
        calendar: CalendarSettingsService,
        semester_settings: SemesterSettingsService | None = None,
    ) -> None:
        self._planning = planning
        self._schedules = schedules
        self._calendar = calendar
        self._semester_settings = semester_settings

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._planning.list_teachers()

    def list_years(self, teacher_id: int) -> tuple[AcademicYear, ...]:
        return self._planning.list_years(teacher_id)

    def list_time_slots(self) -> tuple[TimeSlot, ...]:
        return self._schedules.list_time_slots()

    def available_months(self, teacher_id: int, academic_year_id: int) -> tuple[ScheduleMonth, ...]:
        snapshot = self._planning.load(teacher_id, academic_year_id)
        totals: dict[tuple[int, int], int] = {}
        for row in snapshot.rows:
            for entry in row.allocations:
                if entry.hours > 0:
                    key = entry.year, entry.month
                    totals[key] = totals.get(key, 0) + int(entry.hours / 2)
        return tuple(
            ScheduleMonth(year, month, count)
            for (year, month), count in sorted(totals.items())
        )

    def list_lessons(self, teacher_id: int, year: int, month: int) -> tuple[ScheduleLessonRow, ...]:
        slots = {slot.id: slot for slot in self._schedules.list_time_slots()}
        lessons = self._schedules.list_month_lessons(
            teacher_id=teacher_id, year=year, month=month
        )
        if any(lesson.time_slot_id not in slots for lesson in lessons):
            raise InvalidScheduleError("Расписание содержит неизвестный временной слот.")
        return tuple(ScheduleLessonRow(lesson, slots[lesson.time_slot_id]) for lesson in lessons)

    def has_manual_changes(self, teacher_id: int, year: int, month: int) -> bool:
        return any(
            row.lesson.manual_override
            for row in self.list_lessons(teacher_id, year, month)
        )

    def validate_existing(
        self, teacher_id: int, academic_year_id: int, year: int, month: int
    ) -> None:
        rows = self.list_lessons(teacher_id, year, month)
        if not rows:
            raise InvalidScheduleError("Для выбранного месяца нет сохранённых занятий.")
        validate_lessons(
            (row.lesson for row in rows),
            teacher_id=teacher_id,
            availability=self._schedules.get_availability(teacher_id),
            calendar_policy=self._calendar.policy_for_years([year]),
            time_slots=self._schedules.list_time_slots(),
            practice_lab_start_date=self._practice_start(academic_year_id, month),
            allocations=self._allocation_details(teacher_id, academic_year_id),
        )

    def _allocation_details(
        self, teacher_id: int, academic_year_id: int
    ) -> dict[int, ScheduledAllocation]:
        snapshot = self._planning.load(teacher_id, academic_year_id)
        return {
            allocation.id: ScheduledAllocation(
                allocation=allocation,
                group_name=row.item.group_name or "",
                discipline=row.item.discipline or "",
                work_type=row.item.work_type,
                study_form=row.item.study_form,
                course=row.item.course,
                prefer_evening=row.selection.prefer_evening,
            )
            for row in snapshot.rows
            for allocation in row.allocations
            if allocation.id is not None
        }

    def _practice_start(self, academic_year_id: int, month: int) -> date | None:
        if self._semester_settings is None:
            return None
        return self._semester_settings.get(academic_year_id, semester_for_month(month))

    def clear_month(
        self, teacher_id: int, academic_year_id: int, year: int, month: int
    ) -> int:
        if not any(
            entry.year == year and entry.month == month
            for entry in self.available_months(teacher_id, academic_year_id)
        ):
            raise InvalidScheduleError("Месяц не относится к выбранному помесячному плану.")
        return self._schedules.clear_month_schedule(
            teacher_id=teacher_id, year=year, month=month
        )

    def move_lesson(
        self, teacher_id: int, academic_year_id: int, year: int, month: int,
        lesson_id: int, lesson_date: date, time_slot_id: int,
    ) -> bool:
        if not any(
            entry.year == year and entry.month == month
            for entry in self.available_months(teacher_id, academic_year_id)
        ):
            raise InvalidScheduleError("Месяц не относится к выбранному помесячному плану.")
        if (lesson_date.year, lesson_date.month) != (year, month):
            raise InvalidScheduleError("Занятие можно перенести только внутри выбранного месяца.")
        lessons = self._schedules.list_month_lessons(
            teacher_id=teacher_id, year=year, month=month
        )
        original = next((lesson for lesson in lessons if lesson.id == lesson_id), None)
        if original is None:
            raise InvalidScheduleError("Занятие не найдено в выбранном месяце.")
        if (original.lesson_date, original.time_slot_id) == (lesson_date, time_slot_id):
            return False
        proposed = tuple(
            replace(
                lesson, lesson_date=lesson_date, time_slot_id=time_slot_id,
                manual_override=True,
            ) if lesson.id == lesson_id else lesson
            for lesson in lessons
        )
        validate_lessons(
            proposed,
            teacher_id=teacher_id,
            availability=self._schedules.get_availability(teacher_id),
            calendar_policy=self._calendar.policy_for_years([year]),
            time_slots=self._schedules.list_time_slots(),
            practice_lab_start_date=self._practice_start(academic_year_id, month),
            allocations=self._allocation_details(teacher_id, academic_year_id),
        )
        self._schedules.move_lesson(
            teacher_id=teacher_id, year=year, month=month,
            lesson_id=lesson_id, lesson_date=lesson_date, time_slot_id=time_slot_id,
        )
        return True

    def generate(
        self,
        teacher_id: int,
        academic_year_id: int,
        year: int,
        month: int,
        *,
        replace_existing: bool = False,
        allow_replace_manual: bool = False,
        seed: int | None = None,
    ) -> ScheduleGenerationResult:
        snapshot = self._planning.load(teacher_id, academic_year_id)
        if not snapshot.rows:
            raise InvalidScheduleError("Сначала выберите и распределите нагрузку по месяцам.")
        incomplete = [
            row
            for row in snapshot.rows
            if sum((entry.hours for entry in row.allocations), start=Decimal("0"))
            != row.selection.selected_hours
        ]
        if incomplete:
            raise InvalidScheduleError(
                "Помесячный план заполнен не полностью. Завершите распределение выбранных часов."
            )

        scheduled: list[ScheduledAllocation] = []
        for row in snapshot.rows:
            for allocation in row.allocations:
                if (allocation.year, allocation.month) != (year, month) or allocation.hours <= 0:
                    continue
                if not row.item.group_name or not row.item.discipline:
                    raise InvalidScheduleError(
                        "У выбранной строки нагрузки нет группы или дисциплины. "
                        f"Проверьте строку {row.item.source_row_number} импортированного файла."
                    )
                scheduled.append(
                    ScheduledAllocation(
                        allocation=allocation,
                        group_name=row.item.group_name,
                        discipline=row.item.discipline,
                        work_type=row.item.work_type,
                        study_form=row.item.study_form,
                        course=row.item.course,
                        prefer_evening=row.selection.prefer_evening,
                    )
                )
        if not scheduled:
            raise InvalidScheduleError("В выбранном месяце нет распределённых часов.")

        existing = self._schedules.list_month_lessons(
            teacher_id=teacher_id, year=year, month=month
        )
        if existing and not replace_existing:
            raise InvalidScheduleError(
                "Расписание месяца уже существует. Используйте «Перегенерировать»."
            )
        valid_allocation_ids = {entry.allocation.id for entry in scheduled}
        if any(lesson.monthly_allocation_id not in valid_allocation_ids for lesson in existing):
            raise InvalidScheduleError(
                "Существующее расписание содержит нагрузку вне текущего плана. "
                "Проверьте выбранные источники и распределение."
            )

        result = generate_schedule(
            teacher_id=teacher_id,
            year=year,
            month=month,
            allocations=scheduled,
            availability=self._schedules.get_availability(teacher_id),
            calendar_policy=self._calendar.policy_for_years([year]),
            time_slots=self._schedules.list_time_slots(),
            seed=seed,
            practice_lab_start_date=self._practice_start(academic_year_id, month),
        )
        self._schedules.replace_month_schedule(
            result, allow_replace_manual=allow_replace_manual
        )
        return result
