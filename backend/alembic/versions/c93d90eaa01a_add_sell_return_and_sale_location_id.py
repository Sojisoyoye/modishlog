"""add_sell_return_and_sale_location_id

Revision ID: c93d90eaa01a
Revises: f4a5b6c7d8e9
Create Date: 2026-06-23 17:20:08.468815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c93d90eaa01a'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('sell_returns',
    sa.Column('sale_id', sa.Uuid(), nullable=False),
    sa.Column('return_date', sa.Date(), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('amount_paid', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sell_returns_sale_id'), 'sell_returns', ['sale_id'], unique=False)
    op.add_column('sales', sa.Column('location_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_sales_location_id'), 'sales', ['location_id'], unique=False)
    op.create_foreign_key(None, 'sales', 'business_locations', ['location_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(None, 'sales', type_='foreignkey')
    op.drop_index(op.f('ix_sales_location_id'), table_name='sales')
    op.drop_column('sales', 'location_id')
    op.drop_index(op.f('ix_sell_returns_sale_id'), table_name='sell_returns')
    op.drop_table('sell_returns')
