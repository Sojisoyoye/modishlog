"""add original_amount/original_currency to order_payments

Revision ID: c3e5f8a1b2d4
Revises: 202e2d0f7c04
Create Date: 2026-08-12 14:00:00.000000

Idempotent — see src/core/migration_utils.py.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3e5f8a1b2d4"
down_revision: Union[str, None] = "202e2d0f7c04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.core.migration_utils import has_column

    insp = sa.inspect(op.get_bind())

    if not has_column("order_payments", "original_amount", insp=insp):
        op.add_column(
            "order_payments",
            sa.Column("original_amount", sa.Numeric(18, 6), nullable=True),
        )
    if not has_column("order_payments", "original_currency", insp=insp):
        op.add_column(
            "order_payments",
            sa.Column("original_currency", sa.String(3), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("order_payments", "original_currency")
    op.drop_column("order_payments", "original_amount")
