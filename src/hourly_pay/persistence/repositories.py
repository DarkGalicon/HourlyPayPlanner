import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from hourly_pay.domain.enums import (
    SessionPeriod,
    StudyForm,
    WarningCode,
    WarningSeverity,
    WorkType,
)
from hourly_pay.domain.errors import (
    DuplicateImportError,
    InvalidMonthlyAllocationError,
    InvalidScheduleError,
    InvalidSelectionError,
    InvalidTeacherSettingsError,
)
from hourly_pay.domain.models import (
    AcademicYear,
    CalendarOverride,
    HourlySelection,
    ImportWarning,
    Lesson,
    MonthlyAllocation,
    SemesterPracticeStart,
    Teacher,
    TimeSlot,
    WorkloadItem,
    WorkloadSource,
)
from hourly_pay.importers.base import ImportResult, ImportTotals
from hourly_pay.persistence.orm_models import (
    AcademicYearRecord,
    CalendarOverrideRecord,
    GenerationBatchRecord,
    HourlyLimitPermissionRecord,
    HourlySelectionRecord,
    ImportWarningRecord,
    LessonRecord,
    MonthlyAllocationRecord,
    SemesterPracticeStartRecord,
    TeacherAvailabilityRuleRecord,
    TeacherRecord,
    TimeSlotRecord,
    WorkloadItemRecord,
    WorkloadSourceRecord,
)
from hourly_pay.scheduler.availability import (
    CalendarPolicy,
    TeacherAvailability,
    russian_holiday_dates,
)
from hourly_pay.scheduler.generator import ScheduleGenerationResult


@dataclass(frozen=True, slots=True)
class SavedImport:
    source_id: int
    teacher_id: int
    academic_year_id: int


@dataclass(frozen=True, slots=True)
class TeacherSourceSummary:
    academic_year: AcademicYear
    source: WorkloadSource


class WorkloadRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def known_hashes(self) -> set[str]:
        with self._session_factory() as session:
            return set(session.scalars(select(WorkloadSourceRecord.file_sha256)))

    def parser_versions_by_hash(self) -> dict[str, set[str]]:
        with self._session_factory() as session:
            versions: dict[str, set[str]] = {}
            for file_hash, parser_version in session.execute(
                select(WorkloadSourceRecord.file_sha256, WorkloadSourceRecord.parser_version)
            ):
                versions.setdefault(file_hash, set()).add(parser_version)
            return versions

    def list_teachers(self) -> tuple[Teacher, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(TeacherRecord).order_by(TeacherRecord.full_name, TeacherRecord.id)
            ).all()
            return tuple(
                Teacher(
                    id=record.id,
                    full_name=record.full_name,
                    effective_rate=record.effective_rate,
                    department=record.department,
                    degree=record.degree,
                    title=record.title,
                    position=record.position,
                    birth_date=record.birth_date,
                    address=record.address,
                    passport_series=record.passport_series,
                    passport_number=record.passport_number,
                    passport_issued_by=record.passport_issued_by,
                    passport_issue_date=record.passport_issue_date,
                    snils=record.snils,
                    inn=record.inn,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
                for record in records
            )

    def list_teacher_sources(self, teacher_id: int) -> tuple[TeacherSourceSummary, ...]:
        with self._session_factory() as session:
            rows = session.execute(
                select(WorkloadSourceRecord, AcademicYearRecord)
                .join(
                    AcademicYearRecord,
                    WorkloadSourceRecord.academic_year_id == AcademicYearRecord.id,
                )
                .where(WorkloadSourceRecord.teacher_id == teacher_id)
                .order_by(AcademicYearRecord.name, WorkloadSourceRecord.id)
            ).all()
            return tuple(
                TeacherSourceSummary(
                    academic_year=AcademicYear(
                        id=year.id,
                        name=year.name,
                        is_active=year.is_active,
                    ),
                    source=WorkloadSource(
                        id=source.id,
                        teacher_id=source.teacher_id,
                        academic_year_id=source.academic_year_id,
                        original_filename=source.original_filename,
                        file_sha256=source.file_sha256,
                        employment_type=source.employment_type,
                        reported_rate=source.reported_rate,
                        reported_total_hours=source.reported_total_hours,
                        include_in_fact=source.include_in_fact,
                        imported_at=source.imported_at,
                        parser_version=source.parser_version,
                    ),
                )
                for source, year in rows
            )

    def set_effective_rate(self, teacher_id: int, rate: Decimal) -> None:
        with self._session_factory.begin() as session:
            teacher = session.get(TeacherRecord, teacher_id)
            if teacher is None:
                raise InvalidTeacherSettingsError("Преподаватель не найден.")
            teacher.effective_rate = rate

    def set_personal_data(self, teacher_id: int, values: dict[str, object]) -> None:
        with self._session_factory.begin() as session:
            teacher = session.get(TeacherRecord, teacher_id)
            if teacher is None:
                raise InvalidTeacherSettingsError("Преподаватель не найден.")
            for field_name, value in values.items():
                setattr(teacher, field_name, value)

    def set_source_inclusions(
        self, teacher_id: int, inclusions: dict[int, bool | None]
    ) -> None:
        with self._session_factory.begin() as session:
            if session.get(TeacherRecord, teacher_id) is None:
                raise InvalidTeacherSettingsError("Преподаватель не найден.")
            if not inclusions:
                return
            records = tuple(
                session.scalars(
                    select(WorkloadSourceRecord).where(
                        WorkloadSourceRecord.id.in_(inclusions),
                        WorkloadSourceRecord.teacher_id == teacher_id,
                    )
                )
            )
            if {record.id for record in records} != set(inclusions):
                raise InvalidTeacherSettingsError(
                    "Один из выбранных источников не принадлежит преподавателю."
                )
            for record in records:
                record.include_in_fact = inclusions[record.id]

    def delete_source(self, teacher_id: int, source_id: int) -> None:
        with self._session_factory.begin() as session:
            source = session.get(WorkloadSourceRecord, source_id)
            if source is None or source.teacher_id != teacher_id:
                raise InvalidTeacherSettingsError("Источник не найден у преподавателя.")
            used = session.scalar(
                select(HourlySelectionRecord.id)
                .join(WorkloadItemRecord,
                      HourlySelectionRecord.workload_item_id == WorkloadItemRecord.id)
                .where(WorkloadItemRecord.source_id == source_id)
                .limit(1)
            )
            if used is not None:
                raise InvalidTeacherSettingsError(
                    "Источник используется в выборе нагрузки. Сначала уберите его часы "
                    "из выбора и помесячного плана; созданные занятия также нужно удалить."
                )
            session.delete(source)
            has_other_source = session.scalar(
                select(WorkloadSourceRecord.id)
                .where(
                    WorkloadSourceRecord.teacher_id == teacher_id,
                    WorkloadSourceRecord.academic_year_id == source.academic_year_id,
                    WorkloadSourceRecord.id != source_id,
                )
                .limit(1)
            )
            if has_other_source is None:
                permission = session.get(
                    HourlyLimitPermissionRecord,
                    (teacher_id, source.academic_year_id),
                )
                if permission is not None:
                    session.delete(permission)

    def save_import(
        self,
        result: ImportResult,
        *,
        allow_duplicate: bool = False,
    ) -> SavedImport:
        with self._session_factory.begin() as session:
            if not allow_duplicate and session.scalar(
                select(WorkloadSourceRecord.id)
                .where(WorkloadSourceRecord.file_sha256 == result.source.file_sha256)
                .limit(1)
            ):
                raise DuplicateImportError(result.source.file_sha256)

            academic_year = session.scalar(
                select(AcademicYearRecord).where(
                    AcademicYearRecord.name == result.academic_year.name
                )
            )
            if academic_year is None:
                academic_year = AcademicYearRecord(
                    name=result.academic_year.name,
                    is_active=result.academic_year.is_active,
                )
                session.add(academic_year)
                session.flush()

            teacher = session.scalar(
                select(TeacherRecord)
                .where(TeacherRecord.imported_name == result.teacher.full_name)
                .order_by(TeacherRecord.id)
                .limit(1)
            )
            if teacher is None:
                teacher = TeacherRecord(
                    full_name=result.teacher.full_name,
                    imported_name=result.teacher.full_name,
                    effective_rate=result.teacher.effective_rate,
                    department=result.teacher.department,
                    degree=result.teacher.degree,
                    title=result.teacher.title,
                    position=result.teacher.position,
                )
                session.add(teacher)
                session.flush()

            source = WorkloadSourceRecord(
                teacher_id=teacher.id,
                academic_year_id=academic_year.id,
                original_filename=result.source.original_filename,
                file_sha256=result.source.file_sha256,
                employment_type=result.source.employment_type,
                reported_rate=result.source.reported_rate,
                reported_total_hours=result.source.reported_total_hours,
                include_in_fact=result.source.include_in_fact,
                imported_at=result.source.imported_at,
                parser_version=result.source.parser_version,
            )
            session.add(source)
            session.flush()

            session.add_all(
                WorkloadItemRecord(
                    source_id=source.id,
                    teacher_id=teacher.id,
                    academic_year_id=academic_year.id,
                    study_form=item.study_form.value,
                    semester=item.semester,
                    session_period=(item.session_period.value if item.session_period else None),
                    source_row_number=item.source_row_number,
                    group_name=item.group_name,
                    course=item.course,
                    stream=item.stream,
                    student_count=item.student_count,
                    faculty=item.faculty,
                    discipline=item.discipline,
                    work_type=item.work_type.value,
                    control_type=item.control_type,
                    hours=item.hours,
                    row_total_hours=item.row_total_hours,
                    is_idpo=item.is_idpo,
                    raw_context_json=json.dumps(item.raw_context, ensure_ascii=False),
                )
                for item in result.items
            )
            session.add_all(
                ImportWarningRecord(
                    source_id=source.id,
                    source_row_number=warning.source_row_number,
                    sheet_name=warning.sheet_name,
                    code=warning.code.value,
                    severity=warning.severity.value,
                    message=warning.message,
                    raw_value=warning.raw_value,
                    resolved=warning.resolved,
                )
                for warning in result.warnings
            )
            return SavedImport(
                source_id=cast(int, source.id),
                teacher_id=cast(int, teacher.id),
                academic_year_id=cast(int, academic_year.id),
            )

    def get_import(self, source_id: int) -> ImportResult | None:
        with self._session_factory() as session:
            source = session.get(WorkloadSourceRecord, source_id)
            if source is None:
                return None
            teacher = session.get(TeacherRecord, source.teacher_id)
            academic_year = session.get(AcademicYearRecord, source.academic_year_id)
            if teacher is None or academic_year is None:
                raise RuntimeError("Нарушена целостность данных импортированной нагрузки.")
            item_records = session.scalars(
                select(WorkloadItemRecord)
                .where(WorkloadItemRecord.source_id == source_id)
                .order_by(WorkloadItemRecord.id)
            )
            warning_records = session.scalars(
                select(ImportWarningRecord)
                .where(ImportWarningRecord.source_id == source_id)
                .order_by(ImportWarningRecord.id)
            )
            items = [
                WorkloadItem(
                    id=item.id,
                    source_id=item.source_id,
                    teacher_id=item.teacher_id,
                    academic_year_id=item.academic_year_id,
                    study_form=StudyForm(item.study_form),
                    semester=item.semester,
                    session_period=(
                        SessionPeriod(item.session_period) if item.session_period else None
                    ),
                    source_row_number=item.source_row_number,
                    group_name=item.group_name,
                    course=item.course,
                    stream=item.stream,
                    student_count=item.student_count,
                    faculty=item.faculty,
                    discipline=item.discipline,
                    work_type=WorkType(item.work_type),
                    control_type=item.control_type,
                    hours=item.hours,
                    row_total_hours=item.row_total_hours,
                    is_idpo=item.is_idpo,
                    raw_context=json.loads(item.raw_context_json),
                )
                for item in item_records
            ]
            warnings = [
                ImportWarning(
                    id=warning.id,
                    source_id=warning.source_id,
                    source_row_number=warning.source_row_number,
                    sheet_name=warning.sheet_name,
                    code=WarningCode(warning.code),
                    severity=WarningSeverity(warning.severity),
                    message=warning.message,
                    raw_value=warning.raw_value,
                    resolved=warning.resolved,
                )
                for warning in warning_records
            ]
            return ImportResult(
                teacher=Teacher(
                    id=teacher.id,
                    full_name=teacher.full_name,
                    effective_rate=teacher.effective_rate,
                    department=teacher.department,
                    degree=teacher.degree,
                    title=teacher.title,
                    position=teacher.position,
                    birth_date=teacher.birth_date,
                    address=teacher.address,
                    passport_series=teacher.passport_series,
                    passport_number=teacher.passport_number,
                    passport_issued_by=teacher.passport_issued_by,
                    passport_issue_date=teacher.passport_issue_date,
                    snils=teacher.snils,
                    inn=teacher.inn,
                    created_at=teacher.created_at,
                    updated_at=teacher.updated_at,
                ),
                academic_year=AcademicYear(
                    id=academic_year.id,
                    name=academic_year.name,
                    is_active=academic_year.is_active,
                ),
                source=WorkloadSource(
                    id=source.id,
                    teacher_id=source.teacher_id,
                    academic_year_id=source.academic_year_id,
                    original_filename=source.original_filename,
                    file_sha256=source.file_sha256,
                    employment_type=source.employment_type,
                    reported_rate=source.reported_rate,
                    reported_total_hours=source.reported_total_hours,
                    include_in_fact=source.include_in_fact,
                    imported_at=source.imported_at,
                    parser_version=source.parser_version,
                ),
                items=items,
                warnings=warnings,
                summary_totals=ImportTotals(overall=source.reported_total_hours),
            )

    def source_count(self) -> int:
        with self._session_factory() as session:
            return len(tuple(session.scalars(select(WorkloadSourceRecord.id))))

    def item_count(self, source_id: int) -> int:
        with self._session_factory() as session:
            return len(
                tuple(
                    session.scalars(
                        select(WorkloadItemRecord.id).where(
                            WorkloadItemRecord.source_id == source_id
                        )
                    )
                )
            )

    def warning_count(self, source_id: int) -> int:
        with self._session_factory() as session:
            return len(
                tuple(
                    session.scalars(
                        select(ImportWarningRecord.id).where(
                            ImportWarningRecord.source_id == source_id
                        )
                    )
                )
            )


class HourlySelectionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def replace_for_teacher(
        self,
        teacher_id: int,
        selections: tuple[HourlySelection, ...],
    ) -> None:
        item_ids = [selection.workload_item_id for selection in selections]
        if len(item_ids) != len(set(item_ids)):
            raise InvalidSelectionError("Одна строка нагрузки выбрана несколько раз.")
        if any(
            selection.teacher_id not in (None, teacher_id) for selection in selections
        ):
            raise InvalidSelectionError("Выбор содержит данные другого преподавателя.")

        with self._session_factory.begin() as session:
            if item_ids:
                owned_ids = set(
                    session.scalars(
                        select(WorkloadItemRecord.id).where(
                            WorkloadItemRecord.id.in_(item_ids),
                            WorkloadItemRecord.teacher_id == teacher_id,
                        )
                    )
                )
                if owned_ids != set(item_ids):
                    raise InvalidSelectionError(
                        "Не все выбранные строки принадлежат указанному преподавателю."
                    )
            session.execute(
                delete(HourlySelectionRecord).where(
                    HourlySelectionRecord.teacher_id == teacher_id
                )
            )
            session.add_all(
                HourlySelectionRecord(
                    teacher_id=teacher_id,
                    workload_item_id=selection.workload_item_id,
                    selected_hours=selection.selected_hours,
                    prefer_evening=selection.prefer_evening,
                )
                for selection in selections
            )

    def list_for_teacher(self, teacher_id: int) -> tuple[HourlySelection, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(HourlySelectionRecord)
                .where(HourlySelectionRecord.teacher_id == teacher_id)
                .order_by(HourlySelectionRecord.id)
            )
            return tuple(
                HourlySelection(
                    id=record.id,
                    teacher_id=record.teacher_id,
                    workload_item_id=record.workload_item_id,
                    selected_hours=record.selected_hours,
                    prefer_evening=record.prefer_evening,
                )
                for record in records
            )

    def list_for_teacher_year(
        self, teacher_id: int, academic_year_id: int
    ) -> tuple[HourlySelection, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(HourlySelectionRecord)
                .join(
                    WorkloadItemRecord,
                    HourlySelectionRecord.workload_item_id == WorkloadItemRecord.id,
                )
                .where(
                    HourlySelectionRecord.teacher_id == teacher_id,
                    WorkloadItemRecord.academic_year_id == academic_year_id,
                )
                .order_by(HourlySelectionRecord.id)
            )
            return tuple(
                HourlySelection(
                    id=record.id,
                    teacher_id=record.teacher_id,
                    workload_item_id=record.workload_item_id,
                    selected_hours=record.selected_hours,
                    prefer_evening=record.prefer_evening,
                )
                for record in records
            )

    def get_allow_limit_excess(self, teacher_id: int, academic_year_id: int) -> bool:
        with self._session_factory() as session:
            record = session.get(
                HourlyLimitPermissionRecord, (teacher_id, academic_year_id)
            )
            return bool(record and record.allow_limit_excess)

    def replace_for_teacher_year(
        self,
        teacher_id: int,
        academic_year_id: int,
        selections: tuple[HourlySelection, ...],
        allow_limit_excess: bool = False,
    ) -> None:
        requested = {item.workload_item_id: item for item in selections}
        if len(requested) != len(selections):
            raise InvalidSelectionError("Одна строка нагрузки выбрана несколько раз.")
        if any(item.teacher_id not in (None, teacher_id) for item in selections):
            raise InvalidSelectionError("Выбор содержит данные другого преподавателя.")

        with self._session_factory.begin() as session:
            item_ids = set(requested)
            owned_ids = set(
                session.scalars(
                    select(WorkloadItemRecord.id).where(
                        WorkloadItemRecord.id.in_(item_ids),
                        WorkloadItemRecord.teacher_id == teacher_id,
                        WorkloadItemRecord.academic_year_id == academic_year_id,
                    )
                )
            )
            if owned_ids != item_ids:
                raise InvalidSelectionError(
                    "Не все выбранные строки принадлежат преподавателю и учебному году."
                )

            existing = {
                record.workload_item_id: record
                for record in session.scalars(
                    select(HourlySelectionRecord)
                    .join(
                        WorkloadItemRecord,
                        HourlySelectionRecord.workload_item_id == WorkloadItemRecord.id,
                    )
                    .where(
                        HourlySelectionRecord.teacher_id == teacher_id,
                        WorkloadItemRecord.academic_year_id == academic_year_id,
                    )
                )
            }
            changed_ids = {
                record.id
                for item_id, record in existing.items()
                if item_id not in requested
                or record.selected_hours != requested[item_id].selected_hours
            }
            if changed_ids and session.scalar(
                select(MonthlyAllocationRecord.id)
                .where(MonthlyAllocationRecord.hourly_selection_id.in_(changed_ids))
                .limit(1)
            ) is not None:
                raise InvalidSelectionError(
                    "У изменяемого выбора уже есть помесячное распределение. "
                    "Сначала удалите или измените его."
                )
            for item_id, record in existing.items():
                selection = requested.get(item_id)
                if selection is None:
                    session.delete(record)
                else:
                    record.selected_hours = selection.selected_hours
                    record.prefer_evening = selection.prefer_evening
            session.add_all(
                HourlySelectionRecord(
                    teacher_id=teacher_id,
                    workload_item_id=item_id,
                    selected_hours=selection.selected_hours,
                    prefer_evening=selection.prefer_evening,
                )
                for item_id, selection in requested.items()
                if item_id not in existing
            )
            permission = session.get(
                HourlyLimitPermissionRecord, (teacher_id, academic_year_id)
            )
            if permission is None:
                session.add(HourlyLimitPermissionRecord(
                    teacher_id=teacher_id,
                    academic_year_id=academic_year_id,
                    allow_limit_excess=allow_limit_excess,
                ))
            else:
                permission.allow_limit_excess = allow_limit_excess


class MonthlyAllocationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def replace_for_selection(
        self,
        selection_id: int,
        allocations: tuple[MonthlyAllocation, ...],
    ) -> None:
        if any(
            allocation.hourly_selection_id != selection_id for allocation in allocations
        ):
            raise InvalidMonthlyAllocationError(
                "Распределение относится к другому выбору нагрузки."
            )
        month_keys = [(allocation.year, allocation.month) for allocation in allocations]
        if len(month_keys) != len(set(month_keys)):
            raise InvalidMonthlyAllocationError(
                "Один месяц указан в распределении несколько раз."
            )

        with self._session_factory.begin() as session:
            if session.get(HourlySelectionRecord, selection_id) is None:
                raise InvalidMonthlyAllocationError(
                    "Выбор нагрузки для распределения не найден."
                )
            session.execute(
                delete(MonthlyAllocationRecord).where(
                    MonthlyAllocationRecord.hourly_selection_id == selection_id
                )
            )
            session.add_all(
                MonthlyAllocationRecord(
                    hourly_selection_id=selection_id,
                    month=allocation.month,
                    year=allocation.year,
                    hours=allocation.hours,
                )
                for allocation in allocations
            )

    def replace_plans(
        self, plans: tuple[tuple[int, tuple[MonthlyAllocation, ...]], ...]
    ) -> None:
        selection_ids = [selection_id for selection_id, _ in plans]
        if len(selection_ids) != len(set(selection_ids)):
            raise InvalidMonthlyAllocationError("Один выбор нагрузки передан несколько раз.")
        for selection_id, allocations in plans:
            keys = [(entry.year, entry.month) for entry in allocations]
            if any(entry.hourly_selection_id != selection_id for entry in allocations):
                raise InvalidMonthlyAllocationError(
                    "Распределение относится к другому выбору нагрузки."
                )
            if len(keys) != len(set(keys)):
                raise InvalidMonthlyAllocationError("Один месяц указан несколько раз.")

        with self._session_factory.begin() as session:
            owned_ids = set(
                session.scalars(
                    select(HourlySelectionRecord.id).where(
                        HourlySelectionRecord.id.in_(selection_ids)
                    )
                )
            )
            if owned_ids != set(selection_ids):
                raise InvalidMonthlyAllocationError("Один из выбранных планов не найден.")
            for selection_id, allocations in plans:
                requested = {(entry.year, entry.month): entry for entry in allocations}
                existing = {
                    (record.year, record.month): record
                    for record in session.scalars(
                        select(MonthlyAllocationRecord).where(
                            MonthlyAllocationRecord.hourly_selection_id == selection_id
                        )
                    )
                }
                changed_ids = {
                    record.id
                    for key, record in existing.items()
                    if key not in requested or record.hours != requested[key].hours
                }
                if changed_ids and session.scalar(
                    select(LessonRecord.id)
                    .where(LessonRecord.monthly_allocation_id.in_(changed_ids))
                    .limit(1)
                ) is not None:
                    raise InvalidMonthlyAllocationError(
                        "По изменяемым месяцам уже созданы занятия. "
                        "Сначала удалите или перегенерируйте их."
                    )
                for key, record in existing.items():
                    allocation = requested.get(key)
                    if allocation is None:
                        session.delete(record)
                    else:
                        record.hours = allocation.hours
                session.add_all(
                    MonthlyAllocationRecord(
                        hourly_selection_id=selection_id,
                        month=entry.month,
                        year=entry.year,
                        hours=entry.hours,
                    )
                    for key, entry in requested.items()
                    if key not in existing
                )

    def clear_for_selections(self, selection_ids: tuple[int, ...]) -> None:
        if not selection_ids:
            return
        with self._session_factory.begin() as session:
            allocation_ids = set(
                session.scalars(
                    select(MonthlyAllocationRecord.id).where(
                        MonthlyAllocationRecord.hourly_selection_id.in_(selection_ids)
                    )
                )
            )
            if allocation_ids and session.scalar(
                select(LessonRecord.id)
                .where(LessonRecord.monthly_allocation_id.in_(allocation_ids))
                .limit(1)
            ) is not None:
                raise InvalidMonthlyAllocationError(
                    "По плану уже созданы занятия. Сначала удалите или перегенерируйте их."
                )
            session.execute(
                delete(MonthlyAllocationRecord).where(
                    MonthlyAllocationRecord.hourly_selection_id.in_(selection_ids)
                )
            )

    def list_for_selection(self, selection_id: int) -> tuple[MonthlyAllocation, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(MonthlyAllocationRecord)
                .where(MonthlyAllocationRecord.hourly_selection_id == selection_id)
                .order_by(MonthlyAllocationRecord.year, MonthlyAllocationRecord.month)
            )
            return tuple(
                MonthlyAllocation(
                    id=record.id,
                    hourly_selection_id=record.hourly_selection_id,
                    month=record.month,
                    year=record.year,
                    hours=record.hours,
                )
                for record in records
            )


class ScheduleRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_time_slots(self) -> tuple[TimeSlot, ...]:
        with self._session_factory() as session:
            records = session.scalars(select(TimeSlotRecord).order_by(TimeSlotRecord.sort_order))
            return tuple(
                TimeSlot(
                    id=record.id,
                    sort_order=record.sort_order,
                    start_time=record.start_time,
                    end_time=record.end_time,
                    display_text=record.display_text,
                )
                for record in records
            )

    def replace_availability(
        self, teacher_id: int, availability: TeacherAvailability
    ) -> None:
        with self._session_factory.begin() as session:
            if session.get(TeacherRecord, teacher_id) is None:
                raise InvalidScheduleError("Преподаватель для настройки доступности не найден.")
            known_slot_ids = set(session.scalars(select(TimeSlotRecord.id)))
            supplied_slot_ids = {
                slot_id
                for values in (
                    *availability.weekday_allowed_slots.values(),
                    *availability.per_date_allowed_slots.values(),
                )
                for slot_id in values
            }
            if not supplied_slot_ids <= known_slot_ids:
                raise InvalidScheduleError("Доступность содержит неизвестные временные слоты.")
            lessons = tuple(
                session.scalars(
                    select(LessonRecord).where(LessonRecord.teacher_id == teacher_id)
                )
            )
            if any(
                lesson.time_slot_id not in availability.allowed_slots(lesson.lesson_date)
                for lesson in lessons
            ):
                raise InvalidScheduleError(
                    "Новая доступность исключает уже сохранённые занятия. "
                    "Сначала измените или удалите эти занятия."
                )
            session.execute(
                delete(TeacherAvailabilityRuleRecord).where(
                    TeacherAvailabilityRuleRecord.teacher_id == teacher_id
                )
            )
            records = [
                TeacherAvailabilityRuleRecord(
                    teacher_id=teacher_id,
                    rule_type="WEEKDAY_ALLOWED_SLOTS",
                    weekday=weekday,
                    target_date=None,
                    allowed_slot_ids_json=json.dumps(sorted(slot_ids)),
                )
                for weekday, slot_ids in availability.weekday_allowed_slots.items()
            ]
            records.extend(
                TeacherAvailabilityRuleRecord(
                    teacher_id=teacher_id,
                    rule_type="EXCLUDED_DATE",
                    weekday=None,
                    target_date=target_date,
                    allowed_slot_ids_json="[]",
                )
                for target_date in availability.excluded_dates
            )
            records.extend(
                TeacherAvailabilityRuleRecord(
                    teacher_id=teacher_id,
                    rule_type="DATE_ALLOWED_SLOTS",
                    weekday=None,
                    target_date=target_date,
                    allowed_slot_ids_json=json.dumps(sorted(slot_ids)),
                )
                for target_date, slot_ids in availability.per_date_allowed_slots.items()
            )
            session.add_all(records)

    def get_availability(self, teacher_id: int) -> TeacherAvailability:
        with self._session_factory() as session:
            records = tuple(
                session.scalars(
                    select(TeacherAvailabilityRuleRecord).where(
                        TeacherAvailabilityRuleRecord.teacher_id == teacher_id
                    )
                )
            )
        weekdays: dict[int, frozenset[int]] = {}
        excluded_dates = set()
        per_date: dict[date, frozenset[int]] = {}
        for record in records:
            slot_ids = frozenset(json.loads(record.allowed_slot_ids_json))
            if record.rule_type == "WEEKDAY_ALLOWED_SLOTS" and record.weekday is not None:
                weekdays[record.weekday] = slot_ids
            elif record.rule_type == "EXCLUDED_DATE" and record.target_date is not None:
                excluded_dates.add(record.target_date)
            elif record.rule_type == "DATE_ALLOWED_SLOTS" and record.target_date is not None:
                per_date[record.target_date] = slot_ids
        return TeacherAvailability(
            weekday_allowed_slots=weekdays,
            excluded_dates=frozenset(excluded_dates),
            per_date_allowed_slots=per_date,
        )

    def clear_month_schedule(self, *, teacher_id: int, year: int, month: int) -> int:
        with self._session_factory.begin() as session:
            batch_ids = tuple(session.scalars(
                select(GenerationBatchRecord.id).where(
                    GenerationBatchRecord.teacher_id == teacher_id,
                    GenerationBatchRecord.year == year,
                    GenerationBatchRecord.month == month,
                )
            ))
            if not batch_ids:
                return 0
            lesson_count = session.query(LessonRecord).filter(
                LessonRecord.generation_batch_id.in_(batch_ids)
            ).count()
            session.execute(
                delete(GenerationBatchRecord).where(GenerationBatchRecord.id.in_(batch_ids))
            )
            return lesson_count

    def move_lesson(
        self, *, teacher_id: int, year: int, month: int,
        lesson_id: int, lesson_date: date, time_slot_id: int,
    ) -> None:
        with self._session_factory.begin() as session:
            record = session.get(LessonRecord, lesson_id)
            batch = (
                session.get(GenerationBatchRecord, record.generation_batch_id)
                if record is not None else None
            )
            if (
                record is None or batch is None or record.teacher_id != teacher_id
                or (batch.year, batch.month) != (year, month)
            ):
                raise InvalidScheduleError("Занятие не найдено в выбранном месяце.")
            if (lesson_date.year, lesson_date.month) != (year, month):
                raise InvalidScheduleError(
                    "Занятие можно перенести только внутри выбранного месяца."
                )
            if session.get(TimeSlotRecord, time_slot_id) is None:
                raise InvalidScheduleError("Выбранный временной слот не найден.")
            conflict = session.scalar(
                select(LessonRecord.id).where(
                    LessonRecord.teacher_id == teacher_id,
                    LessonRecord.lesson_date == lesson_date,
                    LessonRecord.time_slot_id == time_slot_id,
                    LessonRecord.id != lesson_id,
                ).limit(1)
            )
            if conflict is not None:
                raise InvalidScheduleError("В выбранную дату временной слот уже занят.")
            record.lesson_date = lesson_date
            record.time_slot_id = time_slot_id
            record.manual_override = True

    def replace_month_schedule(
        self,
        result: ScheduleGenerationResult,
        *,
        allow_replace_manual: bool = False,
    ) -> int:
        batch = result.batch
        with self._session_factory.begin() as session:
            batch_ids = tuple(
                session.scalars(
                    select(GenerationBatchRecord.id).where(
                        GenerationBatchRecord.teacher_id == batch.teacher_id,
                        GenerationBatchRecord.year == batch.year,
                        GenerationBatchRecord.month == batch.month,
                    )
                )
            )
            if batch_ids and not allow_replace_manual and session.scalar(
                select(LessonRecord.id)
                .where(
                    LessonRecord.generation_batch_id.in_(batch_ids),
                    LessonRecord.manual_override.is_(True),
                )
                .limit(1)
            ):
                raise InvalidScheduleError(
                    "Расписание содержит ручные изменения; подтвердите перегенерацию."
                )

            allocation_ids = {lesson.monthly_allocation_id for lesson in result.lessons}
            valid_allocation_ids = set(
                session.scalars(
                    select(MonthlyAllocationRecord.id)
                    .join(
                        HourlySelectionRecord,
                        MonthlyAllocationRecord.hourly_selection_id
                        == HourlySelectionRecord.id,
                    )
                    .where(
                        MonthlyAllocationRecord.id.in_(allocation_ids),
                        HourlySelectionRecord.teacher_id == batch.teacher_id,
                    )
                )
            )
            if valid_allocation_ids != allocation_ids:
                raise InvalidScheduleError(
                    "Не все распределения принадлежат указанному преподавателю."
                )
            known_slot_ids = set(session.scalars(select(TimeSlotRecord.id)))
            if any(lesson.time_slot_id not in known_slot_ids for lesson in result.lessons):
                raise InvalidScheduleError("Расписание содержит неизвестный временной слот.")

            if batch_ids:
                session.execute(
                    delete(GenerationBatchRecord).where(
                        GenerationBatchRecord.id.in_(batch_ids)
                    )
                )
                session.flush()
            record = GenerationBatchRecord(
                teacher_id=batch.teacher_id,
                year=batch.year,
                month=batch.month,
                seed=batch.seed,
                created_at=batch.created_at,
            )
            session.add(record)
            session.flush()
            session.add_all(
                LessonRecord(
                    teacher_id=lesson.teacher_id,
                    monthly_allocation_id=lesson.monthly_allocation_id,
                    lesson_date=lesson.lesson_date,
                    time_slot_id=lesson.time_slot_id,
                    group_name=lesson.group_name,
                    discipline=lesson.discipline,
                    work_type=lesson.work_type.value,
                    hours=lesson.hours,
                    generation_batch_id=record.id,
                    manual_override=lesson.manual_override,
                )
                for lesson in result.lessons
            )
            return cast(int, record.id)

    def list_month_lessons(
        self, *, teacher_id: int, year: int, month: int
    ) -> tuple[Lesson, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(LessonRecord)
                .join(
                    GenerationBatchRecord,
                    LessonRecord.generation_batch_id == GenerationBatchRecord.id,
                )
                .where(
                    LessonRecord.teacher_id == teacher_id,
                    GenerationBatchRecord.year == year,
                    GenerationBatchRecord.month == month,
                )
                .order_by(LessonRecord.lesson_date, LessonRecord.time_slot_id)
            )
            return tuple(
                Lesson(
                    id=record.id,
                    teacher_id=record.teacher_id,
                    monthly_allocation_id=record.monthly_allocation_id,
                    lesson_date=record.lesson_date,
                    time_slot_id=record.time_slot_id,
                    group_name=record.group_name,
                    discipline=record.discipline,
                    work_type=WorkType(record.work_type),
                    hours=record.hours,
                    generation_batch_id=record.generation_batch_id,
                    manual_override=record.manual_override,
                )
                for record in records
            )


class CalendarOverrideRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_overrides(self) -> tuple[CalendarOverride, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(CalendarOverrideRecord).order_by(CalendarOverrideRecord.target_date)
            )
            return tuple(
                CalendarOverride(target_date=record.target_date, is_working=record.is_working)
                for record in records
            )

    def replace_overrides(self, overrides: tuple[CalendarOverride, ...]) -> None:
        targets = [entry.target_date for entry in overrides]
        if len(targets) != len(set(targets)):
            raise InvalidScheduleError("Одна календарная дата указана несколько раз.")
        excluded = frozenset(entry.target_date for entry in overrides if not entry.is_working)
        working = frozenset(entry.target_date for entry in overrides if entry.is_working)
        with self._session_factory.begin() as session:
            lesson_dates = tuple(session.scalars(select(LessonRecord.lesson_date)))
            policy = CalendarPolicy(
                base_holidays=russian_holiday_dates({value.year for value in lesson_dates}),
                excluded_dates=excluded,
                working_overrides=working,
            )
            invalid_dates = sorted(
                {value for value in lesson_dates if not policy.is_working_date(value)}
            )
            if invalid_dates:
                rendered = ", ".join(value.strftime("%d.%m.%Y") for value in invalid_dates[:3])
                raise InvalidScheduleError(
                    "Новый календарь исключает уже сохранённые занятия: "
                    f"{rendered}. Сначала измените или удалите эти занятия."
                )
            session.execute(delete(CalendarOverrideRecord))
            session.add_all(
                CalendarOverrideRecord(
                    target_date=entry.target_date,
                    is_working=entry.is_working,
                )
                for entry in overrides
            )


class SemesterStartRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_years(self) -> tuple[AcademicYear, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(AcademicYearRecord).order_by(AcademicYearRecord.name.desc())
            )
            return tuple(
                AcademicYear(name=record.name, is_active=record.is_active, id=record.id)
                for record in records
            )

    def get(self, academic_year_id: int, semester: int) -> SemesterPracticeStart | None:
        with self._session_factory() as session:
            record = session.get(SemesterPracticeStartRecord, (academic_year_id, semester))
            if record is None:
                return None
            return SemesterPracticeStart(
                academic_year_id=record.academic_year_id,
                semester=record.semester,
                first_allowed_date=record.first_allowed_date,
            )

    def save(self, academic_year_id: int, semester: int, value: date | None) -> None:
        with self._session_factory.begin() as session:
            lesson_dates = session.scalars(
                select(LessonRecord.lesson_date)
                .join(MonthlyAllocationRecord)
                .join(HourlySelectionRecord)
                .join(WorkloadItemRecord)
                .where(
                    WorkloadItemRecord.academic_year_id == academic_year_id,
                    LessonRecord.work_type.in_(
                        (WorkType.PRACTICE.value, WorkType.LAB.value)
                    ),
                )
            )
            conflicting = sorted(
                lesson_date for lesson_date in lesson_dates
                if (1 if lesson_date.month >= 9 else 2) == semester
                and (value is None or lesson_date < value)
            )
            if conflicting:
                raise InvalidScheduleError(
                    "Новая дата допуска противоречит сохранённым практикам/лабораторным "
                    f"от {conflicting[0]:%d.%m.%Y}. Сначала измените расписание."
                )
            record = session.get(SemesterPracticeStartRecord, (academic_year_id, semester))
            if value is None:
                if record is not None:
                    session.delete(record)
            elif record is None:
                session.add(
                    SemesterPracticeStartRecord(
                        academic_year_id=academic_year_id,
                        semester=semester,
                        first_allowed_date=value,
                    )
                )
            else:
                record.first_allowed_date = value
