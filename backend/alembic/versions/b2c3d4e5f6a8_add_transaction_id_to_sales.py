"""add_transaction_id_to_sales

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-05-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sales',
        sa.Column(
            'transaction_id',
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.create_index('ix_sales_transaction_id', 'sales', ['transaction_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_sales_transaction_id', table_name='sales')
    op.drop_column('sales', 'transaction_id')
