"""Add scheduler configuration and generated lessons.

Revision ID: 0004_scheduler
Revises: 0003_monthly_allocations
"""

from collections.abc import Sequence
from datetime import time

import sqlalchemy as sa
from alembic import op

revision: str = "0004_scheduler"
down_revision: str | None = "0003_monthly_allocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    time_slots = op.create_table(
        "time_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("display_text", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sort_order"),
    )
    op.bulk_insert(
        time_slots,
        [
            {
                "id": slot_id,
                "sort_order": slot_id,
                "start_time": start,
                "end_time": end,
                "display_text": display,
            }
            for slot_id, start, end, display in (
                (1, time(8, 30), time(10, 5), "08:30-10:05"),
                (2, time(10, 15), time(11, 50), "10:15-11:50"),
                (3, time(12, 40), time(14, 15), "12:40-14:15"),
                (4, time(14, 25), time(16, 0), "14:25-16:00"),
                (5, time(16, 10), time(17, 45), "16:10-17:45"),
                (6, time(17, 55), time(19, 30), "17:55-19:30"),
                (7, time(19, 40), time(21, 15), "19:40-21:15"),
            )
        ],
    )
    op.create_table(
        "teacher_availability_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("allowed_slot_ids_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_availability_rules_teacher_id",
        "teacher_availability_rules",
        ["teacher_id"],
    )
    op.create_table(
        "generation_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_batches_teacher_id", "generation_batches", ["teacher_id"])
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("monthly_allocation_id", sa.Integer(), nullable=False),
        sa.Column("lesson_date", sa.Date(), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=300), nullable=False),
        sa.Column("discipline", sa.String(length=1000), nullable=False),
        sa.Column("work_type", sa.String(length=50), nullable=False),
        sa.Column("hours", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("generation_batch_id", sa.Integer(), nullable=False),
        sa.Column("manual_override", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_batch_id"], ["generation_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["monthly_allocation_id"], ["monthly_allocations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["time_slot_id"], ["time_slots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("teacher_id", "lesson_date", "time_slot_id", name="uq_lesson_slot"),
    )
    op.create_index("ix_lessons_generation_batch_id", "lessons", ["generation_batch_id"])
    op.create_index("ix_lessons_lesson_date", "lessons", ["lesson_date"])
    op.create_index("ix_lessons_monthly_allocation_id", "lessons", ["monthly_allocation_id"])
    op.create_index("ix_lessons_teacher_id", "lessons", ["teacher_id"])


def downgrade() -> None:
    op.drop_index("ix_lessons_teacher_id", table_name="lessons")
    op.drop_index("ix_lessons_monthly_allocation_id", table_name="lessons")
    op.drop_index("ix_lessons_lesson_date", table_name="lessons")
    op.drop_index("ix_lessons_generation_batch_id", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_generation_batches_teacher_id", table_name="generation_batches")
    op.drop_table("generation_batches")
    op.drop_index(
        "ix_teacher_availability_rules_teacher_id",
        table_name="teacher_availability_rules",
    )
    op.drop_table("teacher_availability_rules")
    op.drop_table("time_slots")
