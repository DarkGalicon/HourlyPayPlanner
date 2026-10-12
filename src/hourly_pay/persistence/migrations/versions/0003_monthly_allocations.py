"""Add monthly allocations.

Revision ID: 0003_monthly_allocations
Revises: 0002_hourly_selections
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_monthly_allocations"
down_revision: str | None = "0002_hourly_selections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hourly_selection_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.ForeignKeyConstraint(
            ["hourly_selection_id"], ["hourly_selections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "hourly_selection_id", "year", "month", name="uq_allocation_selection_month"
        ),
    )
    op.create_index(
        "ix_monthly_allocations_hourly_selection_id",
        "monthly_allocations",
        ["hourly_selection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monthly_allocations_hourly_selection_id", table_name="monthly_allocations"
    )
    op.drop_table("monthly_allocations")
