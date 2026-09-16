"""add_billing_fields_to_business

Revision ID: bcbed7e86f54
Revises: ee16369ce64b
Create Date: 2026-09-16 14:56:13.546480

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bcbed7e86f54'
down_revision: Union[str, None] = 'ee16369ce64b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE subscriptionstatus AS ENUM ('trialing', 'active', 'past_due', 'read_only', 'canceled')")
    op.execute("CREATE TYPE subscriptiontier AS ENUM ('basic', 'pro')")
    op.add_column('businesses', sa.Column('subscription_status', sa.Enum('trialing', 'active', 'past_due', 'read_only', 'canceled', name='subscriptionstatus'), server_default='trialing', nullable=False))
    op.add_column('businesses', sa.Column('subscription_tier', sa.Enum('basic', 'pro', name='subscriptiontier'), server_default='pro', nullable=False))
    op.add_column('businesses', sa.Column('paystack_customer_code', sa.String(length=100), nullable=True))
    op.add_column('businesses', sa.Column('paystack_subscription_code', sa.String(length=100), nullable=True))
    op.add_column('businesses', sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('businesses', 'current_period_end')
    op.drop_column('businesses', 'paystack_subscription_code')
    op.drop_column('businesses', 'paystack_customer_code')
    op.drop_column('businesses', 'subscription_tier')
    op.drop_column('businesses', 'subscription_status')
    op.execute("DROP TYPE IF EXISTS subscriptiontier")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
