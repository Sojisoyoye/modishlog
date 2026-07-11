"""add_recompute_fields_to_migration_jobs

Revision ID: 2e8ecc311f3c
Revises: e1f2a3b4c5d6
Create Date: 2026-07-11 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2e8ecc311f3c"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

recompute_status = postgresql.ENUM("running", "done", "failed", name="recomputestatus")


def upgrade() -> None:
    # Unlike migration_jobs' other enum columns (created implicitly by
    # create_table when this table was first added), this one is being
    # added to an already-existing table via add_column — the enum type
    # must be created explicitly first, or add_column fails looking for a
    # type that doesn't exist yet.
    recompute_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "migration_jobs",
        sa.Column("recompute_status", recompute_status, nullable=True),
    )
    op.add_column(
        "migration_jobs",
        sa.Column("recompute_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "migration_jobs",
        sa.Column("recompute_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "migration_jobs",
        sa.Column(
            "recompute_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("migration_jobs", "recompute_errors")
    op.drop_column("migration_jobs", "recompute_completed_at")
    op.drop_column("migration_jobs", "recompute_started_at")
    op.drop_column("migration_jobs", "recompute_status")
    recompute_status.drop(op.get_bind(), checkfirst=True)
