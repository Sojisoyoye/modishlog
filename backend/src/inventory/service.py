"""Inventory domain business logic."""

import uuid
from collections.abc import Collection
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from decimal import ROUND_HALF_UP, Decimal

from src.inventory.models import (
    InventoryBatch,
    InventoryLevel,
    MovementType,
    StockMovement,
)
from src.inventory.schemas import DepletionForecastRead
from src.products.models import Product

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
    business_id: uuid.UUID | None = None,
    variant_id: uuid.UUID | None = None,
) -> InventoryLevel:
    """Get the current inventory level for a product (or a specific variant).

    When variant_id is provided the query is scoped to that (product_id, variant_id)
    pair; otherwise only rows with variant_id IS NULL are returned so that aggregate
    (non-variant) stock is not confused with any variant row.

    If business_id is provided, verifies the product belongs to that business
    before returning its inventory level.
    """
    if business_id is not None:
        product_result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.business_id == business_id,
            )
        )
        if product_result.scalar_one_or_none() is None:
            raise ProductStockNotFoundError(product_id)

    query = select(InventoryLevel).where(InventoryLevel.product_id == product_id)
    if variant_id is not None:
        query = query.where(InventoryLevel.variant_id == variant_id)
    else:
        query = query.where(InventoryLevel.variant_id.is_(None))

    result = await db.execute(query)
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise ProductStockNotFoundError(product_id)
    return inventory


def inventory_on_hand_by_product_subquery(
    product_ids: Collection[uuid.UUID] | None = None,
):
    """SQLAlchemy subquery aggregating every InventoryLevel row for each
    product into one on-hand quantity and one (most restrictive)
    low-stock threshold.

    A product can have more than one InventoryLevel row — the aggregate
    (variant_id=NULL) row plus one row per variant — since the migration
    that let a product have variant-level stock alongside its aggregate
    row. Any caller that needs one on-hand figure per product (not per
    variant, e.g. a report, a stock count, or a low-stock check) must
    aggregate across all of a product's rows or it will duplicate/miscount
    that product wherever it joins InventoryLevel directly by product_id.
    Centralized here so a new caller doesn't have to rediscover this.

    Pass product_ids when the caller already knows which products it
    needs (e.g. a stock count's own item list) — it scopes the GROUP BY
    itself rather than aggregating every product in the database and
    relying on the outer join to narrow it down afterward.
    """
    query = select(
        InventoryLevel.product_id,
        func.sum(InventoryLevel.quantity_on_hand).label("quantity_on_hand"),
        func.min(InventoryLevel.low_stock_threshold).label("low_stock_threshold"),
    )
    if product_ids is not None:
        query = query.where(InventoryLevel.product_id.in_(product_ids))
    return query.group_by(InventoryLevel.product_id).subquery()


async def list_inventory_levels(
    db: AsyncSession,
    *,
    business_id: uuid.UUID | None = None,
    low_stock_only: bool = False,
    page: int = 1,
    page_size: int = 200,
) -> tuple[list[InventoryLevel], int]:
    """List inventory levels with pagination. Returns (items, total).

    If business_id is provided, only returns inventory for products belonging
    to that business (scoped through the products table).
    """
    base_query = select(InventoryLevel)
    if business_id is not None:
        scoped_product_ids = select(Product.id).where(
            Product.business_id == business_id
        )
        base_query = base_query.where(
            InventoryLevel.product_id.in_(scoped_product_ids)
        )
    if low_stock_only:
        base_query = base_query.where(
            InventoryLevel.quantity_on_hand <= InventoryLevel.low_stock_threshold
        )
    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar()
    offset = (page - 1) * page_size
    items_result = await db.execute(
        base_query.order_by(InventoryLevel.quantity_on_hand.asc()).offset(offset).limit(page_size)
    )
    return list(items_result.scalars().all()), total


# ---------------------------------------------------------------------------
# Threshold update
# ---------------------------------------------------------------------------


