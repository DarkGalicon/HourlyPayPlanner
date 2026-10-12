"""Remember permission to exceed the calculated hourly limit per teacher and year.

Revision ID: 0008_hourly_limit_permission
Revises: 0007_evening_selection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_hourly_limit_permission"
down_revision: str | None = "0007_evening_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hourly_limit_permissions",
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("academic_year_id", sa.Integer(),
                  sa.ForeignKey("academic_years.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("allow_limit_excess", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("hourly_limit_permissions")
