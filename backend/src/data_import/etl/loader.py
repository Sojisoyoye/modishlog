"""Load layer — FK-ordered inserts, migration_id tagging, rollback.

Scope note: Phase 0 wires up the entities the spec calls out as needing
dedup/ghost-record/variant logic (categories, products, variants, suppliers,
customers, locations, sales). Every other importable table already has its
`migration_id` column (added by this same migration) so future work can
extend `LOAD_ORDER` without another schema change.
"""

import uuid

from sqlalchemy import delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.models import Customer
from src.data_import.etl.transformer import IdMap
from src.inventory.models import InventoryBatch, InventoryLevel, StockMovement
from src.locations.models import BusinessLocation
from src.orders.models import (
    OrderLineItem,
    OrderStatus,
    OrderStatusHistory,
    PurchaseOrder,
)
from src.orders.schemas import OrderCreate, OrderLineItemCreate, StatusTransition
from src.orders.service import create_order, transition_status
from src.products.models import Product, ProductCategory, ProductVariant
from src.sales.models import Sale
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
]


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
                        InventoryLevel(
                            product_id=product.id,
                            quantity_on_hand=0,
                            quantity_reserved=0,
                            migration_id=migration_id,
                        )
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
    count = 0
    for group in po_groups:
        if not group["line_items"]:
            continue

        order_data = OrderCreate(
            supplier_name=group["supplier_name"],
            supplier_id=group.get("supplier_id"),
            currency=group.get("currency") or "USD",
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
        if group.get("order_date"):
            order.order_date = group["order_date"]
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

        # create_order()/transition_status() write InventoryBatch/
        # StockMovement/OrderStatusHistory rows, none of whose functions
        # accept a migration_id — tag them afterward by the order/reference
        # they were just created for.
        batches = await db.execute(
            select(InventoryBatch).where(InventoryBatch.order_id == order.id)
        )
        for batch in batches.scalars().all():
            batch.migration_id = migration_id
        movements = await db.execute(
            select(StockMovement).where(
                StockMovement.reference_id == order.id,
                StockMovement.reference_type == "purchase_order",
            )
        )
        for movement in movements.scalars().all():
            movement.migration_id = migration_id
        history_rows = await db.execute(
            select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
        )
        for history in history_rows.scalars().all():
            history.migration_id = migration_id
        await db.flush()

        count += 1
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
    """
    deleted_counts: dict[str, int] = {}

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

    # Purchase orders aren't in LOAD_ORDER (they're written via
    # load_purchase_orders(), not the generic bulk-insert loop) — delete
    # child-before-parent: line items and batches reference purchase_orders.id
    # and products.id, both of which must still exist at this point.
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
