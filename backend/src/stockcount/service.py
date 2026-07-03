"""Stock count service — create, update, finalize, read."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.inventory.models import InventoryLevel
from src.orders.models import OrderLineItem
from src.products.models import Product
from src.stockcount.exceptions import StockCountFinalizedError, StockCountNotFoundError
from src.stockcount.models import (
    StockCount,
    StockCountItem,
    StockCountStatus,
    StockCountType,
)

logger = structlog.get_logger(__name__)


async def create_stock_count(
    db: AsyncSession,
    count_date: date,
    count_type: str,
    notes: Optional[str],
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> StockCount:
    """Create a DRAFT stock count session and pre-populate items (no snapshot yet)."""
    sc = StockCount(
        business_id=business_id,
        count_date=count_date,
        count_type=StockCountType(count_type),
        status=StockCountStatus.DRAFT,
        notes=notes,
        created_by=user_id,
    )
    db.add(sc)
    await db.flush()

    # Scope to this business's products via subquery (InventoryLevel/OrderLineItem
    # don't yet have their own business_id column — Foundation PR pending)
    scoped_product_ids = select(Product.id).where(Product.business_id == business_id)

    if StockCountType(count_type) == StockCountType.PRODUCT:
        result = await db.execute(
            select(InventoryLevel).where(
                InventoryLevel.product_id.in_(scoped_product_ids)
            )
        )
        levels = result.scalars().all()
        for level in levels:
            db.add(
                StockCountItem(
                    stock_count_id=sc.id,
                    product_id=level.product_id,
                    order_line_item_id=None,
                    system_quantity_at_count=None,
                )
            )
    else:
        result = await db.execute(
            select(OrderLineItem).where(
                OrderLineItem.units_remaining > 0,
                OrderLineItem.product_id.in_(scoped_product_ids),
            )
        )
        lots = result.scalars().all()
        for lot in lots:
            db.add(
                StockCountItem(
                    stock_count_id=sc.id,
                    product_id=lot.product_id,
                    order_line_item_id=lot.id,
                    system_quantity_at_count=None,
                )
            )

    await db.flush()
    await logger.ainfo(
        "stock_count_created", stock_count_id=str(sc.id), count_type=count_type
    )
    return sc


async def update_count_item(
    db: AsyncSession,
    stock_count_id: uuid.UUID,
    item_id: uuid.UUID,
    counted_quantity: Decimal,
    business_id: uuid.UUID,
) -> StockCountItem:
    """Update counted_quantity on an item. Only allowed in DRAFT."""
    sc_result = await db.execute(
        select(StockCount).where(
            StockCount.id == stock_count_id,
            StockCount.business_id == business_id,
        )
    )
    sc = sc_result.scalar_one_or_none()
    if sc is None:
        raise StockCountNotFoundError(stock_count_id)
    if sc.status == StockCountStatus.FINALIZED:
        raise StockCountFinalizedError(stock_count_id)

    item_result = await db.execute(
        select(StockCountItem)
        .where(
            StockCountItem.id == item_id,
            StockCountItem.stock_count_id == stock_count_id,
        )
        .options(selectinload(StockCountItem.product))
    )
    item = item_result.scalar_one_or_none()
    if item is None:
        raise StockCountNotFoundError(item_id)

    item.counted_quantity = counted_quantity
    await db.flush()
    return item


async def finalize_stock_count(
    db: AsyncSession,
    stock_count_id: uuid.UUID,
    business_id: uuid.UUID,
) -> StockCount:
    """Snapshot live system stock into items, then lock the session as FINALIZED."""
    result = await db.execute(
        select(StockCount)
        .where(
            StockCount.id == stock_count_id,
            StockCount.business_id == business_id,
        )
        .options(selectinload(StockCount.items).selectinload(StockCountItem.product))
    )
    sc = result.scalar_one_or_none()
    if sc is None:
        raise StockCountNotFoundError(stock_count_id)
    if sc.status == StockCountStatus.FINALIZED:
        raise StockCountFinalizedError(stock_count_id)

    # Batch-fetch system quantities — one query regardless of item count
    if sc.count_type == StockCountType.PRODUCT:
        product_ids = [item.product_id for item in sc.items]
        inv_result = await db.execute(
            select(InventoryLevel).where(InventoryLevel.product_id.in_(product_ids))
        )
        inv_by_product = {inv.product_id: inv for inv in inv_result.scalars().all()}
        for item in sc.items:
            inv = inv_by_product.get(item.product_id)
            item.system_quantity_at_count = (
                Decimal(str(inv.quantity_on_hand)) if inv else Decimal("0")
            )
    else:
        lot_ids = [
            item.order_line_item_id for item in sc.items if item.order_line_item_id
        ]
        lot_result = await db.execute(
            select(OrderLineItem).where(OrderLineItem.id.in_(lot_ids))
        )
        lot_by_id = {lot.id: lot for lot in lot_result.scalars().all()}
        for item in sc.items:
            lot = lot_by_id.get(item.order_line_item_id)
            item.system_quantity_at_count = (
                lot.units_remaining
                if (lot and lot.units_remaining is not None)
                else Decimal("0")
            )

    sc.status = StockCountStatus.FINALIZED
    sc.finalized_at = datetime.now(timezone.utc)
    await db.flush()

    await logger.ainfo("stock_count_finalized", stock_count_id=str(stock_count_id))
    return sc


async def get_stock_count(
    db: AsyncSession,
    stock_count_id: uuid.UUID,
    business_id: uuid.UUID,
) -> StockCount:
    """Return a single stock count with all items loaded."""
    result = await db.execute(
        select(StockCount)
        .where(
            StockCount.id == stock_count_id,
            StockCount.business_id == business_id,
        )
        .options(selectinload(StockCount.items).selectinload(StockCountItem.product))
    )
    sc = result.scalar_one_or_none()
    if sc is None:
        raise StockCountNotFoundError(stock_count_id)
    return sc


async def list_stock_counts(
    db: AsyncSession,
    business_id: uuid.UUID,
) -> list[StockCount]:
    """Return all stock counts for a business, newest-first, with item count loaded."""
    result = await db.execute(
        select(StockCount)
        .where(StockCount.business_id == business_id)
        .options(selectinload(StockCount.items))
        .order_by(StockCount.created_at.desc())
    )
    return list(result.scalars().all())
