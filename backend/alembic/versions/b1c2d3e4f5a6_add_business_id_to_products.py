"""add_business_id_to_products

Revision ID: b1c2d3e4f5a6
Revises: 9507112c79f3
Create Date: 2026-07-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '9507112c79f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('business_id', sa.UUID(), nullable=True),
    )
    op.create_index('ix_products_business_id', 'products', ['business_id'], unique=False)
    op.create_foreign_key(
        'fk_products_business_id_businesses',
        'products',
        'businesses',
        ['business_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_products_business_id_businesses', 'products', type_='foreignkey')
    op.drop_index('ix_products_business_id', table_name='products')
    op.drop_column('products', 'business_id')
