"""add_purchase_return_amount_paid

Revision ID: b4c5d6e7f8a9
Revises: e8f9a0b1c2d3
Create Date: 2026-06-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchase_returns',
        sa.Column(
            'amount_paid',
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )


def downgrade() -> None:
    op.drop_column('purchase_returns', 'amount_paid')
