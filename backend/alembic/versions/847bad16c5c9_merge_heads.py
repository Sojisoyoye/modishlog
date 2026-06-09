"""merge_heads

Revision ID: 847bad16c5c9
Revises: aa2bb3cc4dd5, b2c3d4e5f6a8
Create Date: 2026-06-06 08:09:34.197237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '847bad16c5c9'
down_revision: Union[str, None] = ('aa2bb3cc4dd5', 'b2c3d4e5f6a8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
