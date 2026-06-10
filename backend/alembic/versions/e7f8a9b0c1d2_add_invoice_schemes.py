"""add_invoice_schemes

Revision ID: e7f8a9b0c1d2
Revises: f8a9b0c1d2e3
Create Date: 2026-06-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'invoice_schemes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'scheme_type',
            sa.Enum('blank', 'year', name='schemetype'),
            nullable=False,
            server_default='blank',
        ),
        sa.Column('prefix', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('start_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('total_digits', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('next_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('invoice_schemes')
    op.execute("DROP TYPE IF EXISTS schemetype")
