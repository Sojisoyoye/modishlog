"""add stock_counts and stock_count_items tables

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-12 04:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_counts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("count_date", sa.Date(), nullable=False),
        sa.Column(
            "count_type",
            sa.Enum("PRODUCT", "LOT", name="stockcounttype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "FINALIZED", name="stockcountstatus"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_counts_created_at", "stock_counts", ["created_at"])

    op.create_table(
        "stock_count_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stock_count_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("order_line_item_id", sa.UUID(), nullable=True),
        sa.Column("system_quantity_at_count", sa.Numeric(18, 6), nullable=True),
        sa.Column("counted_quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["stock_count_id"], ["stock_counts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["order_line_item_id"], ["order_line_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_count_items_stock_count_id", "stock_count_items", ["stock_count_id"])
    op.create_index("ix_stock_count_items_product_id", "stock_count_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_count_items_product_id", table_name="stock_count_items")
    op.drop_index("ix_stock_count_items_stock_count_id", table_name="stock_count_items")
    op.drop_table("stock_count_items")
    op.drop_index("ix_stock_counts_created_at", table_name="stock_counts")
    op.drop_table("stock_counts")
    op.execute("DROP TYPE IF EXISTS stockcounttype")
    op.execute("DROP TYPE IF EXISTS stockcountstatus")
