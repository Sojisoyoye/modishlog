"""add_perf_indexes_sales_stock_movements_product_id

Revision ID: ee16369ce64b
Revises: 38346d09aac0
Create Date: 2026-09-16 09:05:35.248116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee16369ce64b'
down_revision: Union[str, None] = '38346d09aac0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deferred, not module-level — see src/core/migration_utils.py's
    # docstring ("IMPORTING THIS MODULE") for why.
    from src.core.migration_utils import has_index

    insp = sa.inspect(op.get_bind())

    # 370b5f18aa74 (add_perf_indexes) added sales.customer_id/payment_status/
    # (transaction_id, created_at) but missed product_id, despite it being
    # filtered directly (sales/service.py, pricing/service.py, ai_engine/
    # service.py) and joined on repeatedly across reports.
    if not has_index("sales", "ix_sales_product_id", insp=insp):
        op.create_index("ix_sales_product_id", "sales", ["product_id"])

    # stock_movements has never had any index beyond its bare FK constraint.
    # Composite (product_id, created_at) matches the actual hot-path query
    # in inventory/service.py's get_stock_movements() -- WHERE product_id =
    # ... ORDER BY created_at DESC -- and still serves plain product_id-only
    # filters (e.g. calculate_depletion_forecast) via the leftmost-prefix
    # rule, so a separate single-column index would just be redundant.
    if not has_index(
        "stock_movements", "ix_stock_movements_product_id_created_at", insp=insp
    ):
        op.create_index(
            "ix_stock_movements_product_id_created_at",
            "stock_movements",
            ["product_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_stock_movements_product_id_created_at", table_name="stock_movements")
    op.drop_index("ix_sales_product_id", table_name="sales")
