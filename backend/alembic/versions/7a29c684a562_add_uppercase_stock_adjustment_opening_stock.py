"""add_uppercase_stock_adjustment_opening_stock

Revision ID: 7a29c684a562
Revises: 9100b1b36d72
Create Date: 2026-07-12 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "7a29c684a562"
down_revision: Union[str, None] = "9100b1b36d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The movementtype Postgres enum has real schema drift: its original 6
    # labels (5f003722d7b8_initial_schema) were created upper-case
    # ('SALE_DEPLETION', etc.), matching how the SQLAlchemy Enum(MovementType)
    # column (no values_callable) has always serialized every insert — via
    # the Python enum's .name, not .value. Every StockMovement row ever
    # written uses these upper-case labels; confirmed against production
    # data (SALE_DEPLETION/MANUAL_ADD/ORDER_RECEIVED, 100% upper-case, zero
    # rows using any lower-case label).
    #
    # A later migration (5ee86806d6dc_add_migration_v2_columns) added
    # 'stock_adjustment'/'opening_stock' in lower-case instead of matching
    # that established convention — those two labels have been permanently
    # unusable ever since (inserting MovementType.STOCK_ADJUSTMENT tries to
    # write 'STOCK_ADJUSTMENT', which doesn't exist).
    #
    # Fix: add the upper-case labels actually needed to match the
    # convention the other 6 already use. No values_callable change and no
    # data migration are needed — the column's existing (unconventional but
    # working) serialization behavior already matches 100% of existing
    # data; switching it to values_callable would instead require rewriting
    # every existing row's stored value, a much larger and riskier change
    # for the same outcome. The two now-orphaned lower-case labels are left
    # in place — Postgres has no ALTER TYPE ... DROP VALUE, so removing
    # them would require a full type recreation; they're harmless and
    # simply never referenced by the ORM.
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'STOCK_ADJUSTMENT'")
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'OPENING_STOCK'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — removing an enum label
    # requires recreating the whole type (and remapping every dependent
    # column), which is a much larger and riskier operation than adding
    # one was. Left as a no-op, matching this repo's own precedent
    # (5ee86806d6dc's downgrade doesn't reverse its ADD VALUE statements
    # either). The added labels are inert until the application code
    # references them.
    pass
