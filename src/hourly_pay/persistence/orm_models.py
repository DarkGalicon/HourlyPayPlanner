from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AcademicYearRecord(Base):
    __tablename__ = "academic_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class TeacherRecord(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(300), index=True)
    imported_name: Mapped[str | None] = mapped_column(String(300), index=True)
    effective_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    department: Mapped[str | None] = mapped_column(String(500))
    degree: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[str | None] = mapped_column(String(300))
    birth_date: Mapped[date | None] = mapped_column()
    address: Mapped[str | None] = mapped_column(String(1000))
    passport_series: Mapped[str | None] = mapped_column(String(20))
    passport_number: Mapped[str | None] = mapped_column(String(30))
    passport_issued_by: Mapped[str | None] = mapped_column(String(1000))
    passport_issue_date: Mapped[date | None] = mapped_column()
    snils: Mapped[str | None] = mapped_column(String(30))
    inn: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class WorkloadSourceRecord(Base):
    __tablename__ = "workload_sources"
    __table_args__ = (Index("ix_workload_sources_file_sha256", "file_sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64))
    employment_type: Mapped[str] = mapped_column(String(300))
    reported_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reported_total_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    include_in_fact: Mapped[bool | None] = mapped_column(Boolean)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    parser_version: Mapped[str] = mapped_column(String(100))

    items: Mapped[list["WorkloadItemRecord"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    warnings: Mapped[list["ImportWarningRecord"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class WorkloadItemRecord(Base):
    __tablename__ = "workload_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("workload_sources.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id"), index=True)
    study_form: Mapped[str] = mapped_column(String(30))
    semester: Mapped[int | None] = mapped_column(Integer)
    session_period: Mapped[str | None] = mapped_column(String(30))
    source_row_number: Mapped[int] = mapped_column(Integer)
    group_name: Mapped[str | None] = mapped_column(String(300))
    course: Mapped[str | None] = mapped_column(String(50))
    stream: Mapped[str | None] = mapped_column(String(100))
    student_count: Mapped[int | None] = mapped_column(Integer)
    faculty: Mapped[str | None] = mapped_column(String(500))
    discipline: Mapped[str | None] = mapped_column(String(1000))
    work_type: Mapped[str] = mapped_column(String(50))
    control_type: Mapped[str | None] = mapped_column(String(100))
    hours: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    row_total_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    is_idpo: Mapped[bool] = mapped_column(Boolean)
    raw_context_json: Mapped[str] = mapped_column(Text, default="{}")

    source: Mapped[WorkloadSourceRecord] = relationship(back_populates="items")


class ImportWarningRecord(Base):
    __tablename__ = "import_warnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("workload_sources.id", ondelete="CASCADE"), index=True
    )
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(1000))
    raw_value: Mapped[str | None] = mapped_column(String(1000))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped[WorkloadSourceRecord] = relationship(back_populates="warnings")


class HourlySelectionRecord(Base):
    __tablename__ = "hourly_selections"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    workload_item_id: Mapped[int] = mapped_column(
        ForeignKey("workload_items.id", ondelete="CASCADE"), unique=True
    )
    selected_hours: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    prefer_evening: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class HourlyLimitPermissionRecord(Base):
    __tablename__ = "hourly_limit_permissions"

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True
    )
    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE"), primary_key=True
    )
    allow_limit_excess: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MonthlyAllocationRecord(Base):
    __tablename__ = "monthly_allocations"
    __table_args__ = (
        UniqueConstraint(
            "hourly_selection_id",
            "year",
            "month",
            name="uq_allocation_selection_month",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hourly_selection_id: Mapped[int] = mapped_column(
        ForeignKey("hourly_selections.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    hours: Mapped[Decimal] = mapped_column(Numeric(14, 4))


class TimeSlotRecord(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)
    start_time: Mapped[time] = mapped_column()
    end_time: Mapped[time] = mapped_column()
    display_text: Mapped[str] = mapped_column(String(50))


class TeacherAvailabilityRuleRecord(Base):
    __tablename__ = "teacher_availability_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    rule_type: Mapped[str] = mapped_column(String(50))
    weekday: Mapped[int | None] = mapped_column(Integer)
    target_date: Mapped[date | None] = mapped_column()
    allowed_slot_ids_json: Mapped[str] = mapped_column(Text, default="[]")


class CalendarOverrideRecord(Base):
    __tablename__ = "calendar_overrides"

    target_date: Mapped[date] = mapped_column(primary_key=True)
    is_working: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SemesterPracticeStartRecord(Base):
    __tablename__ = "semester_practice_starts"

    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE"), primary_key=True
    )
    semester: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_allowed_date: Mapped[date] = mapped_column(nullable=False)


class GenerationBatchRecord(Base):
    __tablename__ = "generation_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LessonRecord(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("teacher_id", "lesson_date", "time_slot_id", name="uq_lesson_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    monthly_allocation_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_allocations.id", ondelete="CASCADE"), index=True
    )
    lesson_date: Mapped[date] = mapped_column(index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id"))
    group_name: Mapped[str] = mapped_column(String(300))
    discipline: Mapped[str] = mapped_column(String(1000))
    work_type: Mapped[str] = mapped_column(String(50))
    hours: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    generation_batch_id: Mapped[int] = mapped_column(
        ForeignKey("generation_batches.id", ondelete="CASCADE"), index=True
    )
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
