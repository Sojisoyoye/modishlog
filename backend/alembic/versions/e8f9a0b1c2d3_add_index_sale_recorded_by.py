"""add_index_sale_recorded_by

Revision ID: e8f9a0b1c2d3
Revises: c93d90eaa01a
Create Date: 2026-06-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'c93d90eaa01a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_sales_recorded_by'), 'sales', ['recorded_by'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sales_recorded_by'), table_name='sales')
