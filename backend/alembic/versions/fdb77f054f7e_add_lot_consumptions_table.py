"""add_lot_consumptions_table

Revision ID: fdb77f054f7e
Revises: 7a29c684a562
Create Date: 2026-07-12 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "fdb77f054f7e"
down_revision: Union[str, None] = "7a29c684a562"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lot_consumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_line_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_line_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity_consumed", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_lot_consumptions_sale_id", "lot_consumptions", ["sale_id"])
    op.create_index(
        "ix_lot_consumptions_order_line_item_id",
        "lot_consumptions",
        ["order_line_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lot_consumptions_order_line_item_id", table_name="lot_consumptions"
    )
    op.drop_index("ix_lot_consumptions_sale_id", table_name="lot_consumptions")
    op.drop_table("lot_consumptions")
