"""add_lot_consumptions_table

Revision ID: fdb77f054f7e
Revises: 7a29c684a562
Create Date: 2026-07-12 12:00:00.000000

Made idempotent — see migration aaf1881e3f19 and
src/core/migration_utils.py for why: staging/prod's actual schema can
drift ahead of alembic_version, and this migration must self-heal rather
than hard-fail with DuplicateTable if that's already happened here.
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
    # Deferred, not module-level — see src/core/migration_utils.py's
    # docstring ("IMPORTING THIS MODULE") for why.
    from src.core.migration_utils import has_index, has_table

    insp = sa.inspect(op.get_bind())

    if not has_table("lot_consumptions", insp=insp):
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
        # SQLAlchemy's Inspector caches has_table()/get_indexes() results
        # per-instance (confirmed against a live connection) — reusing
        # `insp` after create_table() just ran would make the has_index()
        # checks below see the pre-creation state. Rebuild it.
        insp = sa.inspect(op.get_bind())
    if not has_index("lot_consumptions", "ix_lot_consumptions_sale_id", insp=insp):
        op.create_index("ix_lot_consumptions_sale_id", "lot_consumptions", ["sale_id"])
    if not has_index(
        "lot_consumptions", "ix_lot_consumptions_order_line_item_id", insp=insp
    ):
        op.create_index(
            "ix_lot_consumptions_order_line_item_id",
            "lot_consumptions",
            ["order_line_item_id"],
        )


def downgrade() -> None:
    from src.core.migration_utils import has_index, has_table

    insp = sa.inspect(op.get_bind())

    if has_index(
        "lot_consumptions", "ix_lot_consumptions_order_line_item_id", insp=insp
    ):
        op.drop_index(
            "ix_lot_consumptions_order_line_item_id", table_name="lot_consumptions"
        )
    if has_index("lot_consumptions", "ix_lot_consumptions_sale_id", insp=insp):
        op.drop_index("ix_lot_consumptions_sale_id", table_name="lot_consumptions")
    if has_table("lot_consumptions", insp=insp):
        op.drop_table("lot_consumptions")
