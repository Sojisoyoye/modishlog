"""add business_id to sales and purchase_orders

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-03 12:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add business_id to sales
    op.add_column(
        "sales",
        sa.Column("business_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_sales_business_id", "sales", ["business_id"])
    op.create_foreign_key(
        "fk_sales_business_id",
        "sales",
        "businesses",
        ["business_id"],
        ["id"],
    )

    # Add business_id to purchase_orders
    op.add_column(
        "purchase_orders",
        sa.Column("business_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_purchase_orders_business_id", "purchase_orders", ["business_id"]
    )
    op.create_foreign_key(
        "fk_purchase_orders_business_id",
        "purchase_orders",
        "businesses",
        ["business_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_purchase_orders_business_id", "purchase_orders", type_="foreignkey"
    )
    op.drop_index("ix_purchase_orders_business_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "business_id")

    op.drop_constraint("fk_sales_business_id", "sales", type_="foreignkey")
    op.drop_index("ix_sales_business_id", table_name="sales")
    op.drop_column("sales", "business_id")
