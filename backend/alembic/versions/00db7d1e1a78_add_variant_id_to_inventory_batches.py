"""add_variant_id_to_inventory_batches

Revision ID: 00db7d1e1a78
Revises: ad3a7417f748
Create Date: 2026-07-11 22:00:00.000000

Made idempotent after discovering staging's actual schema had drifted
ahead of alembic_version — inventory_batches.variant_id already existed
on staging (outside Alembic tracking) when a real deploy first tried to
run this migration, blocking every migration after it with
DuplicateColumnError. See migration aaf1881e3f19 for the first instance
of this class of bug and src/core/migration_utils.py for the shared fix.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "00db7d1e1a78"
down_revision: Union[str, None] = "ad3a7417f748"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deferred, not module-level: Alembic's own file-discovery step (which
    # runs for every CLI command, not just `upgrade`) loads every versions
    # file *before* env.py's sys.path fix runs, so a top-level `from src...`
    # import here would break `alembic heads`/`history`/`upgrade` outright
    # with ModuleNotFoundError. By the time this function body actually
    # executes (only ever called from within env.py's run_migrations()),
    # sys.path already has the backend root on it.
    from src.core.migration_utils import has_column, has_constraint, has_index

    if not has_column("inventory_batches", "variant_id"):
        op.add_column(
            "inventory_batches",
            sa.Column(
                "variant_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not has_constraint("inventory_batches", "fk_inventory_batches_variant_id"):
        op.create_foreign_key(
            "fk_inventory_batches_variant_id",
            "inventory_batches",
            "product_variants",
            ["variant_id"],
            ["id"],
        )
    if not has_index("inventory_batches", "ix_inventory_batches_variant_id"):
        op.create_index(
            "ix_inventory_batches_variant_id", "inventory_batches", ["variant_id"]
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    if has_index("inventory_batches", "ix_inventory_batches_variant_id"):
        op.drop_index(
            "ix_inventory_batches_variant_id", table_name="inventory_batches"
        )
    if has_constraint("inventory_batches", "fk_inventory_batches_variant_id"):
        op.drop_constraint(
            "fk_inventory_batches_variant_id", "inventory_batches", type_="foreignkey"
        )
    if has_column("inventory_batches", "variant_id"):
        op.drop_column("inventory_batches", "variant_id")
