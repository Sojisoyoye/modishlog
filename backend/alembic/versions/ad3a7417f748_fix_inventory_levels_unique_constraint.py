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
    op.drop_constraint(
        "inventory_levels_product_id_key", "inventory_levels", type_="unique"
    )
    op.create_index(
        "uq_inventory_levels_product_no_variant",
        "inventory_levels",
        ["product_id"],
        unique=True,
        postgresql_where="variant_id IS NULL",
    )
    op.create_index(
        "uq_inventory_levels_product_variant",
        "inventory_levels",
        ["product_id", "variant_id"],
        unique=True,
        postgresql_where="variant_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_inventory_levels_product_variant", "inventory_levels")
    op.drop_index("uq_inventory_levels_product_no_variant", "inventory_levels")
    op.create_unique_constraint(
        "inventory_levels_product_id_key", "inventory_levels", ["product_id"]
    )
