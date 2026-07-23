"""fix_inventory_levels_unique_constraint

Revision ID: ad3a7417f748
Revises: 2e8ecc311f3c
Create Date: 2026-07-11 14:00:00.000000

The add_product_variants migration (f1e2d3c4b5a6) added variant_id to
inventory_levels but never replaced the original single-column
UniqueConstraint('product_id') from the initial schema, so no variant-level
InventoryLevel row could ever coexist with a product's aggregate row.

A plain composite UNIQUE(product_id, variant_id) isn't the right
replacement either — Postgres treats NULL values as distinct for
uniqueness purposes, so it would silently allow two variant_id=NULL
(aggregate) rows for the same product, weakening an invariant the original
single-column constraint enforced unconditionally. Two partial unique
indexes express what's actually wanted: at most one aggregate row per
product, and at most one row per real (product_id, variant_id) pair.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "ad3a7417f748"
down_revision: Union[str, None] = "2e8ecc311f3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotency guards: alembic_version drift (a prior deploy attempt
    # applying this migration's DDL then failing/retrying, or a manual
    # rollback) must not hard-fail a later `alembic upgrade head` re-run —
    # see src/core/migration_utils.py's docstring for the recurring
    # incident class this guards against. Each has_* call builds its own
    # fresh Inspector (not shared) since DDL runs between checks here.
    from src.core.migration_utils import has_constraint, has_index

    if has_constraint("inventory_levels", "inventory_levels_product_id_key"):
        op.drop_constraint(
            "inventory_levels_product_id_key", "inventory_levels", type_="unique"
        )
    if not has_index("inventory_levels", "uq_inventory_levels_product_no_variant"):
        op.create_index(
            "uq_inventory_levels_product_no_variant",
            "inventory_levels",
            ["product_id"],
            unique=True,
            postgresql_where="variant_id IS NULL",
        )
    if not has_index("inventory_levels", "uq_inventory_levels_product_variant"):
        op.create_index(
            "uq_inventory_levels_product_variant",
            "inventory_levels",
            ["product_id", "variant_id"],
            unique=True,
            postgresql_where="variant_id IS NOT NULL",
        )


def downgrade() -> None:
    from src.core.migration_utils import has_constraint, has_index

    if has_index("inventory_levels", "uq_inventory_levels_product_variant"):
        op.drop_index("uq_inventory_levels_product_variant", "inventory_levels")
    if has_index("inventory_levels", "uq_inventory_levels_product_no_variant"):
        op.drop_index("uq_inventory_levels_product_no_variant", "inventory_levels")
    if not has_constraint("inventory_levels", "inventory_levels_product_id_key"):
        op.create_unique_constraint(
            "inventory_levels_product_id_key", "inventory_levels", ["product_id"]
        )
