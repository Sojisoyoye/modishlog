"""Inventory domain business logic."""

import uuid
from collections.abc import Collection
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from decimal import ROUND_HALF_UP, Decimal

from src.inventory.models import (
    FifoConsumption,
    InventoryBatch,
    InventoryLevel,
    MovementType,
    StockMovement,
)
from src.inventory.schemas import DepletionForecastRead
from src.products.models import Product
from src.core.query_helpers import reverse_ledger_consumption, variant_or_untagged_filter

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


def inventory_level_variant_filter(variant_id: uuid.UUID | None):
    """WHERE-clause fragment scoping InventoryLevel rows to a specific
    variant, or to the aggregate (variant_id=NULL) row when variant_id is
    None — the exact-match version of inventory_batch_variant_filter()
    above, used everywhere an InventoryLevel row is looked up for a
    specific (product_id, variant_id) pair. Centralized so this exact
    "variant_id == X, else variant_id IS NULL" comparison — repeated
    across get_inventory_level(), adjust_stock(), and
    ensure_inventory_level_exists() — can't silently drift between them.
    """
    if variant_id is not None:
        return InventoryLevel.variant_id == variant_id
    return InventoryLevel.variant_id.is_(None)


async def ensure_inventory_level_exists(
    db: AsyncSession,
    product_id: uuid.UUID,
    variant_id: uuid.UUID | None,
    low_stock_threshold: int | None = None,
) -> None:
    """Create a zeroed InventoryLevel(product_id, variant_id) row if one
    doesn't already exist.

    adjust_stock() is a strict UPDATE-only lookup, never an upsert — it
    raises ProductStockNotFoundError if no row matches. products/
    service.py's create_variant() only ever inserts the ProductVariant
    row, never a matching InventoryLevel row, so any caller that can pass
    a variant_id whose InventoryLevel row might not exist yet (e.g.
    crediting a PO delivery to a variant for the first time) must call
    this first, or adjust_stock() fails outright for a perfectly valid
    product/variant.

    When low_stock_threshold isn't given and this is a variant row
    (variant_id is not None), the new row inherits the product's
    aggregate-row threshold — the business's already-configured
    expectation for this product — instead of a hardcoded default that
    would silently override it. Falls back to 10 only if no aggregate row
    exists either.

    The existence check and insert are not atomic — two concurrent callers
    backfilling the same (product_id, variant_id) pair for the first time
    (e.g. two POs for the same new variant delivered at once) can both
    pass the check before either commits. The insert is wrapped in its own
    SAVEPOINT so the loser's unique-index violation is caught and
    swallowed rather than propagating as an unhandled 500 — the row exists
    either way once the winner's insert commits.
    """
    query = select(InventoryLevel).where(
        InventoryLevel.product_id == product_id,
        inventory_level_variant_filter(variant_id),
    )
    result = await db.execute(query)
    if result.scalar_one_or_none() is not None:
        return

    threshold = low_stock_threshold
    if threshold is None:
        threshold = 10
        if variant_id is not None:
            aggregate_result = await db.execute(
                select(InventoryLevel.low_stock_threshold).where(
                    InventoryLevel.product_id == product_id,
                    InventoryLevel.variant_id.is_(None),
                )
            )
            aggregate_threshold = aggregate_result.scalar_one_or_none()
            if aggregate_threshold is not None:
                threshold = aggregate_threshold

    try:
        async with db.begin_nested():
            db.add(
                InventoryLevel(
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    low_stock_threshold=threshold,
                )
            )
            await db.flush()
    except IntegrityError:
        # A concurrent caller won the race and created the row first —
        # it exists now either way, which is all this function promises.
        pass


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

    query = select(InventoryLevel).where(
        InventoryLevel.product_id == product_id,
        inventory_level_variant_filter(variant_id),
    )

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
        base_query = base_query.where(InventoryLevel.product_id.in_(scoped_product_ids))
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
        base_query.order_by(InventoryLevel.quantity_on_hand.asc())
        .offset(offset)
        .limit(page_size)
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

    inv_query = (
        select(InventoryLevel)
        .where(
            InventoryLevel.product_id == product_id,
            inventory_level_variant_filter(variant_id),
        )
        .with_for_update()
    )

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


def inventory_batch_variant_filter(variant_id: uuid.UUID | None):
    """WHERE-clause fragment scoping InventoryBatch rows to a deduction's
    variant_id — see variant_or_untagged_filter() (src/core/query_helpers.py)
    for the shared rule this applies.

    Shared by fifo_deduct() and data_import/recompute.py's insufficient-
    batches pre-check — both need the exact same "which batches would
    actually be drawn from" answer, or the pre-check could count batches
    fifo_deduct() would never touch and report a wrong understated/
    overstated COGS warning.
    """
    return variant_or_untagged_filter(InventoryBatch.variant_id, variant_id)


async def fifo_deduct(
    db: AsyncSession,
    product_id: uuid.UUID,
    quantity: int,
    variant_id: uuid.UUID | None = None,
    sale_id: uuid.UUID | None = None,
) -> Decimal:
    """FIFO cost matching: deduct quantity from oldest batches first.

    Pass sale_id so voiding this sale, or rolling back the import it came
    from, can reverse its FIFO consumption exactly instead of guessing
    which batches to credit back — every real caller (create_sale(),
    data_import's FIFO COGS step) should pass it; omitting it silently
    reproduces the original "can't be reversed" gap this ledger exists to
    close.

    Returns total FIFO COGS for the consumed units.
    """
    result = await db.execute(
        select(InventoryBatch)
        .where(
            InventoryBatch.product_id == product_id,
            InventoryBatch.quantity_remaining > 0,
            inventory_batch_variant_filter(variant_id),
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
        if sale_id is not None:
            db.add(
                FifoConsumption(
                    sale_id=sale_id,
                    batch_id=batch.id,
                    quantity_consumed=consume,
                )
            )

    if remaining_to_deduct > 0:
        await logger.awarning(
            "fifo_insufficient_batches",
            product_id=str(product_id),
            requested=quantity,
            unmatched=remaining_to_deduct,
        )

    await db.flush()
    return total_cogs.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


async def reverse_fifo_consumption(
    db: AsyncSession, sale_ids: Collection[uuid.UUID]
) -> None:
    """Restore InventoryBatch.quantity_remaining for every batch the given
    sales consumed via fifo_deduct(), then remove their consumption ledger
    rows.

    Used by void_sale() (a single sale) and data_import's rollback_job()
    (every imported sale being rolled back) — both need to undo FIFO batch
    consumption exactly, using the FifoConsumption ledger fifo_deduct()
    wrote, rather than guessing which batches to credit back or leaving
    them permanently short.

    A batch that no longer exists (e.g. it was itself created by an
    import that's being rolled back, and loader_rollback() deletes
    InventoryBatch rows separately) is silently skipped — there's nothing
    to restore a deleted batch to.

    Delegates the actual algorithm to reverse_ledger_consumption()
    (src/core/query_helpers.py), shared with orders/service.py's
    reverse_lot_consumption() (task 170).
    """
    await reverse_ledger_consumption(
        db,
        sale_ids,
        ledger_model=FifoConsumption,
        ledger_sale_id_col=FifoConsumption.sale_id,
        ledger_target_id_col=FifoConsumption.batch_id,
        ledger_quantity_col=FifoConsumption.quantity_consumed,
        target_model=InventoryBatch,
        target_quantity_col=InventoryBatch.quantity_remaining,
        zero=0,
        cast=int,
    )


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
