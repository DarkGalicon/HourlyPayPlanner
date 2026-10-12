"""Add explicit global working and non-working date overrides.

Revision ID: 0005_calendar_overrides
Revises: 0004_scheduler
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_calendar_overrides"
down_revision: str | None = "0004_scheduler"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_overrides",
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("is_working", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("target_date"),
    )


def downgrade() -> None:
    op.drop_table("calendar_overrides")
