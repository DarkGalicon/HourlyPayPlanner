"""Create import persistence tables.

Revision ID: 0001_initial
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "academic_years",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "teachers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=300), nullable=False),
        sa.Column("effective_rate", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("department", sa.String(length=500), nullable=True),
        sa.Column("degree", sa.String(length=300), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("position", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teachers_full_name", "teachers", ["full_name"])
    op.create_table(
        "workload_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("employment_type", sa.String(length=300), nullable=False),
        sa.Column("reported_rate", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("reported_total_hours", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("include_in_fact", sa.Boolean(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workload_sources_academic_year_id", "workload_sources", ["academic_year_id"]
    )
    op.create_index("ix_workload_sources_file_sha256", "workload_sources", ["file_sha256"])
    op.create_index("ix_workload_sources_teacher_id", "workload_sources", ["teacher_id"])
    op.create_table(
        "import_warnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(length=100), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("raw_value", sa.String(length=1000), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["workload_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_warnings_source_id", "import_warnings", ["source_id"])
    op.create_table(
        "workload_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), nullable=False),
        sa.Column("study_form", sa.String(length=30), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("session_period", sa.String(length=30), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=300), nullable=True),
        sa.Column("course", sa.String(length=50), nullable=True),
        sa.Column("stream", sa.String(length=100), nullable=True),
        sa.Column("student_count", sa.Integer(), nullable=True),
        sa.Column("faculty", sa.String(length=500), nullable=True),
        sa.Column("discipline", sa.String(length=1000), nullable=True),
        sa.Column("work_type", sa.String(length=50), nullable=False),
        sa.Column("control_type", sa.String(length=100), nullable=True),
        sa.Column("hours", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("row_total_hours", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("is_idpo", sa.Boolean(), nullable=False),
        sa.Column("raw_context_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"]),
        sa.ForeignKeyConstraint(
            ["source_id"], ["workload_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workload_items_academic_year_id", "workload_items", ["academic_year_id"])
    op.create_index("ix_workload_items_source_id", "workload_items", ["source_id"])
    op.create_index("ix_workload_items_teacher_id", "workload_items", ["teacher_id"])


def downgrade() -> None:
    op.drop_index("ix_workload_items_teacher_id", table_name="workload_items")
    op.drop_index("ix_workload_items_source_id", table_name="workload_items")
    op.drop_index("ix_workload_items_academic_year_id", table_name="workload_items")
    op.drop_table("workload_items")
    op.drop_index("ix_import_warnings_source_id", table_name="import_warnings")
    op.drop_table("import_warnings")
    op.drop_index("ix_workload_sources_teacher_id", table_name="workload_sources")
    op.drop_index("ix_workload_sources_file_sha256", table_name="workload_sources")
    op.drop_index("ix_workload_sources_academic_year_id", table_name="workload_sources")
    op.drop_table("workload_sources")
    op.drop_index("ix_teachers_full_name", table_name="teachers")
    op.drop_table("teachers")
    op.drop_table("academic_years")
