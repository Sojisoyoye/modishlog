"""add_current_balance_to_loan_obligations

Revision ID: a1b2c3d4e5f6
Revises: c47911aa433e
Create Date: 2026-04-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c47911aa433e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'loan_obligations',
        sa.Column('current_balance', sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        'loan_obligations',
        sa.Column(
            'current_balance_currency',
            sa.String(length=3),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('loan_obligations', 'current_balance_currency')
    op.drop_column('loan_obligations', 'current_balance')
