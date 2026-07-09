"""add_product_variants

Revision ID: f1e2d3c4b5a6
Revises: 8ecf7c69c468
Create Date: 2026-07-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = '8ecf7c69c468'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that should gain a nullable variant_id FK column
_VARIANT_FK_TABLES = [
    "inventory_levels",
    "inventory_batches",
    "stock_movements",
    "sales",
    "order_line_items",
    "supplier_products",
    "stock_count_items",
    "price_history",
]


def upgrade() -> None:
    # 1. Add has_variants flag to products
    op.add_column(
        "products",
        sa.Column("has_variants", sa.Boolean(), nullable=False, server_default="false"),
    )

    # 2. Create product_variants table
    op.create_table(
        "product_variants",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("barcode", sa.String(length=100), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("price_override", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("cost_price_override", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", "business_id", name="uq_product_variants_sku_business"),
    )
    op.create_index("ix_product_variants_business_id", "product_variants", ["business_id"])
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    # 3. Add nullable variant_id to related tables
    for table in _VARIANT_FK_TABLES:
        op.add_column(
            table,
            sa.Column("variant_id", sa.Uuid(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_variant_id",
            table,
            "product_variants",
            ["variant_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_variant_id", table, ["variant_id"])


def downgrade() -> None:
    # Remove variant_id from related tables (reverse order)
    for table in reversed(_VARIANT_FK_TABLES):
        op.drop_index(f"ix_{table}_variant_id", table_name=table)
        op.drop_constraint(f"fk_{table}_variant_id", table, type_="foreignkey")
        op.drop_column(table, "variant_id")

    # Drop product_variants table
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_index("ix_product_variants_business_id", table_name="product_variants")
    op.drop_table("product_variants")

    # Remove has_variants from products
    op.drop_column("products", "has_variants")
