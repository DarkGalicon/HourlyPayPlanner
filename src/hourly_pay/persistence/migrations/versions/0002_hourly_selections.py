"""Add manual hourly selections.

Revision ID: 0002_hourly_selections
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_hourly_selections"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hourly_selections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("workload_item_id", sa.Integer(), nullable=False),
        sa.Column("selected_hours", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workload_item_id"], ["workload_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workload_item_id"),
    )
    op.create_index(
        "ix_hourly_selections_teacher_id", "hourly_selections", ["teacher_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_hourly_selections_teacher_id", table_name="hourly_selections")
    op.drop_table("hourly_selections")
