"""widen_sale_payment_amount_precision

Revision ID: 5baae79a6c06
Revises: 5fad784c007a
Create Date: 2026-09-15 05:50:06.289268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5baae79a6c06'
down_revision: Union[str, None] = '5fad784c007a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'sales',
        'payment_amount',
        existing_type=sa.Numeric(precision=18, scale=2),
        type_=sa.Numeric(precision=18, scale=6),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'sales',
        'payment_amount',
        existing_type=sa.Numeric(precision=18, scale=6),
        type_=sa.Numeric(precision=18, scale=2),
        existing_nullable=True,
    )
