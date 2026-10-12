"""Store editable teacher details for statement headers.

Revision ID: 0009_teacher_personal_data
Revises: 0008_hourly_limit_permission
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_teacher_personal_data"
down_revision: str | None = "0008_hourly_limit_permission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("teachers") as batch:
        batch.add_column(sa.Column("imported_name", sa.String(300)))
        batch.add_column(sa.Column("birth_date", sa.Date()))
        batch.add_column(sa.Column("address", sa.String(1000)))
        batch.add_column(sa.Column("passport_series", sa.String(20)))
        batch.add_column(sa.Column("passport_number", sa.String(30)))
        batch.add_column(sa.Column("passport_issued_by", sa.String(1000)))
        batch.add_column(sa.Column("passport_issue_date", sa.Date()))
        batch.add_column(sa.Column("snils", sa.String(30)))
        batch.add_column(sa.Column("inn", sa.String(30)))
    op.execute("UPDATE teachers SET imported_name = full_name")
    op.create_index("ix_teachers_imported_name", "teachers", ["imported_name"])


def downgrade() -> None:
    op.drop_index("ix_teachers_imported_name", table_name="teachers")
    with op.batch_alter_table("teachers") as batch:
        for name in (
            "inn", "snils", "passport_issue_date", "passport_issued_by",
            "passport_number", "passport_series", "address", "birth_date",
            "imported_name",
        ):
            batch.drop_column(name)
