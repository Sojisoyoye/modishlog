"""Post-import recomputation.

etl/loader.py's own docstrings admit what it intentionally leaves stale:
`load()` inserts raw `Sale` rows without ever calling `adjust_stock()`/
`fifo_deduct()` (see `load()`'s comment on `_zeroed_inventory_level()`), and
`rollback()`'s docstring explicitly says reversing a deduped product's
quantity delta "needs delta-based undo... that's the recompute service's
job, not this one." This module is that job: it runs once, after an import
has already committed successfully, using the real inventory/pricing/
ai_engine services (never raw SQL) to deduct stock for imported sales,
compute their FIFO COGS, seed opening price history, raise low-stock alerts,
and refresh AI reorder/price signals.

Every step is isolated — a step (or a single item within a step) failing is
recorded in the returned error list, never raised, so a partial recompute
can never undo the already-committed import. Idempotent: re-running derives
everything fresh from migration_id-tagged rows or checks for an existing
row before creating one, so calling it twice produces the same end state.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_engine.models import ReorderStatus, ReorderSuggestion
from src.ai_engine.service import generate_reorder_suggestions
from src.inventory.models import (
    AlertStatus,
    InventoryLevel,
    LowStockAlert,
    MovementType,
    StockMovement,
)
from src.inventory.service import adjust_stock, fifo_deduct
from src.pricing.exceptions import PricingSuggestionError
from src.pricing.service import compute_suggestion
from src.products.models import PriceHistory, Product
from src.sales.models import Sale

logger = structlog.get_logger()


async def _deduct_imported_sales_stock(
    db: AsyncSession,
    business_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[dict]:
    """Aggregate imported sales per (product, variant) and deduct once per
    group — not once per sale, matching the task's own performance guidance
    (a single aggregate query, not a row-by-row replay).

    Idempotent: if this job's deduction already ran (marked by the tag
    sweep at the end of a prior run), skip entirely rather than deduct the
    same imported sales' stock again — recompute_after_import() can be
    re-triggered manually (POST /jobs/{id}/recompute) after already
    succeeding once.
    """
    already_applied = await db.execute(
        select(StockMovement.id)
        .where(
            StockMovement.reference_id == job_id,
            StockMovement.reference_type == "data_import_recompute",
        )
        .limit(1)
    )
    if already_applied.scalar_one_or_none() is not None:
        return []

    result = await db.execute(
        select(Sale.product_id, Sale.variant_id, func.sum(Sale.quantity))
        .where(Sale.migration_id == job_id)
        .group_by(Sale.product_id, Sale.variant_id)
    )
    groups = result.all()
    if not groups:
        return []

    # adjust_stock() is an UPDATE, not an upsert. load() only ever creates a
    # product-level (variant_id=None) InventoryLevel row for imported
    # products — never a variant-level one. Unlike PO delivery (which
    # reuses transition_status()/create_batch() unmodified and has no
    # variant-aware path — see transform_purchase_orders()'s warning), this
    # step calls adjust_stock() directly and CAN pass variant_id, so create
    # whatever variant-level rows are missing before deducting.
    variant_pairs = {(pid, vid) for pid, vid, _ in groups if vid is not None}
    if variant_pairs:
        variant_ids = {vid for _, vid in variant_pairs}
        existing = await db.execute(
            select(InventoryLevel.product_id, InventoryLevel.variant_id).where(
                InventoryLevel.variant_id.in_(variant_ids)
            )
        )
        existing_pairs = set(existing.all())
        missing = variant_pairs - existing_pairs
        for product_id, variant_id in missing:
            db.add(
                InventoryLevel(
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    low_stock_threshold=10,
                )
            )
        if missing:
            await db.flush()

    errors: list[dict] = []
    any_succeeded = False
    for product_id, variant_id, total_quantity in groups:
        try:
            await adjust_stock(
                db,
                product_id=product_id,
                quantity_change=-int(total_quantity),
                movement_type=MovementType.SALE_DEPLETION.value,
                reason="Post-import stock deduction (aggregated from imported sales)",
                user_id=user_id,
                business_id=business_id,
                variant_id=variant_id,
                reference_id=job_id,
                reference_type="data_import_recompute",
            )
            any_succeeded = True
        except Exception as e:
            await logger.awarning(
                "recompute_stock_deduction_failed",
                product_id=str(product_id),
                variant_id=str(variant_id) if variant_id else None,
                error=str(e),
            )
            errors.append(
                {
                    "step": "deduct_sales_stock",
                    "product_id": str(product_id),
                    "error": str(e),
                }
            )

    if any_succeeded:
        # adjust_stock() has no migration_id param — it never tags the
        # StockMovement rows it creates. Tag them afterward by the
        # reference_id/reference_type just passed in, so rollback's
        # reversal-delta calculation (which sums StockMovement rows tagged
        # with this migration_id) can find them.
        await db.execute(
            update(StockMovement)
            .where(
                StockMovement.reference_id == job_id,
                StockMovement.reference_type == "data_import_recompute",
            )
            .values(migration_id=job_id)
        )
    return errors


async def _compute_fifo_cogs_for_imported_sales(
    db: AsyncSession, job_id: uuid.UUID
) -> list[dict]:
    """For each imported sale, in chronological order per product (matching
    how the batches would actually have been depleted), compute FIFO COGS
    against the InventoryBatch rows created during purchase-order import.

    Idempotent: only processes sales that don't already have fifo_cogs set
    — fifo_deduct() consumes InventoryBatch.quantity_remaining, so re-
    running it against an already-processed sale would double-consume the
    same batches. This also means a re-trigger after a partial failure
    only picks up the sales that didn't get processed last time.
    """
    result = await db.execute(
        select(Sale)
        .where(Sale.migration_id == job_id, Sale.fifo_cogs.is_(None))
        .order_by(Sale.product_id, Sale.sale_date)
    )
    sales = result.scalars().all()

    errors: list[dict] = []
    for sale in sales:
        try:
            cogs = await fifo_deduct(db, sale.product_id, sale.quantity)
        except Exception as e:
            await logger.awarning(
                "recompute_fifo_cogs_failed", sale_id=str(sale.id), error=str(e)
            )
            errors.append(
                {"step": "fifo_cogs", "sale_id": str(sale.id), "error": str(e)}
            )
            continue
        sale.fifo_cogs = cogs
        sale.fifo_gross_profit = sale.total_amount - cogs
    return errors


async def _create_opening_price_history(
    db: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """No price_history import entity exists — create one opening row per
    imported product from its current cost/price, so P&L reports built on
    price_history don't have a gap for the whole pre-import history.

    Idempotent: skips products that already have an opening row from this
    job — a re-trigger (POST /jobs/{id}/recompute) must not create
    duplicates.
    """
    already_seeded = await db.execute(
        select(PriceHistory.product_id).where(PriceHistory.migration_id == job_id)
    )
    already_seeded_ids = set(already_seeded.scalars().all())

    result = await db.execute(select(Product).where(Product.migration_id == job_id))
    products = [p for p in result.scalars().all() if p.id not in already_seeded_ids]
    for product in products:
        db.add(
            PriceHistory(
                product_id=product.id,
                old_unit_cost=product.unit_cost,
                new_unit_cost=product.unit_cost,
                old_selling_price=product.selling_price,
                new_selling_price=product.selling_price,
                effective_date=product.created_at.date()
                if isinstance(product.created_at, datetime)
                else product.created_at,
                reason="Opening balance from import",
                changed_by=user_id,
                migration_id=job_id,
            )
        )
    if products:
        await db.flush()


async def _recompute_low_stock_alerts(db: AsyncSession, job_id: uuid.UUID) -> None:
    """LowStockAlert has no variant_id column — it's a product-level signal
    only, matching the product-level (variant_id=None) InventoryLevel rows
    the loader creates for imported products.
    """
    result = await db.execute(
        select(InventoryLevel, Product.migration_id)
        .join(Product, Product.id == InventoryLevel.product_id)
        .where(Product.migration_id == job_id, InventoryLevel.variant_id.is_(None))
    )
    rows = result.all()

    now = datetime.now(timezone.utc)
    for inventory, _ in rows:
        if inventory.quantity_on_hand > inventory.low_stock_threshold:
            continue
        existing = await db.execute(
            select(LowStockAlert).where(
                LowStockAlert.product_id == inventory.product_id,
                LowStockAlert.status == AlertStatus.ACTIVE,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        db.add(
            LowStockAlert(
                product_id=inventory.product_id,
                threshold=inventory.low_stock_threshold,
                current_quantity=inventory.quantity_on_hand,
                triggered_at=now,
            )
        )
    if rows:
        await db.flush()


async def _recompute_ai_signals(
    db: AsyncSession, business_id: uuid.UUID, job_id: uuid.UUID
) -> list[dict]:
    """Regenerate reorder suggestions for the whole business (they aren't
    migration_id-tagged, so a full regenerate — not a scoped one — is the
    only way to keep them consistent with the now-current stock levels) and
    price suggestions for the products this import actually created.
    """
    errors: list[dict] = []

    await db.execute(
        delete(ReorderSuggestion).where(
            ReorderSuggestion.business_id == business_id,
            ReorderSuggestion.status == ReorderStatus.PENDING,
        )
    )
    try:
        await generate_reorder_suggestions(db, business_id)
    except Exception as e:
        await logger.awarning("recompute_reorder_suggestions_failed", error=str(e))
        errors.append({"step": "reorder_suggestions", "error": str(e)})

    result = await db.execute(select(Product.id).where(Product.migration_id == job_id))
    product_ids = result.scalars().all()
    for product_id in product_ids:
        try:
            await compute_suggestion(db, product_id)
        except PricingSuggestionError as e:
            errors.append(
                {
                    "step": "price_suggestion",
                    "product_id": str(product_id),
                    "error": str(e),
                }
            )
    return errors


async def recompute_after_import(
    db: AsyncSession,
    business_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Orchestrates every recompute step. Each step is wrapped individually
    — an unhandled exception escaping a step (distinct from the per-item
    errors each step already catches itself) still must not stop the
    remaining, independent steps from running.
    """
    errors: list[dict] = []

    try:
        errors.extend(
            await _deduct_imported_sales_stock(db, business_id, job_id, user_id)
        )
    except Exception as e:
        await logger.aexception("recompute_step_failed", step="deduct_sales_stock")
        errors.append({"step": "deduct_sales_stock", "error": str(e)})

    try:
        errors.extend(await _compute_fifo_cogs_for_imported_sales(db, job_id))
    except Exception as e:
        await logger.aexception("recompute_step_failed", step="fifo_cogs")
        errors.append({"step": "fifo_cogs", "error": str(e)})

    try:
        await _create_opening_price_history(db, job_id, user_id)
    except Exception as e:
        await logger.aexception("recompute_step_failed", step="opening_price_history")
        errors.append({"step": "opening_price_history", "error": str(e)})

    try:
        await _recompute_low_stock_alerts(db, job_id)
    except Exception as e:
        await logger.aexception("recompute_step_failed", step="low_stock_alerts")
        errors.append({"step": "low_stock_alerts", "error": str(e)})

    try:
        errors.extend(await _recompute_ai_signals(db, business_id, job_id))
    except Exception as e:
        await logger.aexception("recompute_step_failed", step="ai_signals")
        errors.append({"step": "ai_signals", "error": str(e)})

    return {"errors": errors}
