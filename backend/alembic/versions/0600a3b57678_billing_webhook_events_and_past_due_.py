"""billing webhook events and past_due_since

Revision ID: 0600a3b57678
Revises: bcbed7e86f54
Create Date: 2026-09-17 06:57:05.406380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0600a3b57678'
down_revision: Union[str, None] = 'bcbed7e86f54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'webhook_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_webhook_events_event_type'), 'webhook_events', ['event_type'], unique=False
    )
    op.create_index(
        op.f('ix_webhook_events_idempotency_key'),
        'webhook_events',
        ['idempotency_key'],
        unique=True,
    )
    op.add_column(
        'businesses', sa.Column('past_due_since', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('businesses', 'past_due_since')
    op.drop_index(op.f('ix_webhook_events_idempotency_key'), table_name='webhook_events')
    op.drop_index(op.f('ix_webhook_events_event_type'), table_name='webhook_events')
    op.drop_table('webhook_events')
