from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

from hourly_pay.domain.errors import InvalidTeacherSettingsError
from hourly_pay.domain.models import Teacher
from hourly_pay.persistence.repositories import TeacherSourceSummary

RATE_STORAGE_PRECISION = Decimal("0.0001")
PERSONAL_TEXT_LIMITS = {
    "full_name": 300, "department": 500, "degree": 300, "title": 300,
    "position": 300, "address": 1000, "passport_series": 20,
    "passport_number": 30, "passport_issued_by": 1000,
    "snils": 30, "inn": 30,
}


@dataclass(frozen=True, slots=True)
class TeacherPersonalData:
    full_name: str
    department: str = ""
    degree: str = ""
    title: str = ""
    position: str = ""
    birth_date: date | None = None
    address: str = ""
    passport_series: str = ""
    passport_number: str = ""
    passport_issued_by: str = ""
    passport_issue_date: date | None = None
    snils: str = ""
    inn: str = ""


class TeacherSettingsRepository(Protocol):
    def list_teachers(self) -> tuple[Teacher, ...]: ...

    def list_teacher_sources(self, teacher_id: int) -> tuple[TeacherSourceSummary, ...]: ...

    def set_effective_rate(self, teacher_id: int, rate: Decimal) -> None: ...

    def set_personal_data(self, teacher_id: int, values: dict[str, object]) -> None: ...

    def set_source_inclusions(
        self, teacher_id: int, inclusions: dict[int, bool | None]
    ) -> None: ...

    def delete_source(self, teacher_id: int, source_id: int) -> None: ...


@dataclass(frozen=True, slots=True)
class TeacherProfile:
    teacher: Teacher
    sources: tuple[TeacherSourceSummary, ...]


class TeacherSettingsService:
    def __init__(self, repository: TeacherSettingsRepository) -> None:
        self._repository = repository

    def list_teachers(self) -> tuple[Teacher, ...]:
        return self._repository.list_teachers()

    def get_profile(self, teacher_id: int) -> TeacherProfile:
        teacher = next(
            (item for item in self._repository.list_teachers() if item.id == teacher_id),
            None,
        )
        if teacher is None:
            raise InvalidTeacherSettingsError("Преподаватель не найден.")
        return TeacherProfile(teacher, self._repository.list_teacher_sources(teacher_id))

    def confirm_effective_rate(self, teacher_id: int, rate: Decimal) -> None:
        if not isinstance(rate, Decimal) or not rate.is_finite() or rate < 0:
            raise InvalidTeacherSettingsError(
                "Эффективная ставка должна быть неотрицательным числом."
            )
        try:
            has_extra_digits = rate.quantize(RATE_STORAGE_PRECISION) != rate
        except InvalidOperation as error:
            raise InvalidTeacherSettingsError("Эффективная ставка слишком велика.") from error
        if has_extra_digits:
            raise InvalidTeacherSettingsError(
                "Эффективная ставка: не более 4 знаков после запятой."
            )
        self._repository.set_effective_rate(teacher_id, rate)

    def save_personal_data(self, teacher_id: int, data: TeacherPersonalData) -> None:
        values: dict[str, object] = {}
        for field_name, limit in PERSONAL_TEXT_LIMITS.items():
            raw = getattr(data, field_name)
            if not isinstance(raw, str):
                raise InvalidTeacherSettingsError("Некорректное текстовое поле карточки.")
            value = raw.strip()
            if len(value) > limit:
                raise InvalidTeacherSettingsError(
                    f"Поле «{field_name}» слишком длинное (максимум {limit} символов)."
                )
            values[field_name] = value if field_name == "full_name" else value or None
        if not values["full_name"]:
            raise InvalidTeacherSettingsError("Укажите ФИО преподавателя.")
        for field_name in ("birth_date", "passport_issue_date"):
            value = getattr(data, field_name)
            if value is not None and (not isinstance(value, date) or value > date.today()):
                raise InvalidTeacherSettingsError("Укажите корректную дату, не позднее сегодня.")
            values[field_name] = value
        self._repository.set_personal_data(teacher_id, values)

    def save_source_inclusions(
        self, teacher_id: int, inclusions: dict[int, bool | None]
    ) -> None:
        if any(value is not True and value is not False and value is not None
               for value in inclusions.values()):
            raise InvalidTeacherSettingsError("Неизвестное значение учета источника.")
        self._repository.set_source_inclusions(teacher_id, inclusions)

    def delete_source(self, teacher_id: int, source_id: int) -> None:
        self._repository.delete_source(teacher_id, source_id)
