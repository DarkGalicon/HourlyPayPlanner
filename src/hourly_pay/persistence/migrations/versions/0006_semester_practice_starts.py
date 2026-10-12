"""Store the explicit first practice/lab date per academic year and semester.

Revision ID: 0006_semester_practice_starts
Revises: 0005_calendar_overrides
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_semester_practice_starts"
down_revision: str | None = "0005_calendar_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semester_practice_starts",
        sa.Column("academic_year_id", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("first_allowed_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("academic_year_id", "semester"),
    )


def downgrade() -> None:
    op.drop_table("semester_practice_starts")
