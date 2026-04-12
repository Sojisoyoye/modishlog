"""add_fx_rate_at_delivery_to_orders

Revision ID: a7b8c9d0e1f2
Revises: e276548633ad, f6a7b8c9d0e1
Create Date: 2026-04-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str]] = ("e276548633ad", "f6a7b8c9d0e1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column(
            "fx_rate_at_delivery",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("purchase_orders", "fx_rate_at_delivery")
