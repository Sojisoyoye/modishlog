"""add fx_rate to order_payments

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-11 14:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_payments",
        sa.Column("fx_rate", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_payments", "fx_rate")
