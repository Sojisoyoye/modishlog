"""add_ref_no_to_sell_returns

Revision ID: f5b9f118b7cc
Revises: 35679dbf97c7
Create Date: 2026-07-01 15:19:15.783092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5b9f118b7cc'
down_revision: Union[str, None] = '35679dbf97c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sell_returns', sa.Column('ref_no', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('sell_returns', 'ref_no')
