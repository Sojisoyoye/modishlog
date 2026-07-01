"""add_index_sell_returns_return_date

Revision ID: 70b06e888409
Revises: f5b9f118b7cc
Create Date: 2026-07-01 15:33:22.007600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70b06e888409'
down_revision: Union[str, None] = 'f5b9f118b7cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_sell_returns_return_date'), 'sell_returns', ['return_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sell_returns_return_date'), table_name='sell_returns')
