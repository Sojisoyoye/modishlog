"""add_inventory_batches_and_fifo_fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-11 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create inventory_batches table
    op.create_table(
        'inventory_batches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('order_id', sa.Uuid(), sa.ForeignKey('purchase_orders.id'), nullable=False),
        sa.Column('quantity_received', sa.Integer(), nullable=False),
        sa.Column('quantity_remaining', sa.Integer(), nullable=False),
        sa.Column('unit_cost_usd', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('fx_rate_at_arrival', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('logistics_allocation_per_unit', sa.Numeric(precision=18, scale=6), nullable=False, server_default='0'),
        sa.Column('landed_cost_per_unit', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('received_at', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_inventory_batches_product_id', 'inventory_batches', ['product_id'])
    op.create_index('ix_inventory_batches_order_id', 'inventory_batches', ['order_id'])

    # Add FIFO fields to sales table
    op.add_column(
        'sales',
        sa.Column('fifo_cogs', sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        'sales',
        sa.Column('fifo_gross_profit', sa.Numeric(precision=18, scale=6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('sales', 'fifo_gross_profit')
    op.drop_column('sales', 'fifo_cogs')
    op.drop_index('ix_inventory_batches_order_id', 'inventory_batches')
    op.drop_index('ix_inventory_batches_product_id', 'inventory_batches')
    op.drop_table('inventory_batches')
