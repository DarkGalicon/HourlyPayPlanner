from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from hourly_pay.domain.enums import (
    SessionPeriod,
    StudyForm,
    WarningCode,
    WarningSeverity,
    WorkType,
)


@dataclass(slots=True)
class AcademicYear:
    name: str
    is_active: bool = False
    id: int | None = None


@dataclass(slots=True)
class Teacher:
    full_name: str
    effective_rate: Decimal | None = None
    department: str | None = None
    degree: str | None = None
    title: str | None = None
    position: str | None = None
    birth_date: date | None = None
    address: str | None = None
    passport_series: str | None = None
    passport_number: str | None = None
    passport_issued_by: str | None = None
    passport_issue_date: date | None = None
    snils: str | None = None
    inn: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class WorkloadSource:
    original_filename: str
    file_sha256: str
    employment_type: str
    reported_rate: Decimal | None
    reported_total_hours: Decimal | None
    parser_version: str = "nagr_xlsx_v2"
    include_in_fact: bool | None = None
    id: int | None = None
    teacher_id: int | None = None
    academic_year_id: int | None = None
    imported_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class WorkloadItem:
    study_form: StudyForm
    source_row_number: int
    group_name: str | None
    discipline: str | None
    work_type: WorkType
    hours: Decimal
    semester: int | None = None
    session_period: SessionPeriod | None = None
    course: str | None = None
    stream: str | None = None
    student_count: int | None = None
    faculty: str | None = None
    control_type: str | None = None
    row_total_hours: Decimal | None = None
    is_idpo: bool = False
    raw_context: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    source_id: int | None = None
    teacher_id: int | None = None
    academic_year_id: int | None = None


@dataclass(slots=True)
class ImportWarning:
    code: WarningCode
    severity: WarningSeverity
    message: str
    source_row_number: int | None = None
    raw_value: str | None = None
    resolved: bool = False
    id: int | None = None
    source_id: int | None = None
    sheet_name: str | None = None


@dataclass(slots=True)
class HourlyCalculation:
    effective_rate: Decimal
    norm_hours: Decimal
    fact_hours: Decimal
    idpo_hours: Decimal
    net_hours: Decimal
    excess_hours: Decimal
    eligible_auditory_hours: Decimal
    hourly_limit: Decimal
    calculated_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class HourlySelection:
    workload_item_id: int
    selected_hours: Decimal
    id: int | None = None
    teacher_id: int | None = None
    prefer_evening: bool = False


@dataclass(slots=True)
class MonthlyAllocation:
    hourly_selection_id: int
    month: int
    year: int
    hours: Decimal
    id: int | None = None


@dataclass(slots=True)
class AvailabilityRule:
    rule_type: str
    weekday: int | None = None
    target_date: date | None = None
    allowed_slot_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class CalendarOverride:
    target_date: date
    is_working: bool


@dataclass(frozen=True, slots=True)
class SemesterPracticeStart:
    academic_year_id: int
    semester: int
    first_allowed_date: date


@dataclass(frozen=True, slots=True)
class TimeSlot:
    id: int
    sort_order: int
    start_time: time
    end_time: time
    display_text: str


@dataclass(slots=True)
class GenerationBatch:
    teacher_id: int
    year: int
    month: int
    seed: int | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class Lesson:
    teacher_id: int
    monthly_allocation_id: int
    lesson_date: date
    time_slot_id: int
    group_name: str
    discipline: str
    work_type: WorkType
    generation_batch_id: int | None
    hours: Decimal = Decimal("2")
    manual_override: bool = False
    id: int | None = None
    start_time: time | None = None
