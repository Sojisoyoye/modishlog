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
    InventoryBatch,
    InventoryLevel,
    LowStockAlert,
    MovementType,
    StockMovement,
)
from src.inventory.service import adjust_stock, fifo_deduct
from src.pricing.service import compute_suggestion
from src.products.models import PriceHistory, Product
from src.sales.models import Sale

logger = structlog.get_logger()


async def run_isolated(
    db: AsyncSession,
    factory,
    *,
    log_event: str,
    error_entry: dict,
    silent_exceptions: tuple = (),
):
    """Runs factory() — a zero-arg async callable performing one item-level
    DB write — inside its own nested SAVEPOINT.

    Every recompute/rollback loop that does one DB-mutating operation per
    item (per sale, per product, per suggestion) needs this: a per-item
    try/except alone only guards against the specific Python-level
    exceptions each caller anticipates. A genuine DB-level failure
    (constraint violation, lock timeout) inside the operation's own flush
    leaves the underlying Postgres transaction "aborted" until rolled
    back — every subsequent db.execute()/flush() call, for the rest of
    that loop and every later step sharing the same outer transaction,
    would fail too, even though the try/except appears to isolate
    failures. The SAVEPOINT gives this one item's failure somewhere to
    roll back to that doesn't touch anything outside it.

    Returns (result, None) on success, or (None, error_dict) on failure,
    where error_dict is error_entry with an "error" key added — unless the
    exception is one of silent_exceptions (an entirely expected outcome
    for some callers, e.g. "this product was already deleted"), in which
    case it returns (None, None) with nothing logged or recorded.
    """
    try:
        async with db.begin_nested():
            result = await factory()
        return result, None
    except silent_exceptions:
        return None, None
    except Exception as e:
        await logger.awarning(log_event, error=str(e))
        return None, {**error_entry, "error": str(e)}


