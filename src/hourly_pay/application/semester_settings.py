import re
from datetime import date
from typing import Protocol

from hourly_pay.domain.errors import InvalidScheduleError
from hourly_pay.domain.models import AcademicYear, SemesterPracticeStart


class SemesterStartStore(Protocol):
    def list_years(self) -> tuple[AcademicYear, ...]: ...

    def get(self, academic_year_id: int, semester: int) -> SemesterPracticeStart | None: ...

    def save(self, academic_year_id: int, semester: int, value: date | None) -> None: ...


def semester_for_month(month: int) -> int:
    if month in (9, 10, 11, 12):
        return 1
    if month in (1, 2, 3, 4, 5):
        return 2
    raise InvalidScheduleError(f"Месяц {month} не входит в учебный год.")


class SemesterSettingsService:
    def __init__(self, repository: SemesterStartStore) -> None:
        self._repository = repository

    def list_years(self) -> tuple[AcademicYear, ...]:
        return self._repository.list_years()

    def get(self, academic_year_id: int, semester: int) -> date | None:
        self._validate_year_and_semester(academic_year_id, semester)
        entry = self._repository.get(academic_year_id, semester)
        return entry.first_allowed_date if entry else None

    def save(self, academic_year_id: int, semester: int, value: date | None) -> None:
        year = self._validate_year_and_semester(academic_year_id, semester)
        if value is not None:
            match = re.fullmatch(r"(20\d{2})-(20\d{2})", year.name)
            if match is None or int(match[2]) != int(match[1]) + 1:
                raise InvalidScheduleError(f"Некорректный учебный год: {year.name}.")
            expected_year = int(match[1]) if semester == 1 else int(match[2])
            allowed_months = (9, 10, 11, 12) if semester == 1 else (1, 2, 3, 4, 5)
            if value.year != expected_year or value.month not in allowed_months:
                raise InvalidScheduleError(
                    f"Дата допуска должна относиться к {semester}-му семестру "
                    f"учебного года {year.name}."
                )
        self._repository.save(academic_year_id, semester, value)

    def _validate_year_and_semester(self, academic_year_id: int, semester: int) -> AcademicYear:
        if semester not in (1, 2):
            raise InvalidScheduleError("Номер семестра должен быть 1 или 2.")
        year = next(
            (entry for entry in self._repository.list_years() if entry.id == academic_year_id),
            None,
        )
        if year is None:
            raise InvalidScheduleError("Учебный год не найден.")
        return year
