"""add_suppliers_table

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-06-09 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("mobile", sa.String(50), nullable=True),
        sa.Column("alternate_number", sa.String(50), nullable=True),
        sa.Column("tax_number", sa.String(100), nullable=True),
        sa.Column("address_line_1", sa.String(255), nullable=True),
        sa.Column("address_line_2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("pay_term_number", sa.Integer(), nullable=True),
        sa.Column(
            "pay_term_type",
            sa.Enum("days", "months", name="paytermtype"),
            nullable=True,
        ),
        sa.Column(
            "opening_balance",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    op.create_table(
        "supplier_products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", "product_id"),
    )

    op.add_column(
        "purchase_orders",
        sa.Column("supplier_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_purchase_orders_supplier_id",
        "purchase_orders",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_supplier_id", "purchase_orders")
    op.drop_constraint(
        "fk_purchase_orders_supplier_id", "purchase_orders", type_="foreignkey"
    )
    op.drop_column("purchase_orders", "supplier_id")
    op.drop_table("supplier_products")
    op.drop_index("ix_suppliers_name", "suppliers")
    op.drop_table("suppliers")
    op.execute("DROP TYPE IF EXISTS paytermtype")
