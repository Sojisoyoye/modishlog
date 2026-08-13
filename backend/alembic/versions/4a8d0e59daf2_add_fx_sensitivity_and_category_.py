"""add_fx_sensitivity_and_category_elasticity_defaults

Revision ID: 4a8d0e59daf2
Revises: c3e5f8a1b2d4
Create Date: 2026-08-13 21:25:40.368210

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4a8d0e59daf2'
down_revision: Union[str, None] = 'c3e5f8a1b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'demand_elasticities',
        sa.Column('fx_sensitivity_coefficient', sa.Numeric(precision=8, scale=4), nullable=True),
    )
    op.add_column(
        'product_categories',
        sa.Column('default_elasticity_coefficient', sa.Numeric(precision=8, scale=4), nullable=True),
    )
    op.add_column(
        'product_categories',
        sa.Column('default_fx_sensitivity_coefficient', sa.Numeric(precision=8, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('product_categories', 'default_fx_sensitivity_coefficient')
    op.drop_column('product_categories', 'default_elasticity_coefficient')
    op.drop_column('demand_elasticities', 'fx_sensitivity_coefficient')
