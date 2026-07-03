"""scope_product_sku_slug_unique_per_business

Replace global unique constraints on products.sku and products.slug with
composite unique constraints scoped to (sku, business_id) and (slug, business_id)
to support multi-tenant isolation.

Revision ID: b1c2d3e4f5a6
Revises: 9507112c79f3
Create Date: 2026-07-03 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "9507112c79f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old global unique index on sku (created as a unique index in initial schema)
    op.drop_index("ix_products_sku", table_name="products")

    # Drop the old global unique constraint on slug (created in f4a5b6c7d8e9)
    op.drop_constraint("uq_products_slug", "products", type_="unique")

    # Create composite unique constraints scoped to business
    op.create_unique_constraint(
        "uq_products_sku_business", "products", ["sku", "business_id"]
    )
    op.create_unique_constraint(
        "uq_products_slug_business", "products", ["slug", "business_id"]
    )

    # Re-create non-unique indexes for query performance
    op.create_index("ix_products_sku", "products", ["sku"], unique=False)


def downgrade() -> None:
    # Drop composite constraints
    op.drop_constraint("uq_products_sku_business", "products", type_="unique")
    op.drop_constraint("uq_products_slug_business", "products", type_="unique")

    # Drop the non-unique sku index we created in upgrade
    op.drop_index("ix_products_sku", table_name="products")

    # Restore original global unique index on sku
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)

    # Restore original global unique constraint on slug
    op.create_unique_constraint("uq_products_slug", "products", ["slug"])
