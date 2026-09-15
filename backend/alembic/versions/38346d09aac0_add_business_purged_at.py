"""add_business_purged_at

Revision ID: 38346d09aac0
Revises: eed0bc0b02ff
Create Date: 2026-09-15 09:13:19.238018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38346d09aac0'
down_revision: Union[str, None] = 'eed0bc0b02ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'businesses',
        sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('businesses', 'purged_at')
