"""add_pos_id_to_sales_orders_and_sync_state_table

Revision ID: 36e556663d21
Revises: 5ee86806d6dc
Create Date: 2026-07-01 20:50:04.986978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36e556663d21'
down_revision: Union[str, None] = '5ee86806d6dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pos_sync_state: key-value watermark store for incremental POS sync
    op.create_table(
        'pos_sync_state',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.add_column('purchase_orders', sa.Column('pos_id', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_purchase_orders_pos_id'), 'purchase_orders', ['pos_id'], unique=False)
    op.add_column('sales', sa.Column('pos_id', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_sales_pos_id'), 'sales', ['pos_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sales_pos_id'), table_name='sales')
    op.drop_column('sales', 'pos_id')
    op.drop_index(op.f('ix_purchase_orders_pos_id'), table_name='purchase_orders')
    op.drop_column('purchase_orders', 'pos_id')
    op.drop_table('pos_sync_state')
