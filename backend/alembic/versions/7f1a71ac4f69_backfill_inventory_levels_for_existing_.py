"""backfill_inventory_levels_for_existing_products

Revision ID: 7f1a71ac4f69
Revises: a7b8c9d0e1f2
Create Date: 2026-04-12 17:01:30.410562

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f1a71ac4f69'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert inventory_levels rows for products that don't have one yet
    op.execute(
        sa.text("""
            INSERT INTO inventory_levels (id, product_id, quantity_on_hand, quantity_reserved, low_stock_threshold, created_at, updated_at)
            SELECT gen_random_uuid(), p.id, 0, 0, 10, NOW(), NOW()
            FROM products p
            LEFT JOIN inventory_levels il ON il.product_id = p.id
            WHERE il.id IS NULL
        """)
    )


def downgrade() -> None:
    # No safe way to reverse a backfill; leave rows in place
    pass
