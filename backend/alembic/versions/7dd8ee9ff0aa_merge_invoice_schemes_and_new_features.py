"""merge_invoice_schemes_and_new_features

Revision ID: 7dd8ee9ff0aa
Revises: 6cc7dd8ee9ff, e7f8a9b0c1d2
Create Date: 2026-06-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "7dd8ee9ff0aa"
down_revision: Union[str, Sequence[str], None] = ("6cc7dd8ee9ff", "e7f8a9b0c1d2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
