"""add_triage_records_table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'triage_records',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('trigger_date', sa.Date(), nullable=False),
        sa.Column('shortfall_amount', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('horizon_days', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'resolved', name='triagestatus'),
            nullable=False,
            server_default='active',
        ),
        sa.Column('resolution_date', sa.Date(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('triage_records')
    op.execute("DROP TYPE IF EXISTS triagestatus")
