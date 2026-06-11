"""add units_remaining to order_line_items

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-06-11 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_line_items",
        sa.Column("units_remaining", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_line_items", "units_remaining")
