"""add_order_date_payment_status_location

Revision ID: b3c4d5e6f7a8
Revises: 7dd8ee9ff0aa
Create Date: 2026-06-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = '7dd8ee9ff0aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    payment_status_enum = sa.Enum('UNPAID', 'PARTIAL', 'PAID', name='order_payment_status')
    payment_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('purchase_orders', sa.Column('order_date', sa.Date(), nullable=True))
    op.add_column(
        'purchase_orders',
        sa.Column(
            'payment_status',
            sa.Enum('UNPAID', 'PARTIAL', 'PAID', name='order_payment_status'),
            nullable=False,
            server_default='UNPAID',
        ),
    )
    op.add_column('purchase_orders', sa.Column('location_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        None,
        'purchase_orders',
        'business_locations',
        ['location_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_purchase_orders_location_id', 'purchase_orders', ['location_id'])


def downgrade() -> None:
    op.drop_index('ix_purchase_orders_location_id', table_name='purchase_orders')
    op.drop_constraint(
        None, 'purchase_orders', type_='foreignkey'
    )
    op.drop_column('purchase_orders', 'location_id')
    op.drop_column('purchase_orders', 'payment_status')
    op.drop_column('purchase_orders', 'order_date')

    # Drop the enum type
    sa.Enum(name='order_payment_status').drop(op.get_bind(), checkfirst=True)
