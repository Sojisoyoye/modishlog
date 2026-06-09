"""add_customers_table_and_sale_customer_payment_status

Revision ID: a8b9c0d1e2f3
Revises: 6f6e21964f05
Create Date: 2026-06-06 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "6f6e21964f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create customers table
    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_number", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customers_name"), "customers", ["name"], unique=False)

    # Add customer_id FK and payment_status to sales
    op.add_column("sales", sa.Column("customer_id", sa.UUID(), nullable=True))
    op.add_column(
        "sales", sa.Column("payment_status", sa.String(length=20), nullable=True)
    )
    op.create_foreign_key(
        "fk_sales_customer_id",
        "sales",
        "customers",
        ["customer_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_sales_customer_id", "sales", type_="foreignkey")
    op.drop_column("sales", "payment_status")
    op.drop_column("sales", "customer_id")
    op.drop_index(op.f("ix_customers_name"), table_name="customers")
    op.drop_table("customers")
