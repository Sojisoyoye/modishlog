"""add_business_deletion_fields

Revision ID: eed0bc0b02ff
Revises: 5baae79a6c06
Create Date: 2026-09-15 06:32:11.670141

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eed0bc0b02ff'
down_revision: Union[str, None] = '5baae79a6c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'businesses',
        sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'businesses',
        sa.Column('purge_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('businesses', 'purge_at')
    op.drop_column('businesses', 'deletion_requested_at')
