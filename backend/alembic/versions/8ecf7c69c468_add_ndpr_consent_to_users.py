"""add_ndpr_consent_to_users

Revision ID: 8ecf7c69c468
Revises: 4def4e1d8faf
Create Date: 2026-07-08 16:24:26.963575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8ecf7c69c468'
down_revision: Union[str, None] = '4def4e1d8faf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('ndpr_consent_given', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('ndpr_consent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'ndpr_consent_at')
    op.drop_column('users', 'ndpr_consent_given')