async def _deduct_imported_sales_stock(
    db: AsyncSession,
    business_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[dict]:
    """Aggregate imported sales per (product, variant) and deduct once per
    group — not once per sale, matching the task's own performance guidance
    (a single aggregate query, not a row-by-row replay).

    Idempotent per group: a re-trigger (POST /jobs/{id}/recompute) skips
    only the (product, variant) groups already tagged by a prior run's tag
    sweep, and still retries whatever group failed or was never reached
    last time — a step-level "any tag exists -> skip everything" check
    would permanently strand any group that failed on the first attempt.
    """
    already_applied = await db.execute(
        select(StockMovement.product_id, StockMovement.variant_id).where(
            StockMovement.reference_id == job_id,
            StockMovement.reference_type == "data_import_recompute",
        )
    )
    already_applied_pairs = set(already_applied.all())

    result = await db.execute(
        select(Sale.product_id, Sale.variant_id, func.sum(Sale.quantity))
        .where(Sale.migration_id == job_id)
        .group_by(Sale.product_id, Sale.variant_id)
    )
    groups = [g for g in result.all() if (g[0], g[1]) not in already_applied_pairs]
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
        if missing:
            # Tag the new row with migration_id only if the *product* is
            # also new (migration_id == job_id) — mirrors
            # etl/loader.py's _zeroed_inventory_level() precedent: tagging
            # a deduped (pre-existing) product's row would make rollback
            # incorrectly delete it. A row left untagged here for a new
            # product would instead orphan it from rollback's generic
            # migration_id-scoped delete, and then loader_rollback()'s
            # `DELETE FROM products` would hit an FK violation from this
            # surviving InventoryLevel row still referencing it.
            missing_product_ids = {pid for pid, _ in missing}
            new_products = await db.execute(
                select(Product.id).where(
                    Product.id.in_(missing_product_ids), Product.migration_id == job_id
                )
            )
            new_product_ids = set(new_products.scalars().all())
            for product_id, variant_id in missing:
                db.add(
                    InventoryLevel(
                        product_id=product_id,
                        variant_id=variant_id,
                        quantity_on_hand=0,
                        quantity_reserved=0,
                        low_stock_threshold=10,
                        migration_id=(
                            job_id if product_id in new_product_ids else None
                        ),
                    )
                )
            await db.flush()

    errors: list[dict] = []
    any_succeeded = False
    for product_id, variant_id, total_quantity in groups:
        _, error = await run_isolated(
            db,
            lambda pid=product_id, vid=variant_id, qty=total_quantity: adjust_stock(
                db,
                product_id=pid,
                quantity_change=-int(qty),
                movement_type=MovementType.SALE_DEPLETION.value,
                reason="Post-import stock deduction (aggregated from imported sales)",
                user_id=user_id,
                business_id=business_id,
                variant_id=vid,
                reference_id=job_id,
                reference_type="data_import_recompute",
            ),
            log_event="recompute_stock_deduction_failed",
            error_entry={"step": "deduct_sales_stock", "product_id": str(product_id)},
        )
        if error:
            errors.append(error)
        else:
            any_succeeded = True

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
        # fifo_deduct() only *logs* a warning when batches run short — it
        # still returns whatever partial COGS it could match, with no way
        # for the caller to tell "fully matched" from "understated" from
        # the return value alone. Check first so an understated COGS/
        # overstated gross-profit figure is visible in job.recompute_errors
        # instead of silently looking like a normal result.
        available = await db.execute(
            select(func.sum(InventoryBatch.quantity_remaining)).where(
                InventoryBatch.product_id == sale.product_id,
                InventoryBatch.quantity_remaining > 0,
            )
        )
        available_units = available.scalar() or 0
        if available_units < sale.quantity:
            errors.append(
                {
                    "step": "fifo_cogs",
                    "sale_id": str(sale.id),
                    "error": (
                        f"Only {available_units} of {sale.quantity} units have "
                        "matching purchase-order batches — fifo_cogs/"
                        "fifo_gross_profit for this sale is understated/"
                        "overstated."
                    ),
                }
            )

        cogs, error = await run_isolated(
            db,
            lambda s=sale: fifo_deduct(db, s.product_id, s.quantity),
            log_event="recompute_fifo_cogs_failed",
            error_entry={"step": "fifo_cogs", "sale_id": str(sale.id)},
        )
        if error:
            errors.append(error)
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

    Checks every product this job could plausibly have pushed below
    threshold: products it *created* (whose opening PO-delivered stock
    might already be below whatever threshold applies), and — just as
    importantly — deduped (pre-existing) products it deducted stock from
    via imported sales. Scoping only to newly-created products would miss
    a deduped product's real, current low-stock condition entirely.
    """
    relevant_products = await db.execute(
        select(Product.id)
        .where(Product.migration_id == job_id)
        .union(select(Sale.product_id).where(Sale.migration_id == job_id))
    )
    product_ids = set(relevant_products.scalars().all())
    if not product_ids:
        return

    result = await db.execute(
        select(InventoryLevel).where(
            InventoryLevel.product_id.in_(product_ids),
            InventoryLevel.variant_id.is_(None),
        )
    )
    rows = result.scalars().all()
    below_threshold = [r for r in rows if r.quantity_on_hand <= r.low_stock_threshold]
    if not below_threshold:
        return

    already_active = await db.execute(
        select(LowStockAlert.product_id).where(
            LowStockAlert.product_id.in_([r.product_id for r in below_threshold]),
            LowStockAlert.status == AlertStatus.ACTIVE,
        )
    )
    already_active_ids = set(already_active.scalars().all())

    now = datetime.now(timezone.utc)
    for inventory in below_threshold:
        if inventory.product_id in already_active_ids:
            continue
        db.add(
            LowStockAlert(
                product_id=inventory.product_id,
                threshold=inventory.low_stock_threshold,
                current_quantity=inventory.quantity_on_hand,
                triggered_at=now,
            )
        )
    await db.flush()


async def regenerate_reorder_suggestions_for_business(
    db: AsyncSession, business_id: uuid.UUID, *, log_event: str
) -> str | None:
    """Clear PENDING reorder suggestions and regenerate them against
    current stock levels. Shared by recompute_after_import() (after an
    import changes stock) and rollback_job() (after a rollback changes it
    back) — suggestions aren't migration_id-tagged, so "only what this
    import/rollback caused" isn't identifiable after the fact; a full
    regenerate is the only way to keep them consistent. Returns an error
    string (not raised) if regeneration fails, or None on success.

    Wrapped in its own SAVEPOINT (via run_isolated) so both the delete and
    the regenerate are isolated as one unit regardless of whether the
    caller has an outer SAVEPOINT of its own — rollback_job() doesn't.
    """
    _, error = await run_isolated(
        db,
        lambda: _clear_and_regenerate_reorder_suggestions(db, business_id),
        log_event=log_event,
        error_entry={},
    )
    return error["error"] if error else None


async def _clear_and_regenerate_reorder_suggestions(
    db: AsyncSession, business_id: uuid.UUID
) -> None:
    await db.execute(
        delete(ReorderSuggestion).where(
            ReorderSuggestion.business_id == business_id,
            ReorderSuggestion.status == ReorderStatus.PENDING,
        )
    )
    await generate_reorder_suggestions(db, business_id)


async def _recompute_ai_signals(
    db: AsyncSession, business_id: uuid.UUID, job_id: uuid.UUID
) -> list[dict]:
    """Regenerates reorder suggestions for the whole business, and price
    suggestions for the products this import actually created.
    """
    errors: list[dict] = []

    reorder_error = await regenerate_reorder_suggestions_for_business(
        db, business_id, log_event="recompute_reorder_suggestions_failed"
    )
    if reorder_error:
        errors.append({"step": "reorder_suggestions", "error": reorder_error})

    result = await db.execute(select(Product.id).where(Product.migration_id == job_id))
    product_ids = result.scalars().all()
    for product_id in product_ids:
        _, error = await run_isolated(
            db,
            lambda pid=product_id: compute_suggestion(db, pid),
            log_event="recompute_price_suggestion_failed",
            error_entry={"step": "price_suggestion", "product_id": str(product_id)},
        )
        if error:
            errors.append(error)
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
