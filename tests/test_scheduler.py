from datetime import date
from decimal import Decimal

import pytest

from hourly_pay.config.defaults import DEFAULT_TIME_SLOTS
from hourly_pay.domain.enums import StudyForm, WorkType
from hourly_pay.domain.errors import InvalidScheduleError, ScheduleCapacityError
from hourly_pay.domain.models import Lesson, MonthlyAllocation
from hourly_pay.scheduler.availability import (
    CalendarPolicy,
    TeacherAvailability,
    russian_holiday_dates,
)
from hourly_pay.scheduler.generator import (
    ScheduledAllocation,
    ScheduleGenerationResult,
    generate_schedule,
    validate_lessons,
)


def _scheduled(*, hours: str = "10", allocation_id: int = 1) -> ScheduledAllocation:
    return ScheduledAllocation(
        allocation=MonthlyAllocation(
            id=allocation_id,
            hourly_selection_id=1,
            month=3,
            year=2027,
            hours=Decimal(hours),
        ),
        group_name="ГРУППА",
        discipline="Дисциплина",
        work_type=WorkType.LECTURE,
    )


def _availability(*slot_ids: int) -> TeacherAvailability:
    allowed = frozenset(slot_ids or range(1, 8))
    return TeacherAvailability(weekday_allowed_slots={day: allowed for day in range(5)})


def _keys(result: ScheduleGenerationResult) -> list[tuple[date, int]]:
    return [(lesson.lesson_date, lesson.time_slot_id) for lesson in result.lessons]


def test_default_time_slots_match_specification() -> None:
    assert [slot.display_text for slot in DEFAULT_TIME_SLOTS] == [
        "08:30-10:05",
        "10:15-11:50",
        "12:40-14:15",
        "14:25-16:00",
        "16:10-17:45",
        "17:55-19:30",
        "19:40-21:15",
    ]


def test_hours_are_split_into_two_hour_weekday_lessons() -> None:
    result = generate_schedule(
        teacher_id=1,
        year=2027,
        month=3,
        allocations=[_scheduled(hours="10")],
        availability=_availability(),
        seed=42,
    )
    assert len(result.lessons) == 5
    assert all(lesson.hours == Decimal("2") for lesson in result.lessons)
    assert all(lesson.lesson_date.weekday() < 5 for lesson in result.lessons)
    assert len(set(_keys(result))) == len(result.lessons)


def test_holidays_exclusions_and_forbidden_slots_are_respected() -> None:
    excluded = date(2027, 3, 2)
    holiday = date(2027, 3, 3)
    result = generate_schedule(
        teacher_id=1,
        year=2027,
        month=3,
        allocations=[_scheduled(hours="20")],
        availability=TeacherAvailability(
            weekday_allowed_slots={day: frozenset({3}) for day in range(5)},
            excluded_dates=frozenset({excluded}),
        ),
        calendar_policy=CalendarPolicy(base_holidays=frozenset({holiday})),
        seed=4,
    )
    assert all(lesson.time_slot_id == 3 for lesson in result.lessons)
    assert all(lesson.lesson_date not in {excluded, holiday} for lesson in result.lessons)


def test_manual_working_override_restores_base_holiday_but_not_global_exclusion() -> None:
    value = date(2027, 3, 3)
    assert CalendarPolicy(
        base_holidays=frozenset({value}), working_overrides=frozenset({value})
    ).is_working_date(value)
    assert not CalendarPolicy(
        base_holidays=frozenset({value}),
        excluded_dates=frozenset({value}),
        working_overrides=frozenset({value}),
    ).is_working_date(value)


def test_russian_holidays_are_available_offline() -> None:
    assert date(2027, 1, 1) in russian_holiday_dates([2027])


def test_existing_occupied_slot_is_not_reused() -> None:
    occupied = (date(2027, 3, 1), 1)
    result = generate_schedule(
        teacher_id=1,
        year=2027,
        month=3,
        allocations=[_scheduled(hours="4")],
        availability=_availability(1),
        seed=1,
        occupied={occupied},
    )
    assert occupied not in _keys(result)


