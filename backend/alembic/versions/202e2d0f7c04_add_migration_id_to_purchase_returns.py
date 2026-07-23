"""add_migration_id_to_purchase_returns

Revision ID: 202e2d0f7c04
Revises: 78362e79f979
Create Date: 2026-07-23 00:00:00.000000

purchase_returns was the one domain table left off MIGRATION_ID_TABLES in
bc0d9bce053d (add_data_import_migration_jobs) — every other importable
table already carries migration_id, but purchase_returns predates the
data_import feature's own migration_id backfill pass and was never
included. Needed before purchase_returns can become an importable/
rollback-safe data_import entity. Idempotent per the has_column/
has_constraint/has_index pattern established after the Jul 12 staging
schema-drift incident (see 00db7d1e1a78, aaf1881e3f19).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202e2d0f7c04"
down_revision: Union[str, None] = "78362e79f979"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deferred, not module-level — see src/core/migration_utils.py's
    # docstring ("IMPORTING THIS MODULE") for why.
    from src.core.migration_utils import has_column, has_constraint, has_index

    insp = sa.inspect(op.get_bind())

    if not has_column("purchase_returns", "migration_id", insp=insp):
        op.add_column(
            "purchase_returns",
            sa.Column("migration_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not has_constraint(
        "purchase_returns", "fk_purchase_returns_migration_id", insp=insp
    ):
        op.create_foreign_key(
            "fk_purchase_returns_migration_id",
            "purchase_returns",
            "migration_jobs",
            ["migration_id"],
            ["id"],
        )
    if not has_index(
        "purchase_returns", "ix_purchase_returns_migration_id", insp=insp
    ):
        op.create_index(
            "ix_purchase_returns_migration_id", "purchase_returns", ["migration_id"]
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    insp = sa.inspect(op.get_bind())

    if has_index("purchase_returns", "ix_purchase_returns_migration_id", insp=insp):
        op.drop_index(
            "ix_purchase_returns_migration_id", table_name="purchase_returns"
        )
    if has_constraint(
        "purchase_returns", "fk_purchase_returns_migration_id", insp=insp
    ):
        op.drop_constraint(
            "fk_purchase_returns_migration_id",
            "purchase_returns",
            type_="foreignkey",
        )
    if has_column("purchase_returns", "migration_id", insp=insp):
        op.drop_column("purchase_returns", "migration_id")