async def update_threshold(
    db: AsyncSession,
    product_id: uuid.UUID,
    low_stock_threshold: int,
    business_id: uuid.UUID | None = None,
) -> InventoryLevel:
    """Update the low-stock threshold for a product."""
    inventory = await get_inventory_level(db, product_id, business_id=business_id)
    inventory.low_stock_threshold = low_stock_threshold
    await db.flush()
    await logger.ainfo(
        "threshold_updated",
        product_id=str(product_id),
        new_threshold=low_stock_threshold,
    )
    return inventory


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
    business_id: uuid.UUID | None = None,
    variant_id: uuid.UUID | None = None,
    migration_id: uuid.UUID | None = None,
) -> InventoryLevel:
    """Adjust stock and create a StockMovement audit record.

    When variant_id is provided the adjustment targets that variant's inventory
    row (product_id, variant_id) and records the variant on the StockMovement.

    migration_id tags the StockMovement row directly at insert time, for
    callers (e.g. data_import's recompute/rollback) that need to find their
    own movements later without a follow-up UPDATE keyed on reference_id/
    reference_type — fields other domains also use, so a blanket UPDATE on
    them risks retagging unrelated rows.
    """
    if business_id is not None:
        product_result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.business_id == business_id,
            )
        )
        if product_result.scalar_one_or_none() is None:
            raise ProductStockNotFoundError(product_id)

    inv_query = select(InventoryLevel).where(InventoryLevel.product_id == product_id)
    if variant_id is not None:
        inv_query = inv_query.where(InventoryLevel.variant_id == variant_id)
    else:
        inv_query = inv_query.where(InventoryLevel.variant_id.is_(None))
    inv_query = inv_query.with_for_update()

    result = await db.execute(inv_query)
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise ProductStockNotFoundError(product_id)
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
        variant_id=variant_id,
        movement_type=MovementType(movement_type),
        quantity_change=quantity_change,
        quantity_before=quantity_before,
        quantity_after=new_quantity,
        reference_id=reference_id,
        reference_type=reference_type,
        reason=reason,
        performed_by=user_id,
        migration_id=migration_id,
    )
    db.add(movement)
    await db.flush()

    await logger.ainfo(
        "stock_adjusted",
        product_id=str(product_id),
        variant_id=str(variant_id) if variant_id else None,
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
    business_id: uuid.UUID | None = None,
) -> list[StockMovement]:
    """Get stock movement history for a product.

    If business_id is provided, verifies the product belongs to that business.
    """
    if business_id is not None:
        product_result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.business_id == business_id,
            )
        )
        if product_result.scalar_one_or_none() is None:
            raise ProductStockNotFoundError(product_id)

    result = await db.execute(
        select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.created_at.desc())
    )
    return list(result.scalars().all())


