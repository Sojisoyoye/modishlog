"""add price_suggestions table

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-06-11 21:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_suggestions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("unit_cost_ngn", sa.Numeric(18, 6), nullable=False),
        sa.Column("fx_rate_used", sa.Numeric(18, 6), nullable=False),
        sa.Column("target_margin_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("suggested_price_ngn", sa.Numeric(18, 6), nullable=False),
        sa.Column("current_catalog_price_ngn", sa.Numeric(18, 6), nullable=True),
        sa.Column("suggested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_suggestions_product_id", "price_suggestions", ["product_id"])
    op.create_index("ix_price_suggestions_suggested_at", "price_suggestions", ["suggested_at"])


def downgrade() -> None:
    op.drop_index("ix_price_suggestions_suggested_at", table_name="price_suggestions")
    op.drop_index("ix_price_suggestions_product_id", table_name="price_suggestions")
    op.drop_table("price_suggestions")
