"""add_liquidity_snapshots_table

Revision ID: 4947af767e2a
Revises: 4a8d0e59daf2
Create Date: 2026-08-14 08:12:27.405118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4947af767e2a'
down_revision: Union[str, None] = '4a8d0e59daf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'liquidity_snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('business_id', sa.Uuid(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('cash_runway_months', sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column('cash_runway_is_finite', sa.Boolean(), nullable=True),
        sa.Column('dscr', sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column('dscr_is_finite', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'snapshot_date', name='uq_liquidity_snapshot_business_date'),
    )
    op.create_index(
        op.f('ix_liquidity_snapshots_business_id'), 'liquidity_snapshots', ['business_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_liquidity_snapshots_business_id'), table_name='liquidity_snapshots')
    op.drop_table('liquidity_snapshots')
