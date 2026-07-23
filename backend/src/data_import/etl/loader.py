"""Load layer — FK-ordered inserts, migration_id tagging, rollback.

Scope note: Phase 0 wires up the entities the spec calls out as needing
dedup/ghost-record/variant logic (categories, products, variants, suppliers,
customers, locations, sales). Every other importable table already has its
`migration_id` column (added by this same migration) so future work can
extend `LOAD_ORDER` without another schema change.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, inspect, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.models import Customer
from src.data_import.etl.transformer import IdMap
from src.data_import.exceptions import (
    PurchaseOrderRollbackBlockedError,
    SellReturnRollbackBlockedError,
)
from src.expenses.models import Expense, ExpenseCategory
from src.inventory.models import InventoryBatch, InventoryLevel, StockMovement
from src.inventory.service import adjust_stock
from src.locations.models import BusinessLocation
from src.orders.models import (
    OrderLineItem,
    OrderPayment,
    OrderStatus,
    OrderStatusHistory,
    PurchaseOrder,
    PurchaseReturn,
)
from src.orders.schemas import OrderCreate, OrderLineItemCreate, StatusTransition
from src.orders.service import create_order, transition_status
from src.products.models import Product, ProductCategory, ProductVariant
from src.sales.models import Sale, SellReturn
from src.sales.schemas import SellReturnCreate
from src.sales.service import create_sell_return
from src.suppliers.models import Supplier

# Chained in order — the order state machine has no shortcut from PENDING
# straight to DELIVERED, so a historical (already-received) import replays
# every intermediate transition to reach it. Only the final DELIVERED step
# has side effects (adjust_stock + create_batch, inside transition_status).
_DELIVERY_CHAIN = [
    OrderStatus.IN_PRODUCTION,
    OrderStatus.SHIPPING,
    OrderStatus.CLEARED,
    OrderStatus.DELIVERED,
]

# FK dependency order — parents before children.
LOAD_ORDER: list[tuple[str, type]] = [
    ("product_categories", ProductCategory),
    ("products", Product),
    ("product_variants", ProductVariant),
    ("suppliers", Supplier),
    ("customers", Customer),
    ("business_locations", BusinessLocation),
    ("sales", Sale),
    ("expense_categories", ExpenseCategory),
    ("expenses", Expense),
]


def _zeroed_inventory_level(
    product_id: uuid.UUID,
    migration_id: uuid.UUID | None,
    variant_id: uuid.UUID | None = None,
) -> InventoryLevel:
    """A product-level (variant_id=None) InventoryLevel row starting at zero,
    or a variant-level one when variant_id is given.

    `migration_id=None` for a product this loader didn't create itself
    (a deduped/pre-existing product) — tagging it would make rollback
    incorrectly delete a pre-existing product's inventory row.

    low_stock_threshold is passed explicitly (matching
    src.inventory.service.initialize_inventory()'s own default) rather than
    left to InventoryLevel's column default, so the two construction sites
    can't silently drift apart if either one's default ever changes.
    """
    return InventoryLevel(
        product_id=product_id,
        variant_id=variant_id,
        quantity_on_hand=0,
        quantity_reserved=0,
        low_stock_threshold=10,
        migration_id=migration_id,
    )


async def load(
    db: AsyncSession,
    migration_id: uuid.UUID,
    transformed: dict[str, list[dict]],
    id_map: IdMap,
) -> dict[str, int]:
    """Insert every transformed row in FK order, tagging each with migration_id.

    Atomicity is provided by the caller's request-scoped session (see
    `core/database.get_db`), which rolls back entirely on any exception — the
    confirm endpoint is the only caller, so no other code path can trigger a
    partial load.
    """
    row_counts: dict[str, int] = {}
    for entity, model_cls in LOAD_ORDER:
        rows = transformed.get(entity, [])
        valid_columns = {c.name for c in inspect(model_cls).columns}
        objs = []
        source_ids = []
        for row in rows:
            row = dict(row)
            source_ids.append(row.pop("_source_id", None))
            kwargs = {k: v for k, v in row.items() if k in valid_columns}
            kwargs["migration_id"] = migration_id
            objs.append(model_cls(**kwargs))
        if objs:
            db.add_all(objs)
            # Ids are pre-assigned by the transformer (see Transformer._assign_id),
            # so one flush per entity is enough — no need to flush per row to
            # discover generated PKs.
            await db.flush()
            for obj, source_id in zip(objs, source_ids):
                if source_id:
                    id_map.register(entity, source_id, obj.id)
            if entity == "products":
                # adjust_stock() (called by transition_status() during
                # purchase-order delivery, see load_purchase_orders()) is an
                # UPDATE, not an upsert — it requires an existing
                # InventoryLevel row. The normal create_product() flow gets
                # one via initialize_inventory(); this bulk-insert path
                # bypasses that entirely, so every imported product needs
                # one created here, zeroed (no opening-stock data exists to
                # seed it with — see purchase_orders import for real stock).
                db.add_all(
                    [
                        _zeroed_inventory_level(product.id, migration_id)
                        for product in objs
                    ]
                )
                await db.flush()
        row_counts[entity] = len(objs)
    return row_counts


async def load_purchase_orders(
    db: AsyncSession,
    migration_id: uuid.UUID,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    po_groups: list[dict],
) -> int:
    """Create + fully deliver each grouped purchase order via the real
    `create_order()`/`transition_status()` service functions, so inventory
    levels and FIFO batches stay consistent with the exact same logic
    real-time POs go through — this loader never writes InventoryLevel/
    InventoryBatch/StockMovement rows itself. Returns the number of orders
    created (groups with no resolvable line items are skipped).
    """
    # adjust_stock() (called inside transition_status()'s DELIVERED branch)
    # is an UPDATE, not an upsert. Newly-imported products always get a row
    # (see load()), but a PO line item can also reference a *deduped*
    # (pre-existing) product — nothing guarantees those already have one
    # (e.g. seeded via a path that bypassed create_product()). Without this,
    # one product missing a row aborts the entire import batch, not just
    # its own order.
    referenced_product_ids = {
        li["product_id"] for group in po_groups for li in group["line_items"]
    }
    if referenced_product_ids:
        existing = await db.execute(
            select(InventoryLevel.product_id).where(
                InventoryLevel.product_id.in_(referenced_product_ids),
                InventoryLevel.variant_id.is_(None),
            )
        )
        missing_ids = referenced_product_ids - set(existing.scalars().all())
        if missing_ids:
            db.add_all([_zeroed_inventory_level(pid, None) for pid in missing_ids])
            await db.flush()

    order_ids: list[uuid.UUID] = []
    for group in po_groups:
        if not group["line_items"]:
            continue

        order_data = OrderCreate(
            supplier_name=group["supplier_name"],
            supplier_id=group.get("supplier_id"),
            # transform_purchase_orders() already backfills a "USD" default
            # for every group it returns — no fallback needed here.
            currency=group["currency"],
            fx_rate_at_creation=group.get("fx_rate"),
            is_purchase_order=False,
            line_items=[
                OrderLineItemCreate(
                    product_id=li["product_id"],
                    variant_id=li.get("variant_id"),
                    quantity=li["quantity"],
                    unit_cost=li["unit_cost"],
                )
                for li in group["line_items"]
            ],
        )
        order = await create_order(db, order_data, user_id, business_id)
        order.migration_id = migration_id
        # order_date/location_id/pos_id aren't in OrderCreate (only
        # order_date is accepted at all, and create_order() never actually
        # writes it — see the model directly instead of going through the
        # schema). pos_id (the source purchase's numeric POS id) lets
        # load_purchase_returns() resolve a return back to this order later.
        if group.get("order_date"):
            order.order_date = group["order_date"]
        if group.get("location_id"):
            order.location_id = group["location_id"]
        # A CSV-driven import has no separate numeric pos_id — only
        # source_id, its one and only identifier — so purchase_returns
        # resolution (against PurchaseOrder.pos_id) still works for CSV
        # uploads by falling back to that.
        order.pos_id = group.get("pos_id") or group["source_id"]
        for line_item in order.line_items:
            line_item.migration_id = migration_id
        await db.flush()

        for status in _DELIVERY_CHAIN:
            transition = StatusTransition(
                new_status=status.value,
                actual_delivery_date=group.get("order_date")
                if status == OrderStatus.DELIVERED
                else None,
            )
            order = await transition_status(db, order.id, transition, user_id)

        order_ids.append(order.id)

    # create_order()/transition_status() write InventoryBatch/StockMovement/
    # OrderStatusHistory rows, none of whose functions accept a migration_id
    # — tag them afterward by the orders/references just created. 3 bulk
    # UPDATEs total (not 3 per order, and no row materialization needed
    # since only one column changes) now that every order_id is known.
    if order_ids:
        await db.execute(
            update(InventoryBatch)
            .where(InventoryBatch.order_id.in_(order_ids))
            .values(migration_id=migration_id)
        )
        await db.execute(
            update(StockMovement)
            .where(
                StockMovement.reference_id.in_(order_ids),
                StockMovement.reference_type == "purchase_order",
            )
            .values(migration_id=migration_id)
        )
        await db.execute(
            update(OrderStatusHistory)
            .where(OrderStatusHistory.order_id.in_(order_ids))
            .values(migration_id=migration_id)
        )
        await db.flush()

    return len(order_ids)


async def load_stock_adjustments(
    db: AsyncSession,
    migration_id: uuid.UUID,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[dict],
) -> int:
    """Apply each adjustment via the real adjust_stock() service function
    (never writes StockMovement/InventoryLevel rows directly), so low-stock-
    alert side effects and audit records stay consistent with a live
    adjustment. Rollback needs no bespoke handling here — service.py's
    rollback_job() already reverses any StockMovement row tagged with this
    migration_id generically, regardless of which loader created it.
    """
    referenced = {(row["product_id"], row.get("variant_id")) for row in rows}
    if referenced:
        existing_result = await db.execute(
            select(InventoryLevel.product_id, InventoryLevel.variant_id).where(
                InventoryLevel.product_id.in_({pid for pid, _ in referenced})
            )
        )
        existing = set(existing_result.all())
        missing = referenced - existing
        if missing:
            db.add_all(
                [
                    _zeroed_inventory_level(pid, None, variant_id=vid)
                    for pid, vid in missing
                ]
            )
            await db.flush()

    count = 0
    for row in rows:
        await adjust_stock(
            db,
            product_id=row["product_id"],
            variant_id=row.get("variant_id"),
            quantity_change=row["quantity_change"],
            movement_type=row["movement_type"].value,
            reason=row.get("reason") or "Imported stock adjustment",
            user_id=user_id,
            business_id=business_id,
            migration_id=migration_id,
        )
        count += 1
    return count


async def load_sell_returns(
    db: AsyncSession,
    migration_id: uuid.UUID,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[dict],
) -> int:
    """Resolves each row's sale_source_id against Sale.pos_id (set by
    transform_sales()/load() for every sale this same import creates, or
    left over from an earlier import/live sale — the lookup is scoped to
    business_id, not migration_id, so a return can target either), then
    creates the return via the real create_sell_return() service function
    so it goes through the same validation (sale must be COMPLETED) real
    returns do.

    A single UltimatePOS sell can fan out into multiple Sale rows here (one
    per product line) sharing the same pos_id; a return only ever carries
    one aggregate total with no per-product breakdown even from the source
    system, so this attributes the whole return to whichever one of that
    sell's Sale rows is oldest — a documented simplification, not a guess
    at data that was never available in the first place.

    Rows with no resolvable sale are skipped, not errored — the parent sale
    may not have been part of this import (e.g. filtered out, or from a
    time range this job didn't cover).
    """
    count = 0
    for row in rows:
        result = await db.execute(
            select(Sale.id)
            .where(
                Sale.pos_id == row["sale_source_id"], Sale.business_id == business_id
            )
            .order_by(Sale.created_at)
            .limit(1)
        )
        sale_id = result.scalar_one_or_none()
        if sale_id is None:
            continue

        sell_return = await create_sell_return(
            db,
            sale_id,
            SellReturnCreate(
                return_date=row["return_date"],
                total_amount=row["total_amount"],
                amount_paid=row["amount_paid"],
                ref_no=row.get("ref_no"),
                notes=row.get("notes"),
            ),
            user_id,
            business_id,
        )
        sell_return.migration_id = migration_id
        count += 1
    if count:
        await db.flush()
    return count


async def load_purchase_returns(
    db: AsyncSession,
    migration_id: uuid.UUID,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[dict],
) -> int:
    """Constructs PurchaseReturn rows directly rather than going through the
    real create_purchase_return() service function. That function requires
    real per-product line items (to compute total_amount and reverse
    inventory via adjust_stock() per line), but no real purchase-return
    record with line-item detail exists on the one live UltimatePOS
    instance this was built against (zero real purchase returns at the
    time of writing) to confirm what that detail's shape looks like —
    importing only the return's header-level aggregate total (already
    available directly from the list endpoint) rather than guessing an
    unverified per-line parser.

    Known limitation: imported purchase returns do NOT reverse inventory —
    matches pos_migrate.py's own prior (also aggregate-only, also no
    adjust_stock call) behavior for this same entity. Resolves each row's
    purchase_source_id against PurchaseOrder.pos_id, scoped to business_id
    (not migration_id) for the same reason load_sell_returns() is.
    """
    count = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        result = await db.execute(
            select(PurchaseOrder.id)
            .where(
                PurchaseOrder.pos_id == row["purchase_source_id"],
                PurchaseOrder.business_id == business_id,
            )
            # purchase_orders are never deduped by source_id/pos_id across
            # jobs (validator.py sets unique_source_id=False for this
            # entity) — re-importing the same purchase data in a second job
            # creates a second PurchaseOrder row with the identical pos_id.
            # Without this, scalar_one_or_none() raises MultipleResultsFound
            # on that second match, matching load_sell_returns()'s own
            # guard against the analogous case for Sale.pos_id.
            .order_by(PurchaseOrder.created_at)
            .limit(1)
        )
        order_id = result.scalar_one_or_none()
        if order_id is None:
            continue

        purchase_return = PurchaseReturn(
            original_order_id=order_id,
            ref_no=row.get("ref_no") or None,
            return_date=row["return_date"],
            notes=row.get("notes"),
            total_amount=row["total_amount"],
            amount_paid=row["amount_paid"],
            created_by=user_id,
            business_id=business_id,
            migration_id=migration_id,
        )
        purchase_return.created_at = now
        purchase_return.updated_at = now
        db.add(purchase_return)
        count += 1
    if count:
        await db.flush()
    return count


async def rollback(db: AsyncSession, migration_id: uuid.UUID) -> dict[str, int]:
    """Delete every row tagged with this migration_id, in FK-safe order.

    Correctly undoes everything for products genuinely *created* by this
    import (the common case — a purchase-order import almost always
    accompanies importing the products it's for). It does NOT fully reverse
    the quantity effect of this import's purchase orders on a *deduped*
    (pre-existing) product: that product's InventoryLevel row isn't tagged
    with this migration_id (only newly-created rows are), so it isn't
    touched here — only the StockMovement audit trail for that change is
    deleted. Correctly reversing that case needs delta-based undo, not
    blanket deletion; that's the recompute service's job, not this one.

    Raises PurchaseOrderRollbackBlockedError, before deleting anything, if
    the business has recorded a real payment (via the normal orders
    endpoint, after the import) against one of these purchase orders, or a
    real purchase return (not one this same import created) against one of
    them — neither is part of the import and must not be silently
    destroyed or left dangling against a deleted order.
    """
    deleted_counts: dict[str, int] = {}

    blocked_ids = (
        (
            await db.execute(
                select(OrderPayment.order_id)
                .where(
                    OrderPayment.order_id.in_(
                        select(PurchaseOrder.id).where(
                            PurchaseOrder.migration_id == migration_id
                        )
                    )
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if blocked_ids:
        raise PurchaseOrderRollbackBlockedError(migration_id, list(blocked_ids))

    # Unlike OrderPayment (never created by this loader at all), a
    # PurchaseReturn CAN be one of this same import's own rows (see
    # load_purchase_returns()) — those are fine to delete below. Only a
    # return NOT tagged with this migration_id (created via the normal
    # orders endpoint, after the import) is the "real business data" case
    # that must block rollback instead of being silently destroyed.
    blocked_return_order_ids = (
        (
            await db.execute(
                select(PurchaseReturn.original_order_id)
                .where(
                    PurchaseReturn.original_order_id.in_(
                        select(PurchaseOrder.id).where(
                            PurchaseOrder.migration_id == migration_id
                        )
                    ),
                    or_(
                        PurchaseReturn.migration_id.is_(None),
                        PurchaseReturn.migration_id != migration_id,
                    ),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if blocked_return_order_ids:
        raise PurchaseOrderRollbackBlockedError(
            migration_id, list(blocked_return_order_ids)
        )

    # Same rationale as the PurchaseReturn check above, but for Sale: a
    # SellReturn NOT tagged with this migration_id is real business data
    # created after the import. Unlike PurchaseReturn, SellReturn.sale_id
    # has ON DELETE CASCADE — without this check, that real return would
    # be silently destroyed once the Sale itself is deleted below, instead
    # of causing any error at all.
    blocked_sale_ids = (
        (
            await db.execute(
                select(SellReturn.sale_id)
                .where(
                    SellReturn.sale_id.in_(
                        select(Sale.id).where(Sale.migration_id == migration_id)
                    ),
                    or_(
                        SellReturn.migration_id.is_(None),
                        SellReturn.migration_id != migration_id,
                    ),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if blocked_sale_ids:
        raise SellReturnRollbackBlockedError(migration_id, list(blocked_sale_ids))

    # StockMovement/InventoryLevel reference products.id and must go before
    # the reversed LOAD_ORDER loop deletes products, further down.
    result = await db.execute(
        delete(StockMovement).where(StockMovement.migration_id == migration_id)
    )
    deleted_counts["stock_movements"] = result.rowcount
    result = await db.execute(
        delete(InventoryLevel).where(InventoryLevel.migration_id == migration_id)
    )
    deleted_counts["inventory_levels"] = result.rowcount

    # SellReturn.sale_id has ON DELETE CASCADE, so this isn't strictly
    # required for FK safety — deleted explicitly anyway for an accurate
    # per-entity count and to match every other entity's explicit-delete
    # convention here, rather than relying on an implicit cascade.
    result = await db.execute(
        delete(SellReturn).where(SellReturn.migration_id == migration_id)
    )
    deleted_counts["sell_returns"] = result.rowcount

    # Purchase orders aren't in LOAD_ORDER (they're written via
    # load_purchase_orders(), not the generic bulk-insert loop) — delete
    # child-before-parent: line items, batches, and returns all reference
    # purchase_orders.id (returns via a FK with no ON DELETE behavior, so
    # this one IS required for FK safety, not just accurate counts) and
    # must go before the order itself, further down.
    result = await db.execute(
        delete(PurchaseReturn).where(PurchaseReturn.migration_id == migration_id)
    )
    deleted_counts["purchase_returns"] = result.rowcount
    result = await db.execute(
        delete(OrderLineItem).where(OrderLineItem.migration_id == migration_id)
    )
    deleted_counts["order_line_items"] = result.rowcount
    result = await db.execute(
        delete(InventoryBatch).where(InventoryBatch.migration_id == migration_id)
    )
    deleted_counts["inventory_batches"] = result.rowcount
    result = await db.execute(
        delete(OrderStatusHistory).where(
            OrderStatusHistory.migration_id == migration_id
        )
    )
    deleted_counts["order_status_history"] = result.rowcount
    result = await db.execute(
        delete(PurchaseOrder).where(PurchaseOrder.migration_id == migration_id)
    )
    deleted_counts["purchase_orders"] = result.rowcount

    for entity, model_cls in reversed(LOAD_ORDER):
        result = await db.execute(
            delete(model_cls).where(model_cls.migration_id == migration_id)
        )
        deleted_counts[entity] = result.rowcount

    return deleted_counts
