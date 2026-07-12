"""add_variant_id_to_price_suggestions

Revision ID: 78362e79f979
Revises: fdb77f054f7e
Create Date: 2026-07-12 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "78362e79f979"
down_revision: Union[str, None] = "fdb77f054f7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "price_suggestions",
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_price_suggestions_variant_id",
        "price_suggestions",
        "product_variants",
        ["variant_id"],
        ["id"],
    )
    op.create_index(
        "ix_price_suggestions_variant_id", "price_suggestions", ["variant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_price_suggestions_variant_id", table_name="price_suggestions")
    op.drop_constraint(
        "fk_price_suggestions_variant_id", "price_suggestions", type_="foreignkey"
    )
    op.drop_column("price_suggestions", "variant_id")
