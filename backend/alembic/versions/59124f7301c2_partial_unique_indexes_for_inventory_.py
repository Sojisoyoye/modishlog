"""partial_unique_indexes_for_inventory_levels

Revision ID: 59124f7301c2
Revises: ad3a7417f748
Create Date: 2026-07-11 14:30:00.000000

The previous migration (ad3a7417f748) replaced the single-column
UniqueConstraint('product_id') with a plain composite
UNIQUE(product_id, variant_id) — but Postgres treats NULL values as
distinct for uniqueness purposes, so that constraint does NOT prevent two
variant_id=NULL (aggregate) rows for the same product, silently weakening
an invariant the single-column constraint used to enforce unconditionally.
Two partial unique indexes express what's actually wanted.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "59124f7301c2"
down_revision: Union[str, None] = "ad3a7417f748"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_inventory_levels_product_variant", "inventory_levels", type_="unique"
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
        "uq_inventory_levels_product_variant",
        "inventory_levels",
        ["product_id", "variant_id"],
    )
