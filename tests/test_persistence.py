from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text

from hourly_pay.domain.allocation import build_monthly_allocation_plan
from hourly_pay.domain.errors import DuplicateImportError, InvalidScheduleError
from hourly_pay.domain.selection import build_selection_plan
from hourly_pay.importers.nagr_xlsx_v1 import NagrXlsxV1Importer
from hourly_pay.persistence.db import (
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from hourly_pay.persistence.orm_models import (
    AcademicYearRecord,
    HourlySelectionRecord,
    LessonRecord,
    MonthlyAllocationRecord,
    TeacherRecord,
    WorkloadItemRecord,
)
from hourly_pay.persistence.repositories import (
    HourlySelectionRepository,
    MonthlyAllocationRepository,
    ScheduleRepository,
    WorkloadRepository,
)
from hourly_pay.scheduler.availability import TeacherAvailability
from hourly_pay.scheduler.generator import ScheduledAllocation, generate_schedule


def _repository(path: Path) -> tuple[WorkloadRepository, Engine]:
    upgrade_database(path)
    engine = create_sqlite_engine(path)
    return WorkloadRepository(create_session_factory(engine)), engine


def test_initial_migration_is_repeatable(tmp_path: Path) -> None:
    database = tmp_path / "planner.db"
    upgrade_database(database)
    upgrade_database(database)
    engine = create_sqlite_engine(database)

    assert set(inspect(engine).get_table_names()) >= {
        "alembic_version",
        "academic_years",
        "teachers",
        "workload_sources",
        "workload_items",
        "import_warnings",
        "hourly_selections",
        "monthly_allocations",
        "time_slots",
        "teacher_availability_rules",
        "generation_batches",
        "lessons",
        "semester_practice_starts",
    }
    engine.dispose()


def test_existing_teacher_survives_personal_data_migration(tmp_path: Path) -> None:
    database = tmp_path / "previous.db"
    config = Config()
    migrations = Path(__file__).resolve().parents[1] / "src/hourly_pay/persistence/migrations"
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, "0008_hourly_limit_permission")
    engine = create_sqlite_engine(database)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO teachers (full_name, created_at, updated_at) "
            "VALUES ('Тестов Т.Т.', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    engine.dispose()

    upgrade_database(database)
    repository = WorkloadRepository(create_session_factory(create_sqlite_engine(database)))
    teacher = repository.list_teachers()[0]
    assert teacher.full_name == "Тестов Т.Т."
    assert teacher.birth_date is None
    with create_sqlite_engine(database).connect() as connection:
        assert connection.scalar(text("SELECT imported_name FROM teachers")) == "Тестов Т.Т."


