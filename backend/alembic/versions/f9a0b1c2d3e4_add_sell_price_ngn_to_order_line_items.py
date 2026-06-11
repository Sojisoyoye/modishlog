"""add sell_price_ngn to order_line_items

Revision ID: f9a0b1c2d3e4
Revises: e2f3a4b5c6d7
Create Date: 2026-06-11 19:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_line_items",
        sa.Column("sell_price_ngn", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_line_items", "sell_price_ngn")
