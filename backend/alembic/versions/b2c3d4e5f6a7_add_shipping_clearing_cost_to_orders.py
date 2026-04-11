"""add_shipping_clearing_cost_to_orders

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchase_orders',
        sa.Column(
            'shipping_cost',
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'purchase_orders',
        sa.Column(
            'clearing_cost',
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('purchase_orders', 'clearing_cost')
    op.drop_column('purchase_orders', 'shipping_cost')
