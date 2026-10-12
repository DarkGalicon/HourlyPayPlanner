import calendar
import random
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from hourly_pay.config.defaults import DEFAULT_TIME_SLOTS
from hourly_pay.domain.enums import StudyForm, WorkType
from hourly_pay.domain.errors import InvalidScheduleError, ScheduleCapacityError
from hourly_pay.domain.models import GenerationBatch, Lesson, MonthlyAllocation, TimeSlot
from hourly_pay.domain.rules import AUDITORY_WORK_TYPES, is_even_hours
from hourly_pay.scheduler.availability import CalendarPolicy, TeacherAvailability

LESSON_HOURS = Decimal("2")
FIRST_COURSE_LAST_END = time(16, 0)
EVENING_START = time(16, 0)
LECTURE_PRIORITY_DAYS = 14


@dataclass(frozen=True, slots=True)
class ScheduledAllocation:
    allocation: MonthlyAllocation
    group_name: str
    discipline: str
    work_type: WorkType
    study_form: StudyForm = StudyForm.FULL_TIME
    course: str | None = None
    prefer_evening: bool = False


@dataclass(frozen=True, slots=True)
class ScheduleGenerationResult:
    batch: GenerationBatch
    lessons: tuple[Lesson, ...]
    available_capacity: int


def generate_schedule(
    *,
    teacher_id: int,
    year: int,
    month: int,
    allocations: Iterable[ScheduledAllocation],
    availability: TeacherAvailability,
    calendar_policy: CalendarPolicy | None = None,
    time_slots: Sequence[TimeSlot] = DEFAULT_TIME_SLOTS,
    seed: int | None = None,
    occupied: Iterable[tuple[date, int]] = (),
    practice_lab_start_date: date | None = None,
) -> ScheduleGenerationResult:
    if not 1 <= month <= 12:
        raise InvalidScheduleError(f"Некорректный месяц: {month}.")
    slots_by_id = _validate_time_slots(time_slots)
    allocation_units = _lesson_units(tuple(allocations), year=year, month=month)
    practice_units = [unit for unit in allocation_units if unit.work_type != WorkType.LECTURE]
    if practice_units and practice_lab_start_date is None:
        raise InvalidScheduleError(
            "Укажите первую допустимую дату практик и лабораторных для семестра."
        )
    policy = calendar_policy or CalendarPolicy()
    occupied_set = set(occupied)
    candidates = _available_candidates(
        year=year,
        month=month,
        availability=availability,
        calendar_policy=policy,
        slots_by_id=slots_by_id,
        occupied=occupied_set,
    )
    if len(allocation_units) > len(candidates):
        raise ScheduleCapacityError(
            needed_lessons=len(allocation_units), available_slots=len(candidates)
        )

    actual_seed = seed if seed is not None else secrets.randbits(63)
    randomizer = random.Random(actual_seed)
    randomizer.shuffle(candidates)
    randomizer.shuffle(allocation_units)
    late_candidates = [candidate for candidate in candidates
                       if practice_lab_start_date is not None
                       and candidate[0] >= practice_lab_start_date]
    if len(practice_units) > len(late_candidates):
        raise InvalidScheduleError(
            "После первой допустимой даты практик и лабораторных недостаточно "
            f"свободных слотов: нужно {len(practice_units)}, доступно {len(late_candidates)}."
        )
    options = [
        [candidate for candidate in candidates if _unit_allows(
            unit, candidate, slots_by_id, practice_lab_start_date
        )]
        for unit in allocation_units
    ]
    order = sorted(range(len(allocation_units)), key=lambda index: len(options[index]))
    assigned: dict[tuple[date, int], int] = {}

    def assign(unit_index: int, seen: set[tuple[date, int]]) -> bool:
        unit = allocation_units[unit_index]
        ranked = sorted(options[unit_index], key=lambda candidate: _preference(
            unit, candidate, slots_by_id
        ))
        for candidate in ranked:
            if candidate in seen:
                continue
            seen.add(candidate)
            previous = assigned.get(candidate)
            if previous is None or assign(previous, seen):
                assigned[candidate] = unit_index
                return True
        return False

    for index in order:
        if not assign(index, set()):
            raise InvalidScheduleError(
                "Недостаточно допустимых слотов для выбранных занятий. "
                "Проверьте время первого курса и дату допуска практик/лабораторных."
            )
    _improve_preferences(assigned, allocation_units, options, slots_by_id)
    selected = [(allocation_units[index], candidate) for candidate, index in assigned.items()]
    batch = GenerationBatch(teacher_id=teacher_id, year=year, month=month, seed=actual_seed)
    lessons = tuple(
        Lesson(
            teacher_id=teacher_id,
            monthly_allocation_id=_required_allocation_id(unit.allocation),
            lesson_date=lesson_date,
            time_slot_id=slot_id,
            group_name=unit.group_name,
            discipline=unit.discipline,
            work_type=unit.work_type,
            hours=LESSON_HOURS,
            generation_batch_id=None,
            manual_override=False,
        )
        for unit, (lesson_date, slot_id) in selected
    )
    validate_lessons(
        lessons,
        teacher_id=teacher_id,
        availability=availability,
        calendar_policy=policy,
        time_slots=time_slots,
        practice_lab_start_date=practice_lab_start_date,
        allocations={_required_allocation_id(unit.allocation): unit for unit in allocation_units},
    )
    return ScheduleGenerationResult(
        batch=batch,
        lessons=lessons,
        available_capacity=len(candidates),
    )


