"""enrich_customer_model_for_pos_import

Revision ID: 35679dbf97c7
Revises: 370b5f18aa74
Create Date: 2026-07-01 13:47:34.188414

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '35679dbf97c7'
down_revision: Union[str, None] = '370b5f18aa74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('alternate_number', sa.String(length=50), nullable=True))
    op.add_column('customers', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('customers', sa.Column('state', sa.String(length=100), nullable=True))
    op.add_column('customers', sa.Column('country', sa.String(length=100), nullable=True))
    op.add_column('customers', sa.Column('zip_code', sa.String(length=20), nullable=True))
    op.add_column('customers', sa.Column('tax_number', sa.String(length=100), nullable=True))
    op.add_column('customers', sa.Column('pay_term_number', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('pay_term_type', sa.Enum('days', 'months', name='paytermtype', create_type=False), nullable=True))
    op.add_column('customers', sa.Column('opening_balance', sa.Numeric(precision=18, scale=6), server_default='0', nullable=False))
    op.add_column('customers', sa.Column('credit_limit', sa.Numeric(precision=18, scale=6), nullable=True))
    op.add_column('customers', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('customers', sa.Column('customer_group', sa.String(length=100), nullable=True))
    op.create_index('ix_customers_is_active', 'customers', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_customers_is_active', table_name='customers')
    op.drop_column('customers', 'customer_group')
    op.drop_column('customers', 'is_active')
    op.drop_column('customers', 'credit_limit')
    op.drop_column('customers', 'opening_balance')
    op.drop_column('customers', 'pay_term_type')
    op.drop_column('customers', 'pay_term_number')
    op.drop_column('customers', 'tax_number')
    op.drop_column('customers', 'zip_code')
    op.drop_column('customers', 'country')
    op.drop_column('customers', 'state')
    op.drop_column('customers', 'city')
    op.drop_column('customers', 'alternate_number')
