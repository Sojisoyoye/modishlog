"""add_payment_amount_to_sales

Revision ID: acd49221d4a4
Revises: b4c5d6e7f8a9
Create Date: 2026-06-23 22:29:33.610884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'acd49221d4a4'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sales', sa.Column('payment_amount', sa.Numeric(precision=18, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('sales', 'payment_amount')
