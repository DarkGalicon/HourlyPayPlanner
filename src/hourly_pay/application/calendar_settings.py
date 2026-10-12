from collections.abc import Iterable
from datetime import date
from typing import Protocol

from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import CalendarOverride
from hourly_pay.scheduler.availability import CalendarPolicy, russian_holiday_dates


class CalendarOverrideStore(Protocol):
    def list_overrides(self) -> tuple[CalendarOverride, ...]: ...

    def replace_overrides(self, overrides: tuple[CalendarOverride, ...]) -> None: ...


class CalendarSettingsService:
    def __init__(self, repository: CalendarOverrideStore) -> None:
        self._repository = repository

    def list_overrides(self) -> tuple[CalendarOverride, ...]:
        return self._repository.list_overrides()

    def base_holidays(self, year: int) -> tuple[date, ...]:
        if not 1900 <= year <= 2200:
            raise InvalidScheduleError("Год календаря должен быть между 1900 и 2200.")
        return tuple(sorted(russian_holiday_dates([year])))

    def policy_for_years(self, years: Iterable[int]) -> CalendarPolicy:
        overrides = self.list_overrides()
        return CalendarPolicy(
            base_holidays=russian_holiday_dates(years),
            excluded_dates=frozenset(
                entry.target_date for entry in overrides if not entry.is_working
            ),
            working_overrides=frozenset(
                entry.target_date for entry in overrides if entry.is_working
            ),
        )

    def save(self, overrides: Iterable[CalendarOverride]) -> tuple[CalendarOverride, ...]:
        entries = tuple(overrides)
        targets = [entry.target_date for entry in entries]
        if len(targets) != len(set(targets)):
            raise InvalidScheduleError("Одна календарная дата указана несколько раз.")
        if any(entry.is_working and entry.target_date.weekday() > 4 for entry in entries):
            raise InvalidScheduleError("Выходной нельзя сделать рабочим днём для занятий.")
        if any(not isinstance(entry.is_working, bool) for entry in entries):
            raise InvalidScheduleError("Для даты укажите статус «рабочая» или «нерабочая».")
        ordered = tuple(sorted(entries, key=lambda entry: entry.target_date))
        self._repository.replace_overrides(ordered)
        return ordered
