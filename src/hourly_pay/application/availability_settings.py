from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import Teacher, TimeSlot
from hourly_pay.scheduler.availability import TeacherAvailability


class TeacherReader(Protocol):
    def list_teachers(self) -> tuple[Teacher, ...]: ...


class AvailabilityRepository(Protocol):
    def list_time_slots(self) -> tuple[TimeSlot, ...]: ...

    def get_availability(self, teacher_id: int) -> TeacherAvailability: ...

    def replace_availability(self, teacher_id: int, availability: TeacherAvailability) -> None: ...


@dataclass(frozen=True, slots=True)
class AvailabilitySnapshot:
    time_slots: tuple[TimeSlot, ...]
    availability: TeacherAvailability


class AvailabilitySettingsService:
    def __init__(self, teachers: TeacherReader, repository: AvailabilityRepository) -> None:
        self._teachers = teachers
        self._repository = repository

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._teachers.list_teachers()

    def load(self, teacher_id: int) -> AvailabilitySnapshot:
        return AvailabilitySnapshot(
            time_slots=self._repository.list_time_slots(),
            availability=self._repository.get_availability(teacher_id),
        )

    def save(
        self,
        teacher_id: int,
        *,
        weekdays: Mapping[int, Iterable[int]],
        excluded_dates: Iterable[date],
        per_date: Mapping[date, Iterable[int]],
    ) -> TeacherAvailability:
        weekday_map = {day: frozenset(slot_ids) for day, slot_ids in weekdays.items()}
        excluded = frozenset(excluded_dates)
        date_map = {target: frozenset(slot_ids) for target, slot_ids in per_date.items()}
        if not set(weekday_map) <= set(range(5)):
            raise InvalidScheduleError("Недельная доступность задаётся только для Пн–Пт.")
        if excluded & date_map.keys():
            raise InvalidScheduleError(
                "Одна дата не может быть одновременно исключена и иметь разрешённые слоты."
            )
        if any(target.weekday() > 4 for target in date_map):
            raise InvalidScheduleError("Для выходного дня нельзя разрешить слоты занятий.")
        known_ids = {slot.id for slot in self._repository.list_time_slots()}
        supplied_ids = {
            slot_id
            for values in (*weekday_map.values(), *date_map.values())
            for slot_id in values
        }
        if not supplied_ids <= known_ids:
            raise InvalidScheduleError("Доступность содержит неизвестные временные слоты.")
        availability = TeacherAvailability(
            weekday_allowed_slots=weekday_map,
            excluded_dates=excluded,
            per_date_allowed_slots=date_map,
        )
        self._repository.replace_availability(teacher_id, availability)
        return availability
