"""add parent_id to product_categories

Revision ID: d1e2f3a4b5c6
Revises: c2d3e4f5a6b7
Create Date: 2026-06-12 14:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d1e2f3a4b5c6"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_categories",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_product_categories_parent_id",
        "product_categories",
        ["parent_id"],
    )
    op.create_foreign_key(
        "fk_product_categories_parent_id",
        "product_categories",
        "product_categories",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_categories_parent_id", "product_categories", type_="foreignkey")
    op.drop_index("ix_product_categories_parent_id", table_name="product_categories")
    op.drop_column("product_categories", "parent_id")
