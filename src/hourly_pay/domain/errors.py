from hourly_pay.domain.enums import WarningCode


class DomainError(Exception):
    """Base class for errors safe to present to a user."""


class UnrecognizedFormatError(DomainError):
    code = WarningCode.UNRECOGNIZED_FORMAT

    def __init__(self, details: str | None = None) -> None:
        message = "Формат файла не распознан"
        if details:
            message = f"{message}: {details}"
        super().__init__(message)


class DuplicateImportError(DomainError):
    code = WarningCode.DUPLICATE_IMPORT

    def __init__(self, file_sha256: str) -> None:
        self.file_sha256 = file_sha256
        super().__init__("Этот файл уже импортирован.")


class InvalidCalculationError(DomainError):
    """Raised when hourly-limit inputs violate a confirmed domain invariant."""


class InvalidTeacherSettingsError(DomainError):
    """Raised when teacher rate or source inclusion cannot be saved."""


class InvalidSelectionError(DomainError):
    """Raised when a manual hourly selection violates a business rule."""


class InvalidMonthlyAllocationError(DomainError):
    """Raised when a monthly allocation cannot be saved."""


class InvalidScheduleError(DomainError):
    """Raised when schedule inputs or manual edits violate scheduler rules."""


class InvalidDocumentExportError(DomainError):
    """Raised when a statement cannot be exported safely."""


class InvalidDistributionExportError(DomainError):
    """Raised when an academic-year distribution cannot be exported safely."""


class ScheduleCapacityError(DomainError):
    def __init__(self, *, needed_lessons: int, available_slots: int) -> None:
        self.needed_lessons = needed_lessons
        self.available_slots = available_slots
        self.unallocated_hours = max(0, needed_lessons - available_slots) * 2
        super().__init__(
            f"Не удалось распределить {self.unallocated_hours} часов. "
            f"Нужно занятий: {needed_lessons}. "
            f"Доступно свободных слотов: {available_slots}. "
            "Измените доступность преподавателя или исключенные даты."
        )