async def list_all_movements(
    db: AsyncSession,
    limit: int = 50,
    business_id: uuid.UUID | None = None,
) -> list[StockMovement]:
    """Return the most recent stock movements across all products.

    If business_id is provided, only returns movements for products belonging
    to that business (scoped through the products table).
    """
    query = select(StockMovement)
    if business_id is not None:
        scoped_product_ids = select(Product.id).where(
            Product.business_id == business_id
        )
        query = query.where(StockMovement.product_id.in_(scoped_product_ids))
    query = query.order_by(StockMovement.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Depletion forecast
# ---------------------------------------------------------------------------


async def calculate_depletion_forecast(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> DepletionForecastRead:
    """Compute predicted stock-out date based on 30-day sales velocity."""
    inventory = await get_inventory_level(db, product_id, business_id=business_id)

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


# ---------------------------------------------------------------------------
# Inventory Batches
# ---------------------------------------------------------------------------


def compute_landed_cost(
    unit_cost_usd: Decimal,
    fx_rate: Decimal,
    logistics_per_unit: Decimal,
) -> Decimal:
    """landed_cost = (unit_cost_usd × fx_rate) + logistics_per_unit."""
    return (unit_cost_usd * fx_rate + logistics_per_unit).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


async def create_batch(
    db: AsyncSession,
    product_id: uuid.UUID,
    order_id: uuid.UUID,
    quantity: int,
    unit_cost_usd: Decimal,
    fx_rate_at_arrival: Decimal,
    logistics_allocation_per_unit: Decimal = Decimal("0"),
    received_at: date | None = None,
    variant_id: uuid.UUID | None = None,
) -> InventoryBatch:
    """Create an inventory batch when an order is delivered.

    variant_id should be set from the PO line item's own variant_id when
    the delivered item is for a specific variant, so fifo_deduct() can
    later scope FIFO consumption to that variant instead of pooling it
    with every other variant of the same product.
    """
    landed = compute_landed_cost(
        unit_cost_usd, fx_rate_at_arrival, logistics_allocation_per_unit
    )
    batch = InventoryBatch(
        product_id=product_id,
        order_id=order_id,
        variant_id=variant_id,
        quantity_received=quantity,
        quantity_remaining=quantity,
        unit_cost_usd=unit_cost_usd,
        fx_rate_at_arrival=fx_rate_at_arrival,
        logistics_allocation_per_unit=logistics_allocation_per_unit,
        landed_cost_per_unit=landed,
        received_at=received_at or date.today(),
        created_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    await db.flush()

    await logger.ainfo(
        "inventory_batch_created",
        product_id=str(product_id),
        order_id=str(order_id),
        quantity=quantity,
        landed_cost=str(landed),
    )
    return batch


async def get_batches_for_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> list[InventoryBatch]:
    """List batches for a product ordered by received_at ASC (oldest first).

    If business_id is provided, verifies the product belongs to that business.
    """
    if business_id is not None:
        product_result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.business_id == business_id,
            )
        )
        if product_result.scalar_one_or_none() is None:
            raise ProductStockNotFoundError(product_id)

    result = await db.execute(
        select(InventoryBatch)
        .where(InventoryBatch.product_id == product_id)
        .order_by(InventoryBatch.received_at.asc())
    )
    return list(result.scalars().all())


async def fifo_deduct(
    db: AsyncSession,
    product_id: uuid.UUID,
    quantity: int,
    variant_id: uuid.UUID | None = None,
) -> Decimal:
    """FIFO cost matching: deduct quantity from oldest batches first.

    A variant-specific deduction (variant_id given) may draw from that
    variant's own tagged batches AND from untagged (variant_id=NULL)
    batches — stock received before variant tracking existed, or genuinely
    shared stock — but never from a *different* variant's tagged batches,
    which would misattribute that variant's landed cost onto this one. A
    non-variant deduction (variant_id=None) only draws from untagged
    batches, mirroring how InventoryLevel/adjust_stock scope aggregate vs.
    variant-level rows.

    Returns total FIFO COGS for the consumed units.
    """
    variant_filter = (
        or_(
            InventoryBatch.variant_id == variant_id,
            InventoryBatch.variant_id.is_(None),
        )
        if variant_id is not None
        else InventoryBatch.variant_id.is_(None)
    )
    result = await db.execute(
        select(InventoryBatch)
        .where(
            InventoryBatch.product_id == product_id,
            InventoryBatch.quantity_remaining > 0,
            variant_filter,
        )
        .order_by(InventoryBatch.received_at.asc())
        .with_for_update()
    )
    batches = list(result.scalars().all())

    remaining_to_deduct = quantity
    total_cogs = Decimal("0")

    for batch in batches:
        if remaining_to_deduct <= 0:
            break

        consume = min(remaining_to_deduct, batch.quantity_remaining)
        total_cogs += Decimal(str(consume)) * batch.landed_cost_per_unit
        batch.quantity_remaining -= consume
        remaining_to_deduct -= consume

    if remaining_to_deduct > 0:
        await logger.awarning(
            "fifo_insufficient_batches",
            product_id=str(product_id),
            requested=quantity,
            unmatched=remaining_to_deduct,
        )

    await db.flush()
    return total_cogs.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


async def get_liquidation_candidates(
    db: AsyncSession,
    target_ngn: Decimal,
    business_id: uuid.UUID | None = None,
) -> list[dict]:
    """Return batches ordered by cheapest landed cost with discount needed.

    If business_id is provided, only returns batches for products belonging
    to that business (scoped through the products table).
    """
    query = select(InventoryBatch).where(InventoryBatch.quantity_remaining > 0)
    if business_id is not None:
        scoped_product_ids = select(Product.id).where(
            Product.business_id == business_id
        )
        query = query.where(InventoryBatch.product_id.in_(scoped_product_ids))
    query = query.order_by(InventoryBatch.landed_cost_per_unit.asc())
    result = await db.execute(query)
    batches = list(result.scalars().all())

    candidates = []
    for batch in batches:
        batch_value = (
            Decimal(str(batch.quantity_remaining)) * batch.landed_cost_per_unit
        )
        if batch_value > 0 and target_ngn > 0:
            discount_pct = max(
                Decimal("0"),
                Decimal("1") - (target_ngn / batch_value),
            ) * Decimal("100")
        else:
            discount_pct = Decimal("0")

        candidates.append(
            {
                "batch_id": batch.id,
                "product_id": batch.product_id,
                "quantity_remaining": batch.quantity_remaining,
                "landed_cost_per_unit": batch.landed_cost_per_unit,
                "total_batch_value": batch_value,
                "discount_pct_needed": discount_pct.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
            }
        )
    return candidates