def test_capacity_error_reports_missing_hours_and_slots() -> None:
    only_date = date(2027, 3, 1)
    availability = TeacherAvailability(
        weekday_allowed_slots={},
        per_date_allowed_slots={only_date: frozenset({1})},
    )
    with pytest.raises(ScheduleCapacityError) as error:
        generate_schedule(
            teacher_id=1,
            year=2027,
            month=3,
            allocations=[_scheduled(hours="4")],
            availability=availability,
            seed=1,
        )
    assert error.value.needed_lessons == 2
    assert error.value.available_slots == 1
    assert error.value.unallocated_hours == 2


def test_fixed_seed_is_reproducible_and_reroll_changes_schedule() -> None:
    arguments = {
        "teacher_id": 1,
        "year": 2027,
        "month": 3,
        "allocations": [_scheduled(hours="20")],
        "availability": _availability(),
    }
    first = generate_schedule(**arguments, seed=10)
    repeated = generate_schedule(**arguments, seed=10)
    rerolled = generate_schedule(**arguments, seed=11)
    assert _keys(first) == _keys(repeated)
    assert _keys(first) != _keys(rerolled)


def test_gaps_between_slots_are_valid() -> None:
    lesson_date = date(2027, 3, 1)
    lessons = [
        Lesson(1, 1, lesson_date, slot, "ГРУППА", "Дисциплина", WorkType.LECTURE, None)
        for slot in (1, 3)
    ]
    validate_lessons(
        lessons,
        teacher_id=1,
        availability=_availability(1, 3),
        calendar_policy=CalendarPolicy(),
    )


def test_duplicate_date_and_slot_is_rejected() -> None:
    lesson_date = date(2027, 3, 1)
    lesson = Lesson(
        1, 1, lesson_date, 1, "ГРУППА", "Дисциплина", WorkType.LECTURE, None
    )
    with pytest.raises(InvalidScheduleError, match="повтор"):
        validate_lessons(
            [lesson, lesson],
            teacher_id=1,
            availability=_availability(1),
            calendar_policy=CalendarPolicy(),
        )


def test_unknown_availability_slot_is_rejected() -> None:
    with pytest.raises(InvalidScheduleError, match="неизвестные слоты"):
        generate_schedule(
            teacher_id=1,
            year=2027,
            month=3,
            allocations=[_scheduled(hours="2")],
            availability=_availability(999),
            seed=1,
        )


def test_practice_requires_explicit_semester_date_and_never_precedes_it() -> None:
    practice = _scheduled(hours="4")
    practice = ScheduledAllocation(
        practice.allocation, practice.group_name, practice.discipline, WorkType.PRACTICE
    )
    with pytest.raises(InvalidScheduleError, match="Укажите первую допустимую дату"):
        generate_schedule(
            teacher_id=1, year=2027, month=3, allocations=[practice],
            availability=_availability(1), seed=3,
        )
    result = generate_schedule(
        teacher_id=1, year=2027, month=3,
        allocations=[practice, _scheduled(hours="2", allocation_id=2)],
        availability=_availability(1), practice_lab_start_date=date(2027, 3, 15), seed=3,
    )
    assert all(
        lesson.lesson_date >= date(2027, 3, 15)
        for lesson in result.lessons if lesson.work_type == WorkType.PRACTICE
    )


def test_late_date_capacity_is_reported_without_using_early_slots() -> None:
    practice = _scheduled(hours="4")
    practice = ScheduledAllocation(
        practice.allocation, practice.group_name, practice.discipline, WorkType.LAB
    )
    with pytest.raises(InvalidScheduleError, match="недостаточно свободных слотов"):
        generate_schedule(
            teacher_id=1, year=2027, month=3, allocations=[practice],
            availability=TeacherAvailability(
                weekday_allowed_slots={},
                per_date_allowed_slots={
                    date(2027, 3, 1): frozenset({1}),
                    date(2027, 3, 15): frozenset({1}),
                },
            ),
            practice_lab_start_date=date(2027, 3, 15), seed=2,
        )


def test_validation_rejects_practice_before_configured_date() -> None:
    lesson = Lesson(
        1, 1, date(2027, 3, 1), 1, "ГРУППА", "Дисциплина", WorkType.PRACTICE, None
    )
    with pytest.raises(InvalidScheduleError, match="раньше 15.03.2027"):
        validate_lessons(
            [lesson], teacher_id=1, availability=_availability(1),
            calendar_policy=CalendarPolicy(), practice_lab_start_date=date(2027, 3, 15),
        )