def test_hourly_selection_is_replaced_transactionally(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    result = NagrXlsxV1Importer().import_file(synthetic_workbook)
    workload_repository, engine = _repository(tmp_path / "planner.db")
    saved = workload_repository.save_import(result)
    restored = workload_repository.get_import(saved.source_id)
    assert restored is not None
    eligible_item = next(
        item
        for item in restored.items
        if item.work_type.value == "LECTURE" and not item.is_idpo
    )
    assert eligible_item.id is not None
    plan = build_selection_plan(
        items=restored.items,
        requested_hours={eligible_item.id: Decimal("2")},
        hourly_limit=Decimal("10"),
        teacher_id=saved.teacher_id,
    )
    repository = HourlySelectionRepository(create_session_factory(engine))

    repository.replace_for_teacher(saved.teacher_id, plan.selections)
    stored = repository.list_for_teacher(saved.teacher_id)
    assert len(stored) == 1
    assert stored[0].selected_hours == Decimal("2.0000")

    allocation_plan = build_monthly_allocation_plan(
        selection=stored[0],
        item=eligible_item,
        academic_year=restored.academic_year,
        monthly_hours={9: Decimal("2")},
    )
    allocation_repository = MonthlyAllocationRepository(create_session_factory(engine))
    assert stored[0].id is not None
    selection_id = stored[0].id
    assert isinstance(selection_id, int)
    allocation_repository.replace_for_selection(
        selection_id, allocation_plan.allocations
    )
    allocations = allocation_repository.list_for_selection(selection_id)
    assert len(allocations) == 1
    assert allocations[0].hours == Decimal("2.0000")

    schedule_repository = ScheduleRepository(create_session_factory(engine))
    assert len(schedule_repository.list_time_slots()) == 7
    availability = TeacherAvailability(
        weekday_allowed_slots={day: frozenset({1}) for day in range(5)}
    )
    schedule_repository.replace_availability(saved.teacher_id, availability)
    assert schedule_repository.get_availability(saved.teacher_id) == availability
    generated = generate_schedule(
        teacher_id=saved.teacher_id,
        year=2026,
        month=9,
        allocations=[
            ScheduledAllocation(
                allocation=allocations[0],
                group_name=eligible_item.group_name or "ГРУППА",
                discipline=eligible_item.discipline or "Дисциплина",
                work_type=eligible_item.work_type,
            )
        ],
        availability=availability,
        seed=5,
    )
    schedule_repository.replace_month_schedule(generated)
    lessons = schedule_repository.list_month_lessons(
        teacher_id=saved.teacher_id, year=2026, month=9
    )
    assert len(lessons) == 1
    assert lessons[0].hours == Decimal("2.0000")

    with create_session_factory(engine).begin() as session:
        lesson_record = session.scalar(select(LessonRecord))
        assert lesson_record is not None
        lesson_record.manual_override = True
    with pytest.raises(InvalidScheduleError, match="ручные изменения"):
        schedule_repository.replace_month_schedule(generated)
    schedule_repository.replace_month_schedule(generated, allow_replace_manual=True)

    repository.replace_for_teacher(saved.teacher_id, ())
    assert repository.list_for_teacher(saved.teacher_id) == ()
    with create_session_factory(engine)() as session:
        assert len(tuple(session.scalars(select(HourlySelectionRecord.id)))) == 0
        assert len(tuple(session.scalars(select(MonthlyAllocationRecord.id)))) == 0
        assert len(tuple(session.scalars(select(LessonRecord.id)))) == 0
    engine.dispose()


def test_import_is_saved_transactionally_with_decimal_values(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    result = NagrXlsxV1Importer().import_file(synthetic_workbook)
    repository, engine = _repository(tmp_path / "planner.db")

    saved = repository.save_import(result)

    assert repository.source_count() == 1
    assert repository.item_count(saved.source_id) == len(result.items)
    assert repository.warning_count(saved.source_id) == len(result.warnings)
    assert repository.known_hashes() == {result.source.file_sha256}
    restored = repository.get_import(saved.source_id)
    assert restored is not None
    assert restored.teacher.full_name == result.teacher.full_name
    assert restored.normalized_hours == Decimal("8.0000")
    assert restored.items[0].raw_context == result.items[0].raw_context
    with create_session_factory(engine)() as session:
        hours = list(
            session.scalars(
                select(WorkloadItemRecord.hours).where(
                    WorkloadItemRecord.source_id == saved.source_id
                )
            )
        )
        assert all(isinstance(value, Decimal) for value in hours)
        assert sum(hours, start=Decimal("0")) == Decimal("8.0000")
        assert len(tuple(session.scalars(select(TeacherRecord.id)))) == 1
        assert len(tuple(session.scalars(select(AcademicYearRecord.id)))) == 1
    engine.dispose()


def test_duplicate_is_blocked_by_default_and_explicitly_repeatable(
    tmp_path: Path, synthetic_workbook: Path
) -> None:
    result = NagrXlsxV1Importer().import_file(synthetic_workbook)
    repository, engine = _repository(tmp_path / "planner.db")
    repository.save_import(result)

    with pytest.raises(DuplicateImportError, match="Этот файл уже импортирован"):
        repository.save_import(result)
    assert repository.source_count() == 1

    repository.save_import(result, allow_duplicate=True)
    assert repository.source_count() == 2
    with create_session_factory(engine)() as session:
        assert len(tuple(session.scalars(select(TeacherRecord.id)))) == 1
        assert len(tuple(session.scalars(select(AcademicYearRecord.id)))) == 1
    engine.dispose()
