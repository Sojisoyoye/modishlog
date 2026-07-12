"""add_variant_id_to_inventory_batches

Revision ID: 00db7d1e1a78
Revises: ad3a7417f748
Create Date: 2026-07-11 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "00db7d1e1a78"
down_revision: Union[str, None] = "ad3a7417f748"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_batches",
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_inventory_batches_variant_id",
        "inventory_batches",
        "product_variants",
        ["variant_id"],
        ["id"],
    )
    op.create_index(
        "ix_inventory_batches_variant_id", "inventory_batches", ["variant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_batches_variant_id", table_name="inventory_batches")
    op.drop_constraint(
        "fk_inventory_batches_variant_id", "inventory_batches", type_="foreignkey"
    )
    op.drop_column("inventory_batches", "variant_id")
