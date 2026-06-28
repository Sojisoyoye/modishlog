"""add_payment_date_to_sales

Revision ID: 7ab3f3415ed1
Revises: acd49221d4a4
Create Date: 2026-06-28 15:25:31.132676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7ab3f3415ed1'
down_revision: Union[str, None] = 'acd49221d4a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sales', sa.Column('payment_date', sa.Date(), nullable=True), schema='public')


def downgrade() -> None:
    op.drop_column('sales', 'payment_date', schema='public')