def validate_lessons(
    lessons: Iterable[Lesson],
    *,
    teacher_id: int,
    availability: TeacherAvailability,
    calendar_policy: CalendarPolicy,
    time_slots: Sequence[TimeSlot] = DEFAULT_TIME_SLOTS,
    practice_lab_start_date: date | None = None,
    allocations: Mapping[int, ScheduledAllocation] | None = None,
) -> None:
    slots_by_id = _validate_time_slots(time_slots)
    occupied: set[tuple[date, int]] = set()
    for lesson in lessons:
        if lesson.teacher_id != teacher_id:
            raise InvalidScheduleError("Расписание содержит занятие другого преподавателя.")
        if lesson.hours != LESSON_HOURS:
            raise InvalidScheduleError("Одно занятие должно содержать ровно 2 часа.")
        if lesson.time_slot_id not in slots_by_id:
            raise InvalidScheduleError(f"Неизвестный временной слот: {lesson.time_slot_id}.")
        scheduled = allocations.get(lesson.monthly_allocation_id) if allocations else None
        if (
            scheduled and _is_first_course(scheduled.course)
            and slots_by_id[lesson.time_slot_id].end_time > FIRST_COURSE_LAST_END
        ):
            raise InvalidScheduleError(
                "Занятия первого курса должны заканчиваться не позднее 16:00."
            )
        if lesson.work_type in {WorkType.PRACTICE, WorkType.LAB}:
            if practice_lab_start_date is None:
                raise InvalidScheduleError(
                    "Укажите первую допустимую дату практик и лабораторных для семестра."
                )
            if lesson.lesson_date < practice_lab_start_date:
                raise InvalidScheduleError(
                    f"Практики и лабораторные нельзя ставить раньше "
                    f"{practice_lab_start_date:%d.%m.%Y}."
                )
        if not calendar_policy.is_working_date(lesson.lesson_date):
            raise InvalidScheduleError(f"Дата {lesson.lesson_date:%d.%m.%Y} недоступна.")
        if lesson.time_slot_id not in availability.allowed_slots(lesson.lesson_date):
            raise InvalidScheduleError(
                f"Слот {lesson.time_slot_id} недоступен {lesson.lesson_date:%d.%m.%Y}."
            )
        key = (lesson.lesson_date, lesson.time_slot_id)
        if key in occupied:
            raise InvalidScheduleError("Обнаружен повтор даты и временного слота.")
        occupied.add(key)


def _lesson_units(
    allocations: tuple[ScheduledAllocation, ...], *, year: int, month: int
) -> list[ScheduledAllocation]:
    units: list[ScheduledAllocation] = []
    for scheduled in allocations:
        allocation = scheduled.allocation
        if allocation.id is None:
            raise InvalidScheduleError("Сначала сохраните помесячное распределение.")
        if (allocation.year, allocation.month) != (year, month):
            raise InvalidScheduleError("Распределение относится к другому месяцу.")
        if allocation.hours < 0 or not is_even_hours(allocation.hours):
            raise InvalidScheduleError("Часы распределения должны быть неотрицательны и кратны 2.")
        if scheduled.work_type not in AUDITORY_WORK_TYPES:
            raise InvalidScheduleError("В расписание допускаются только Лек/Пр/Лаб.")
        lesson_count = int(allocation.hours / LESSON_HOURS)
        units.extend(scheduled for _ in range(lesson_count))
    return units


