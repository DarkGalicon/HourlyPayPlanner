"""Remember evening preference for selected workload rows.

Revision ID: 0007_evening_selection
Revises: 0006_semester_practice_starts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_evening_selection"
down_revision: str | None = "0006_semester_practice_starts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hourly_selections") as batch:
        batch.add_column(sa.Column("prefer_evening", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("hourly_selections") as batch:
        batch.drop_column("prefer_evening")
