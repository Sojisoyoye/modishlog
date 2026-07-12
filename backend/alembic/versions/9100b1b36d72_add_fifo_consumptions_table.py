"""add_fifo_consumptions_table

Revision ID: 9100b1b36d72
Revises: 00db7d1e1a78
Create Date: 2026-07-12 10:00:00.000000

Made idempotent — see migration aaf1881e3f19 and
src/core/migration_utils.py for why: staging/prod's actual schema can
drift ahead of alembic_version, and this migration must self-heal rather
than hard-fail with DuplicateTable if that's already happened here.
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
    # Deferred, not module-level — see src/core/migration_utils.py's
    # docstring ("IMPORTING THIS MODULE") for why.
    from src.core.migration_utils import has_index, has_table

    insp = sa.inspect(op.get_bind())

    if not has_table("fifo_consumptions", insp=insp):
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
        # SQLAlchemy's Inspector caches has_table()/get_indexes() results
        # per-instance (confirmed against a live connection) — reusing
        # `insp` after create_table() just ran would make the has_index()
        # checks below see the pre-creation state. Rebuild it.
        insp = sa.inspect(op.get_bind())
    if not has_index("fifo_consumptions", "ix_fifo_consumptions_sale_id", insp=insp):
        op.create_index(
            "ix_fifo_consumptions_sale_id", "fifo_consumptions", ["sale_id"]
        )
    if not has_index("fifo_consumptions", "ix_fifo_consumptions_batch_id", insp=insp):
        op.create_index(
            "ix_fifo_consumptions_batch_id", "fifo_consumptions", ["batch_id"]
        )


def downgrade() -> None:
    from src.core.migration_utils import has_index, has_table

    insp = sa.inspect(op.get_bind())

    if has_index("fifo_consumptions", "ix_fifo_consumptions_batch_id", insp=insp):
        op.drop_index(
            "ix_fifo_consumptions_batch_id", table_name="fifo_consumptions"
        )
    if has_index("fifo_consumptions", "ix_fifo_consumptions_sale_id", insp=insp):
        op.drop_index("ix_fifo_consumptions_sale_id", table_name="fifo_consumptions")
    if has_table("fifo_consumptions", insp=insp):
        op.drop_table("fifo_consumptions")