def _is_first_course(value: str | None) -> bool:
    return value is not None and value.strip().casefold() in {"1", "1 курс", "1.0"}


def _unit_allows(
    unit: ScheduledAllocation,
    candidate: tuple[date, int],
    slots_by_id: Mapping[int, TimeSlot],
    practice_lab_start_date: date | None,
) -> bool:
    lesson_date, slot_id = candidate
    if _is_first_course(unit.course) and slots_by_id[slot_id].end_time > FIRST_COURSE_LAST_END:
        return False
    return (
        unit.work_type == WorkType.LECTURE
        or practice_lab_start_date is not None and lesson_date >= practice_lab_start_date
    )


def _preference(
    unit: ScheduledAllocation,
    candidate: tuple[date, int],
    slots_by_id: Mapping[int, TimeSlot],
) -> tuple[bool, bool]:
    lesson_date, slot_id = candidate
    early_lecture = unit.work_type == WorkType.LECTURE and lesson_date.day <= LECTURE_PRIORITY_DAYS
    evening = (
        (unit.study_form == StudyForm.CORRESPONDENCE or unit.prefer_evening)
        and slots_by_id[slot_id].start_time >= EVENING_START
    )
    return (not early_lecture, not evening)


def _improve_preferences(
    assigned: dict[tuple[date, int], int],
    units: Sequence[ScheduledAllocation],
    options: Sequence[list[tuple[date, int]]],
    slots_by_id: Mapping[int, TimeSlot],
) -> None:
    by_unit = {index: candidate for candidate, index in assigned.items()}
    changed = True
    while changed:
        changed = False
        for index, unit in enumerate(units):
            current = by_unit[index]
            current_rank = _preference(unit, current, slots_by_id)
            for candidate in options[index]:
                if _preference(unit, candidate, slots_by_id) >= current_rank:
                    continue
                occupant = assigned.get(candidate)
                if occupant is not None:
                    if current not in options[occupant]:
                        continue
                    if _preference(units[occupant], current, slots_by_id) > _preference(
                        units[occupant], candidate, slots_by_id
                    ):
                        continue
                    assigned[current] = occupant
                    by_unit[occupant] = current
                else:
                    del assigned[current]
                assigned[candidate] = index
                by_unit[index] = candidate
                changed = True
                break


def _required_allocation_id(allocation: MonthlyAllocation) -> int:
    if allocation.id is None:
        raise InvalidScheduleError("Сначала сохраните помесячное распределение.")
    return allocation.id


def _validate_time_slots(time_slots: Sequence[TimeSlot]) -> dict[int, TimeSlot]:
    slots_by_id = {slot.id: slot for slot in time_slots}
    if len(slots_by_id) != len(time_slots):
        raise InvalidScheduleError("Идентификаторы временных слотов должны быть уникальны.")
    if len({slot.sort_order for slot in time_slots}) != len(time_slots):
        raise InvalidScheduleError("Порядок временных слотов должен быть уникален.")
    return slots_by_id


def _available_candidates(
    *,
    year: int,
    month: int,
    availability: TeacherAvailability,
    calendar_policy: CalendarPolicy,
    slots_by_id: dict[int, TimeSlot],
    occupied: set[tuple[date, int]],
) -> list[tuple[date, int]]:
    candidates: list[tuple[date, int]] = []
    last_day = calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        current = date(year, month, day)
        if not calendar_policy.is_working_date(current):
            continue
        allowed_ids = availability.allowed_slots(current)
        unknown_ids = allowed_ids - slots_by_id.keys()
        if unknown_ids:
            raise InvalidScheduleError(
                "Доступность содержит неизвестные слоты: "
                + ", ".join(str(value) for value in sorted(unknown_ids))
            )
        for slot_id in sorted(allowed_ids, key=lambda value: slots_by_id[value].sort_order):
            candidate = (current, slot_id)
            if candidate not in occupied:
                candidates.append(candidate)
    return candidates
