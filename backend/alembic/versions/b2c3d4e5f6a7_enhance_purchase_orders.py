"""enhance_purchase_orders

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ORDERED to the orderstatus enum
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'ORDERED'")

    # New enums
    op.execute("CREATE TYPE IF NOT EXISTS paytermtype_orders AS ENUM ('days', 'months')")
    op.execute("CREATE TYPE IF NOT EXISTS discounttype AS ENUM ('percentage', 'fixed')")

    cols = [
        sa.Column("is_purchase_order", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pay_term_number", sa.Integer(), nullable=True),
        sa.Column("pay_term_type", sa.Enum("days", "months", name="paytermtype_orders"), nullable=True),
        sa.Column("shipping_details", sa.Text(), nullable=True),
        sa.Column("shipping_custom_field_1", sa.String(255), nullable=True),
        sa.Column("shipping_custom_field_2", sa.String(255), nullable=True),
        sa.Column("shipping_custom_field_3", sa.String(255), nullable=True),
        sa.Column("shipping_custom_field_4", sa.String(255), nullable=True),
        sa.Column("shipping_custom_field_5", sa.String(255), nullable=True),
        sa.Column("additional_expense_key_1", sa.String(100), nullable=True),
        sa.Column("additional_expense_value_1", sa.Numeric(18, 6), nullable=True),
        sa.Column("additional_expense_key_2", sa.String(100), nullable=True),
        sa.Column("additional_expense_value_2", sa.Numeric(18, 6), nullable=True),
        sa.Column("additional_expense_key_3", sa.String(100), nullable=True),
        sa.Column("additional_expense_value_3", sa.Numeric(18, 6), nullable=True),
        sa.Column("additional_expense_key_4", sa.String(100), nullable=True),
        sa.Column("additional_expense_value_4", sa.Numeric(18, 6), nullable=True),
        sa.Column("discount_type", sa.Enum("percentage", "fixed", name="discounttype"), nullable=True),
        sa.Column("discount_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("supplier_invoice_number", sa.String(100), nullable=True),
        sa.Column("supplier_invoice_date", sa.Date(), nullable=True),
    ]
    for col in cols:
        op.add_column("purchase_orders", col)

    op.create_table(
        "purchase_returns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("original_order_id", sa.UUID(), nullable=False),
        sa.Column("ref_no", sa.String(100), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 6), nullable=False),
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
        sa.ForeignKeyConstraint(["original_order_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_returns_order_id", "purchase_returns", ["original_order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_returns_order_id", "purchase_returns")
    op.drop_table("purchase_returns")

    cols_to_drop = [
        "is_purchase_order", "pay_term_number", "pay_term_type",
        "shipping_details",
        "shipping_custom_field_1", "shipping_custom_field_2",
        "shipping_custom_field_3", "shipping_custom_field_4", "shipping_custom_field_5",
        "additional_expense_key_1", "additional_expense_value_1",
        "additional_expense_key_2", "additional_expense_value_2",
        "additional_expense_key_3", "additional_expense_value_3",
        "additional_expense_key_4", "additional_expense_value_4",
        "discount_type", "discount_amount",
        "tax_rate", "tax_amount",
        "supplier_invoice_number", "supplier_invoice_date",
    ]
    for col in cols_to_drop:
        op.drop_column("purchase_orders", col)

    op.execute("DROP TYPE IF EXISTS paytermtype_orders")
    op.execute("DROP TYPE IF EXISTS discounttype")
