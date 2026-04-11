"""add_pricing_scenarios_table

Revision ID: f6a7b8c9d0e1
Revises: c47911aa433e
Create Date: 2026-04-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'c47911aa433e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pricing_scenarios',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('selling_price', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('fx_rate', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('results', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('pricing_scenarios')