def test_first_course_ends_by_1600_and_manual_move_is_rejected() -> None:
    original = _scheduled(hours="4")
    first_course = ScheduledAllocation(
        original.allocation, original.group_name, original.discipline,
        original.work_type, StudyForm.FULL_TIME, "1",
    )
    result = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[first_course],
        availability=_availability(4, 5), seed=7,
    )
    assert {lesson.time_slot_id for lesson in result.lessons} == {4}
    moved = result.lessons[0]
    moved.time_slot_id = 5
    with pytest.raises(InvalidScheduleError, match="первого курса"):
        validate_lessons(
            [moved], teacher_id=1, availability=_availability(4, 5),
            calendar_policy=CalendarPolicy(), allocations={1: first_course},
        )


def test_correspondence_prefers_evening_but_can_use_daytime() -> None:
    original = _scheduled(hours="10")
    correspondence = ScheduledAllocation(
        original.allocation, original.group_name, original.discipline,
        original.work_type, StudyForm.CORRESPONDENCE,
    )
    evening = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[correspondence],
        availability=_availability(1, 5), seed=7,
    )
    assert all(lesson.time_slot_id == 5 for lesson in evening.lessons)
    daytime = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[correspondence],
        availability=_availability(1), seed=7,
    )
    assert all(lesson.time_slot_id == 1 for lesson in daytime.lessons)


def test_first_course_cutoff_takes_precedence_over_evening_preference() -> None:
    original = _scheduled(hours="2")
    allocation = ScheduledAllocation(
        original.allocation, original.group_name, original.discipline,
        original.work_type, StudyForm.CORRESPONDENCE, "1",
    )
    result = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[allocation],
        availability=_availability(4, 5), seed=7,
    )
    assert result.lessons[0].time_slot_id == 4


def test_lecture_can_be_scheduled_after_first_two_weeks() -> None:
    result = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[_scheduled(hours="2")],
        availability=TeacherAvailability(
            weekday_allowed_slots={},
            per_date_allowed_slots={date(2027, 3, 22): frozenset({1})},
        ),
        seed=7,
    )
    assert result.lessons[0].lesson_date == date(2027, 3, 22)


def test_lecture_prefers_first_two_weeks_when_slots_exist() -> None:
    result = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[_scheduled(hours="2")],
        availability=TeacherAvailability(
            weekday_allowed_slots={},
            per_date_allowed_slots={
                date(2027, 3, 2): frozenset({1}),
                date(2027, 3, 22): frozenset({1}),
            },
        ),
        seed=7,
    )
    assert result.lessons[0].lesson_date == date(2027, 3, 2)


def test_explicit_evening_preference_for_full_time_import_row() -> None:
    original = _scheduled(hours="2")
    preferred = ScheduledAllocation(
        original.allocation, original.group_name, original.discipline,
        original.work_type, StudyForm.FULL_TIME, None, True,
    )
    result = generate_schedule(
        teacher_id=1, year=2027, month=3, allocations=[preferred],
        availability=_availability(1, 5), seed=7,
    )
    assert result.lessons[0].time_slot_id == 5


def test_lecture_priority_survives_competition_for_early_slot() -> None:
    lecture = _scheduled(hours="2")
    original = _scheduled(hours="2", allocation_id=2)
    practice = ScheduledAllocation(
        original.allocation, original.group_name, original.discipline, WorkType.PRACTICE
    )
    availability = TeacherAvailability(
        weekday_allowed_slots={},
        per_date_allowed_slots={
            date(2027, 3, 2): frozenset({1}),
            date(2027, 3, 22): frozenset({1}),
        },
    )
    for seed in range(10):
        result = generate_schedule(
            teacher_id=1, year=2027, month=3,
            allocations=[lecture, practice], availability=availability,
            practice_lab_start_date=date(2027, 3, 1), seed=seed,
        )
        lecture_lesson = next(
            lesson for lesson in result.lessons if lesson.work_type == WorkType.LECTURE
        )
        assert lecture_lesson.lesson_date == date(2027, 3, 2)
