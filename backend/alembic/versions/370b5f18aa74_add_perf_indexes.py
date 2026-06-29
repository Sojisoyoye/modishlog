"""add_perf_indexes

Revision ID: 370b5f18aa74
Revises: fc51a3928318
Create Date: 2026-06-29 12:36:58.798034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '370b5f18aa74'
down_revision: Union[str, None] = 'fc51a3928318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sales — missing filter columns (location_id and transaction_id already indexed)
    op.create_index('ix_sales_customer_id', 'sales', ['customer_id'])
    op.create_index('ix_sales_payment_status', 'sales', ['payment_status'])
    # Composite index speeds up transaction-list query (IN + ORDER BY created_at)
    op.create_index('ix_sales_txn_created', 'sales', ['transaction_id', 'created_at'])

    # Purchase orders — status and date filtering
    op.create_index('ix_purchase_orders_status', 'purchase_orders', ['status'])
    op.create_index('ix_purchase_orders_created_at', 'purchase_orders', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_purchase_orders_created_at', table_name='purchase_orders')
    op.drop_index('ix_purchase_orders_status', table_name='purchase_orders')
    op.drop_index('ix_sales_txn_created', table_name='sales')
    op.drop_index('ix_sales_payment_status', table_name='sales')
    op.drop_index('ix_sales_customer_id', table_name='sales')
