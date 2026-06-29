"""merge_user_preferences_and_payment_date

Revision ID: fc51a3928318
Revises: 7ab3f3415ed1, a2b3c4d5e6f7
Create Date: 2026-06-29 08:14:28.395142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc51a3928318'
down_revision: Union[str, None] = ('7ab3f3415ed1', 'a2b3c4d5e6f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
