"""fix_inventory_levels_unique_constraint

Revision ID: ad3a7417f748
Revises: 2e8ecc311f3c
Create Date: 2026-07-11 14:00:00.000000

The add_product_variants migration (f1e2d3c4b5a6) added variant_id to
inventory_levels but never replaced the original single-column
UniqueConstraint('product_id') from the initial schema — the SQLAlchemy
model has always declared the correct composite constraint
(uq_inventory_levels_product_variant on product_id+variant_id), but the
database itself was never migrated to match, so no variant-level
InventoryLevel row could ever coexist with a product's aggregate row.
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
    op.create_unique_constraint(
        "uq_inventory_levels_product_variant",
        "inventory_levels",
        ["product_id", "variant_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_inventory_levels_product_variant", "inventory_levels", type_="unique"
    )
    op.create_unique_constraint(
        "inventory_levels_product_id_key", "inventory_levels", ["product_id"]
    )
