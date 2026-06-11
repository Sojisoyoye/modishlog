"""add unit_cost_ngn to order_line_items

Revision ID: e2f3a4b5c6d7
Revises: c4d5e6f7a8b9
Create Date: 2026-06-11 14:45:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_line_items",
        sa.Column("unit_cost_ngn", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_line_items", "unit_cost_ngn")
