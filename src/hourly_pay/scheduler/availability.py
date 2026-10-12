from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class CalendarPolicy:
    base_holidays: frozenset[date] = frozenset()
    excluded_dates: frozenset[date] = frozenset()
    working_overrides: frozenset[date] = frozenset()

    def is_working_date(self, value: date) -> bool:
        if value.weekday() > 4:
            return False
        if value in self.excluded_dates:
            return False
        return value not in self.base_holidays or value in self.working_overrides


@dataclass(frozen=True, slots=True)
class TeacherAvailability:
    weekday_allowed_slots: Mapping[int, frozenset[int]] = field(default_factory=dict)
    excluded_dates: frozenset[date] = frozenset()
    per_date_allowed_slots: Mapping[date, frozenset[int]] = field(default_factory=dict)

    def allowed_slots(self, value: date) -> frozenset[int]:
        if value in self.excluded_dates:
            return frozenset()
        if value in self.per_date_allowed_slots:
            return self.per_date_allowed_slots[value]
        return self.weekday_allowed_slots.get(value.weekday(), frozenset())


def russian_holiday_dates(years: Iterable[int]) -> frozenset[date]:
    """Return the offline RU calendar supplied by the holidays package."""
    import holidays

    calendar = holidays.country_holidays("RU", years=sorted(set(years)))
    return frozenset(calendar.keys())
