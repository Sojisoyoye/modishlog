"""add_business_model

Revision ID: 9507112c79f3
Revises: a46ec11f3501
Create Date: 2026-07-03 11:58:20.260992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9507112c79f3'
down_revision: Union[str, None] = 'a46ec11f3501'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'owner' value to the userrole enum BEFORE any DDL that references it
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'owner'")

    # Create the businesses table
    op.create_table(
        'businesses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='NGN', nullable=False),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=100), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('timezone', sa.String(length=60), server_default='Africa/Lagos', nullable=False),
        sa.Column('tax_number', sa.String(length=100), nullable=True),
        sa.Column('fiscal_year_start_month', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Add business_id foreign key column to users
    op.add_column('users', sa.Column('business_id', sa.UUID(), nullable=True))
    op.create_index('ix_users_business_id', 'users', ['business_id'], unique=False)
    op.create_foreign_key(
        'fk_users_business_id_businesses',
        'users', 'businesses',
        ['business_id'], ['id'],
    )

def downgrade() -> None:
    op.drop_constraint('fk_users_business_id_businesses', 'users', type_='foreignkey')
    op.drop_index('ix_users_business_id', table_name='users')
    op.drop_column('users', 'business_id')
    op.drop_table('businesses')
    # Note: PostgreSQL does not support removing enum values; 'owner' stays in the type.
