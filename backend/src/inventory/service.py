"""Inventory domain business logic."""

import uuid
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.inventory.models import InventoryLevel, MovementType, StockMovement
from src.inventory.schemas import DepletionForecastRead

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Inventory initialization
# ---------------------------------------------------------------------------


async def initialize_inventory(
    db: AsyncSession,
    product_id: uuid.UUID,
    user_id: uuid.UUID,
    initial_stock: int = 0,
    low_stock_threshold: int = 10,
) -> InventoryLevel:
    """Create an InventoryLevel record for a newly created product."""
    inventory = InventoryLevel(
        product_id=product_id,
        quantity_on_hand=initial_stock,
        quantity_reserved=0,
        low_stock_threshold=low_stock_threshold,
    )
    db.add(inventory)
    await db.flush()

    if initial_stock > 0:
        movement = StockMovement(
            product_id=product_id,
            movement_type=MovementType.MANUAL_ADD,
            quantity_change=initial_stock,
            quantity_before=0,
            quantity_after=initial_stock,
            reason="Initial stock on product creation",
            performed_by=user_id,
        )
        db.add(movement)
        await db.flush()

    await logger.ainfo(
        "inventory_initialized",
        product_id=str(product_id),
        initial_stock=initial_stock,
    )
    return inventory


# ---------------------------------------------------------------------------
# Stock level queries
# ---------------------------------------------------------------------------


async def get_inventory_level(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> InventoryLevel:
    """Get the current inventory level for a product."""
    result = await db.execute(
        select(InventoryLevel).where(InventoryLevel.product_id == product_id)
    )
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise ProductStockNotFoundError(product_id)
    return inventory


async def list_inventory_levels(
    db: AsyncSession,
    *,
    low_stock_only: bool = False,
) -> list[InventoryLevel]:
    """List all inventory levels, optionally filtered to low stock only."""
    query = select(InventoryLevel)
    if low_stock_only:
        query = query.where(
            InventoryLevel.quantity_on_hand <= InventoryLevel.low_stock_threshold
        )
    query = query.order_by(InventoryLevel.quantity_on_hand.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Stock adjustments
# ---------------------------------------------------------------------------


async def adjust_stock(
    db: AsyncSession,
    product_id: uuid.UUID,
    quantity_change: int,
    movement_type: str,
    reason: str,
    user_id: uuid.UUID,
    reference_id: uuid.UUID | None = None,
    reference_type: str | None = None,
) -> InventoryLevel:
    """Adjust stock and create a StockMovement audit record."""
    inventory = await get_inventory_level(db, product_id)
    quantity_before = inventory.quantity_on_hand
    new_quantity = quantity_before + quantity_change

    if new_quantity < 0:
        raise InvalidStockAdjustmentError(product_id, quantity_change, quantity_before)

    inventory.quantity_on_hand = new_quantity

    # Update last_replenished_at if adding stock
    if quantity_change > 0:
        inventory.last_replenished_at = datetime.now(timezone.utc)

    movement = StockMovement(
        product_id=product_id,
        movement_type=MovementType(movement_type),
        quantity_change=quantity_change,
        quantity_before=quantity_before,
        quantity_after=new_quantity,
        reference_id=reference_id,
        reference_type=reference_type,
        reason=reason,
        performed_by=user_id,
    )
    db.add(movement)
    await db.flush()

    await logger.ainfo(
        "stock_adjusted",
        product_id=str(product_id),
        movement_type=movement_type,
        change=quantity_change,
        new_quantity=new_quantity,
    )
    return inventory


# ---------------------------------------------------------------------------
# Stock movement history
# ---------------------------------------------------------------------------


async def get_stock_movements(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> list[StockMovement]:
    """Get stock movement history for a product."""
    result = await db.execute(
        select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.id.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Depletion forecast
# ---------------------------------------------------------------------------


async def calculate_depletion_forecast(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> DepletionForecastRead:
    """Compute predicted stock-out date based on 30-day sales velocity."""
    inventory = await get_inventory_level(db, product_id)

    # Sum all sale depletions for velocity estimate
    result = await db.execute(
        select(func.coalesce(func.sum(func.abs(StockMovement.quantity_change)), 0))
        .where(StockMovement.product_id == product_id)
        .where(StockMovement.movement_type == MovementType.SALE_DEPLETION)
    )
    total_depleted = result.scalar() or 0

    if total_depleted == 0:
        return DepletionForecastRead(
            product_id=product_id,
            current_stock=inventory.quantity_on_hand,
            avg_daily_depletion=0.0,
            days_until_stockout=None,
            estimated_stockout_date=None,
        )

    avg_daily = total_depleted / 30.0
    days_left = int(inventory.quantity_on_hand / avg_daily) if avg_daily > 0 else None
    stockout_date = (
        date.today() + timedelta(days=days_left) if days_left is not None else None
    )

    return DepletionForecastRead(
        product_id=product_id,
        current_stock=inventory.quantity_on_hand,
        avg_daily_depletion=round(avg_daily, 2),
        days_until_stockout=days_left,
        estimated_stockout_date=stockout_date,
    )
