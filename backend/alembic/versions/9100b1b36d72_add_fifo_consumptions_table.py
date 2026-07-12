"""add_fifo_consumptions_table

Revision ID: 9100b1b36d72
Revises: 00db7d1e1a78
Create Date: 2026-07-12 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9100b1b36d72"
down_revision: Union[str, None] = "00db7d1e1a78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fifo_consumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inventory_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity_consumed", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_fifo_consumptions_sale_id", "fifo_consumptions", ["sale_id"])
    op.create_index("ix_fifo_consumptions_batch_id", "fifo_consumptions", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_fifo_consumptions_batch_id", table_name="fifo_consumptions")
    op.drop_index("ix_fifo_consumptions_sale_id", table_name="fifo_consumptions")
    op.drop_table("fifo_consumptions")
