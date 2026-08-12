"""Orders domain business logic."""

import csv
import io
import uuid
from collections.abc import Collection
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.query_helpers import reverse_ledger_consumption
from src.inventory.models import FifoConsumption, InventoryBatch, MovementType
from src.inventory.service import (
    adjust_stock,
    compute_landed_cost,
    create_batch,
    ensure_inventory_level_exists,
)
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    LineItemNotFoundError,
    MissingFxRateError,
    OrderAlreadyConsumedError,
    OrderLineItemError,
    OrderNotDeliveredError,
    OrderNotEditableError,
    OrderNotFoundError,
    OverpaymentError,
    PaymentAlreadyVoidedError,
    PaymentNotFoundError,
    PurchaseReturnNotFoundError,
)
from src.orders.models import (
    DiscountType,
    LotConsumption,
    OrderLineItem,
    OrderPayment,
    OrderPaymentStatus,
    OrderStatus,
    OrderStatusHistory,
    PaymentMethod,
    PaymentStatus,
    PayTermType,
    PurchaseOrder,
    PurchaseReturn,
)
from src.orders.schemas import (
    BulkImportResult,
    ImportRowError,
    LineItemCostCorrection,
    OrderCreate,
    OrderLineItemCreate,
    OrderUpdate,
    ParsedLineItem,
    ParseProductsResult,
    PaymentCreate,
    PaymentSummary,
    PaymentUpdate,
    PurchaseReturnCreate,
    StatusTransition,
)
from src.products.models import Product, ProductVariant
from src.sales.models import Sale

logger = structlog.get_logger()

# Multi-currency payments are converted through a raw NGN amount / fx_rate
# division (see _convert_to_order_currency), which can leave a sub-cent
# residue after summing several payments (e.g. $0.000005 short on a
# $19,180.26 order). Balances at or under this tolerance are treated as
# fully settled so "Partially Paid" doesn't linger on an order a user has
# actually paid off in full.
PAYMENT_BALANCE_TOLERANCE = Decimal("0.01")


def derive_payment_status(total_paid: Decimal, balance: Decimal) -> OrderPaymentStatus:
    """Single source of truth for UNPAID/PARTIAL/PAID, shared by every read
    and write path so they can't drift out of sync with each other."""
    if total_paid == 0:
        return OrderPaymentStatus.UNPAID
    if balance <= PAYMENT_BALANCE_TOLERANCE:
        return OrderPaymentStatus.PAID
    return OrderPaymentStatus.PARTIAL

# Valid status transitions
VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.ORDERED: [
        OrderStatus.PENDING,
        OrderStatus.CANCELLED,
    ],  # PO → received purchase
    OrderStatus.PENDING: [OrderStatus.IN_PRODUCTION, OrderStatus.CANCELLED],
    OrderStatus.IN_PRODUCTION: [OrderStatus.SHIPPING],
    OrderStatus.SHIPPING: [OrderStatus.CLEARED],
    OrderStatus.CLEARED: [OrderStatus.DELIVERED],
}

# Statuses that allow order editing
EDITABLE_STATUSES = {
    OrderStatus.ORDERED,
    OrderStatus.PENDING,
    OrderStatus.IN_PRODUCTION,
    OrderStatus.SHIPPING,
    OrderStatus.CLEARED,
    # DELIVERED is intentionally excluded: editing a delivered order retroactively
    # corrupts FIFO cost calculations and makes paid orders appear unpaid.
}


# ---------------------------------------------------------------------------
# Order number generation
# ---------------------------------------------------------------------------


async def _generate_order_number(db: AsyncSession) -> str:
    """Generate a unique order number in PO-YYYY-NNNNN format."""
    year = datetime.now(timezone.utc).year
    prefix = f"PO-{year}-"
    result = await db.execute(
        select(func.count())
        .select_from(PurchaseOrder)
        .where(PurchaseOrder.order_number.startswith(prefix))
    )
    count = result.scalar() or 0
    while True:
        count += 1
        order_number = f"{prefix}{count:05d}"
        existing = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.order_number == order_number)
        )
        if not existing.scalar_one_or_none():
            return order_number


# ---------------------------------------------------------------------------
# Purchase order CRUD
# ---------------------------------------------------------------------------


async def create_order(
    db: AsyncSession,
    data: OrderCreate,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PurchaseOrder:
    """Create a purchase order with line items."""
    # Validate all products exist
    product_ids = [item.product_id for item in data.line_items]
    for pid in product_ids:
        result = await db.execute(select(Product).where(Product.id == pid))
        if not result.scalar_one_or_none():
            raise OrderLineItemError(None, [pid])

    order_number = await _generate_order_number(db)

    # Calculate total (will be recalculated after variant cost overrides are applied)
    total_amount = Decimal("0")
    for item in data.line_items:
        total_amount += item.unit_cost * item.quantity

    # Calculate expected delivery date from lead times if provided
    expected_delivery = data.expected_delivery_date
    if expected_delivery is None and any(
        [data.production_days, data.shipping_days, data.clearing_days]
    ):
        total_days = (
            (data.production_days or 0)
            + (data.shipping_days or 0)
            + (data.clearing_days or 0)
        )
        expected_delivery = date.today() + timedelta(days=total_days)

    # Calculate tax amount
    tax_amount = Decimal("0")
    if data.tax_rate:
        tax_amount = (total_amount * data.tax_rate / 100).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

    initial_status = (
        OrderStatus.ORDERED if data.is_purchase_order else OrderStatus.PENDING
    )

    order = PurchaseOrder(
        order_number=order_number,
        supplier_id=data.supplier_id,
        supplier_name=data.supplier_name,
        supplier_contact=data.supplier_contact,
        status=initial_status,
        is_purchase_order=data.is_purchase_order,
        total_amount=total_amount,
        currency=data.currency,
        fx_rate_at_creation=data.fx_rate_at_creation,
        shipping_cost=data.shipping_cost,
        clearing_cost=data.clearing_cost,
        expected_delivery_date=expected_delivery,
        # Confirmed live during a real POS migration: this was never set at
        # all here, staying NULL for every normally-created order — only
        # the data_import loader patched it in by hand after the fact (see
        # etl/loader.py's load_purchase_orders()). Any date-scoped report
        # filtering on order_date (the correct field — see
        # reports/service.py's get_profit_loss_report()) would silently
        # exclude every real, organically-created purchase order. Falls
        # back to today when not supplied, matching expected_delivery's
        # own "no date given" convention above.
        order_date=data.order_date or date.today(),
        notes=data.notes,
        created_by=user_id,
        business_id=business_id,
        pay_term_number=data.pay_term_number,
        pay_term_type=data.pay_term_type,
        shipping_details=data.shipping_details,
        shipping_custom_field_1=data.shipping_custom_field_1,
        shipping_custom_field_2=data.shipping_custom_field_2,
        shipping_custom_field_3=data.shipping_custom_field_3,
        shipping_custom_field_4=data.shipping_custom_field_4,
        shipping_custom_field_5=data.shipping_custom_field_5,
        additional_expense_key_1=data.additional_expense_key_1,
        additional_expense_value_1=data.additional_expense_value_1,
        additional_expense_key_2=data.additional_expense_key_2,
        additional_expense_value_2=data.additional_expense_value_2,
        additional_expense_key_3=data.additional_expense_key_3,
        additional_expense_value_3=data.additional_expense_value_3,
        additional_expense_key_4=data.additional_expense_key_4,
        additional_expense_value_4=data.additional_expense_value_4,
        discount_type=data.discount_type,
        discount_amount=data.discount_amount,
        tax_rate=data.tax_rate,
        tax_amount=tax_amount,
        supplier_invoice_number=data.supplier_invoice_number,
        supplier_invoice_date=data.supplier_invoice_date,
    )
    db.add(order)
    await db.flush()

    # Create line items; accumulate actual total to account for variant cost overrides
    actual_total = Decimal("0")
    for item_data in data.line_items:
        # Resolve effective unit_cost, allowing variant cost_price_override to take
        # precedence when a variant is specified.
        effective_unit_cost = item_data.unit_cost
        if item_data.variant_id is not None:
            variant_result = await db.execute(
                select(ProductVariant).where(
                    ProductVariant.id == item_data.variant_id,
                    ProductVariant.product_id == item_data.product_id,
                    ProductVariant.is_active == True,  # noqa: E712
                )
            )
            order_variant = variant_result.scalar_one_or_none()
            if order_variant and order_variant.cost_price_override is not None:
                effective_unit_cost = order_variant.cost_price_override

        line_total = effective_unit_cost * item_data.quantity
        actual_total += line_total
        line_item = OrderLineItem(
            order_id=order.id,
            product_id=item_data.product_id,
            variant_id=item_data.variant_id,
            quantity=item_data.quantity,
            unit_cost=effective_unit_cost,
            unit_cost_ngn=item_data.unit_cost_ngn,
            sell_price_ngn=item_data.sell_price_ngn,
            line_total=line_total,
            notes=item_data.notes,
        )
        db.add(line_item)

    # Update order total if variant overrides changed the cost
    if actual_total != total_amount:
        order.total_amount = actual_total
        total_amount = actual_total

    # Initial status history
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=None,
        to_status=initial_status.value,
        transitioned_by=user_id,
        notes="Order created",
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()

    await logger.ainfo(
        "order_created",
        order_id=str(order.id),
        order_number=order_number,
        total=str(total_amount),
    )

    # Reload with eager-loaded relationships to avoid MissingGreenlet
    # when FastAPI serializes OrderRead with line_items
    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == order.id)
    )
    return result.scalar_one()


async def get_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PurchaseOrder:
    """Get a purchase order with related data loaded."""
    query = (
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.payments),
            selectinload(PurchaseOrder.status_history),
        )
        .where(PurchaseOrder.id == order_id)
    )
    if business_id is not None:
        query = query.where(PurchaseOrder.business_id == business_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise OrderNotFoundError(order_id)
    return order


async def get_order_status_counts(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Return a dict of order status → count for all orders."""
    query = select(PurchaseOrder.status, func.count(PurchaseOrder.id)).group_by(
        PurchaseOrder.status
    )
    if business_id is not None:
        query = query.where(PurchaseOrder.business_id == business_id)
    result = await db.execute(query)
    return {row[0].value: row[1] for row in result.all()}


async def list_orders(
    db: AsyncSession,
    *,
    business_id: uuid.UUID | None = None,
    status: str | None = None,
    supplier_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    overdue: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PurchaseOrder], int]:
    """List orders with filtering and pagination."""
    query = select(PurchaseOrder).options(selectinload(PurchaseOrder.line_items))
    count_query = select(func.count()).select_from(PurchaseOrder)

    if business_id is not None:
        query = query.where(PurchaseOrder.business_id == business_id)
        count_query = count_query.where(PurchaseOrder.business_id == business_id)

    if status is not None:
        query = query.where(PurchaseOrder.status == OrderStatus(status))
        count_query = count_query.where(PurchaseOrder.status == OrderStatus(status))
    if supplier_name is not None:
        pattern = f"%{supplier_name}%"
        query = query.where(PurchaseOrder.supplier_name.ilike(pattern))
        count_query = count_query.where(PurchaseOrder.supplier_name.ilike(pattern))
    if date_from is not None:
        query = query.where(
            PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time())
        )
        count_query = count_query.where(
            PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to is not None:
        query = query.where(
            PurchaseOrder.created_at <= datetime.combine(date_to, datetime.max.time())
        )
        count_query = count_query.where(
            PurchaseOrder.created_at <= datetime.combine(date_to, datetime.max.time())
        )
    if overdue:
        today = date.today()
        terminal = [OrderStatus.DELIVERED, OrderStatus.CANCELLED]
        query = query.where(
            PurchaseOrder.expected_delivery_date < today,
            PurchaseOrder.status.notin_(terminal),
        )
        count_query = count_query.where(
            PurchaseOrder.expected_delivery_date < today,
            PurchaseOrder.status.notin_(terminal),
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    # Sort by order_date (the real-world order date), falling back to created_at
    # for rows where it's still NULL — matches the frontend's own display fallback.
    # order_date is day-precision, so many rows can tie on it (common for
    # imported historical orders) — .id as a secondary key makes the sort
    # fully deterministic, or OFFSET/LIMIT pagination could return duplicate
    # or skipped rows across page loads depending on how Postgres breaks ties.
    query = (
        query.order_by(
            func.coalesce(PurchaseOrder.order_date, cast(PurchaseOrder.created_at, Date)).desc(),
            PurchaseOrder.id,
        )
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    data: OrderUpdate,
    user_id: uuid.UUID,
) -> PurchaseOrder:
    """Update an order. Only allowed in Pending/In Production status."""
    order = await get_order(db, order_id)

    if order.status not in EDITABLE_STATUSES:
        raise OrderNotEditableError(order_id, order.status.value)

    update_fields = data.model_dump(exclude_unset=True)
    line_items_data = update_fields.pop("line_items", None)

    for field, value in update_fields.items():
        setattr(order, field, value)

    # When fx_rate_at_creation is explicitly updated without resubmitting line
    # items, recompute USD unit_cost / line_total from unit_cost_ngn / new_rate.
    # This keeps total_amount accurate when the user corrects an FX rate on a
    # NGN-denominated order (e.g. post-POS-import correction).
    if "fx_rate_at_creation" in update_fields and line_items_data is None:
        new_rate = order.fx_rate_at_creation
        if new_rate and new_rate > 0:
            new_total = Decimal("0")
            any_recomputed = False
            for item in order.line_items:
                if item.unit_cost_ngn is not None:
                    item.unit_cost = (item.unit_cost_ngn / new_rate).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    item.line_total = (item.unit_cost * item.quantity).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    any_recomputed = True
                new_total += item.line_total
            if any_recomputed:
                order.total_amount = new_total

    # Replace line items if provided
    if line_items_data is not None:
        if not line_items_data:
            raise OrderLineItemError(order_id, [])
        # Validate products
        for item_data in line_items_data:
            result = await db.execute(
                select(Product).where(Product.id == item_data["product_id"])
            )
            if not result.scalar_one_or_none():
                raise OrderLineItemError(order_id, [item_data["product_id"]])

        # Preserve units_remaining for each product — it's set by the DELIVERED
        # transition and must survive a sell-price or notes edit on delivered lots.
        units_remaining_by_product: dict[uuid.UUID, Decimal | None] = {
            item.product_id: item.units_remaining
            for item in order.line_items
            if item.units_remaining is not None
        }

        # Delete existing line items
        for existing in order.line_items:
            await db.delete(existing)
        await db.flush()

        # Create new line items and recalculate total
        total = Decimal("0")
        for item_data in line_items_data:
            line_total = Decimal(str(item_data["unit_cost"])) * item_data["quantity"]
            total += line_total
            raw_ngn = item_data.get("unit_cost_ngn")
            raw_sell = item_data.get("sell_price_ngn")
            line_item = OrderLineItem(
                order_id=order.id,
                product_id=item_data["product_id"],
                variant_id=item_data.get("variant_id"),
                quantity=item_data["quantity"],
                unit_cost=Decimal(str(item_data["unit_cost"])),
                unit_cost_ngn=Decimal(str(raw_ngn)) if raw_ngn is not None else None,
                sell_price_ngn=Decimal(str(raw_sell)) if raw_sell is not None else None,
                line_total=line_total,
                notes=item_data.get("notes"),
                units_remaining=units_remaining_by_product.get(item_data["product_id"]),
            )
            db.add(line_item)
        order.total_amount = total

    await db.flush()
    await logger.ainfo("order_updated", order_id=str(order_id))
    return order


async def cancel_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PurchaseOrder:
    """Cancel an order. Only allowed if status is Pending."""
    order = await get_order(db, order_id)

    allowed = VALID_TRANSITIONS.get(order.status, [])
    if OrderStatus.CANCELLED not in allowed:
        raise InvalidStatusTransitionError(
            order_id,
            order.status.value,
            OrderStatus.CANCELLED.value,
            [s.value for s in allowed],
        )

    old_status = order.status.value
    order.status = OrderStatus.CANCELLED
    await db.flush()

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=OrderStatus.CANCELLED.value,
        transitioned_by=user_id,
        notes="Order cancelled",
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()

    await logger.ainfo("order_cancelled", order_id=str(order_id))
    return order


# ---------------------------------------------------------------------------
# Status workflow
# ---------------------------------------------------------------------------


async def transition_status(
    db: AsyncSession,
    order_id: uuid.UUID,
    transition: StatusTransition,
    user_id: uuid.UUID,
) -> PurchaseOrder:
    """Transition an order to a new status."""
    order = await get_order(db, order_id)

    new_status = OrderStatus(transition.new_status)
    allowed = VALID_TRANSITIONS.get(order.status, [])

    if new_status not in allowed:
        raise InvalidStatusTransitionError(
            order_id,
            order.status.value,
            new_status.value,
            [s.value for s in allowed],
        )

    old_status = order.status.value
    order.status = new_status

    # Handle delivery
    if new_status == OrderStatus.DELIVERED:
        order.actual_delivery_date = transition.actual_delivery_date or date.today()

        # Store FX rate at delivery if provided
        if transition.fx_rate_at_delivery is not None:
            order.fx_rate_at_delivery = transition.fx_rate_at_delivery

        # Restock inventory and create FIFO batches for each line item
        # Prefer delivery FX rate over creation rate for FIFO cost calculations
        fx_rate = (
            transition.fx_rate_at_delivery
            or order.fx_rate_at_creation
            or Decimal("1500")
        )
        total_logistics = (order.shipping_cost or Decimal("0")) + (
            order.clearing_cost or Decimal("0")
        )
        total_units = sum(li.quantity for li in order.line_items) or 1
        logistics_per_unit = (total_logistics / Decimal(str(total_units))).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        for item in order.line_items:
            item.units_remaining = Decimal(str(item.quantity))
            if item.variant_id is not None:
                # adjust_stock() is a strict lookup, never an upsert —
                # nothing creates a variant-scoped InventoryLevel row when
                # a variant is created (products/service.py's
                # create_variant() only inserts the ProductVariant row),
                # so the first delivery for a variant must backfill it
                # first or adjust_stock() raises ProductStockNotFoundError
                # for a perfectly valid variant. Non-variant line items
                # never need this: initialize_inventory() already created
                # the product's aggregate row at product-creation time.
                await ensure_inventory_level_exists(
                    db, item.product_id, item.variant_id
                )
            await adjust_stock(
                db,
                product_id=item.product_id,
                variant_id=item.variant_id,
                quantity_change=item.quantity,
                movement_type=MovementType.ORDER_RECEIVED.value,
                reason=f"Order {order.order_number} delivered",
                user_id=user_id,
                reference_id=order.id,
                reference_type="purchase_order",
            )
            await create_batch(
                db,
                product_id=item.product_id,
                order_id=order.id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                unit_cost_usd=item.unit_cost,
                fx_rate_at_arrival=fx_rate,
                logistics_allocation_per_unit=logistics_per_unit,
                received_at=order.actual_delivery_date,
            )

    await db.flush()

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=new_status.value,
        transitioned_by=user_id,
        notes=transition.notes,
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()

    await logger.ainfo(
        "order_status_transitioned",
        order_id=str(order_id),
        from_status=old_status,
        to_status=new_status.value,
    )
    return order


async def revert_delivered_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PurchaseOrder:
    """Undo a DELIVERED transition, moving the order back to CLEARED.

    DELIVERED is otherwise a terminal, locked status (EDITABLE_STATUSES
    excludes it, task 94) because the transition creates InventoryBatch
    rows that sales can draw FIFO cost from — reverting after that has
    happened would corrupt COGS history. This is narrowly scoped to the
    "marked delivered by mistake, nothing has touched it yet" case: it
    only proceeds if every batch this delivery created is still fully
    untouched, then reverses exactly what transition_status()'s DELIVERED
    handling did (inverse of orders/service.py's own DELIVERED block).
    """
    order = await get_order(db, order_id, business_id)
    if order.status != OrderStatus.DELIVERED:
        raise OrderNotDeliveredError(order_id, order.status.value, order.order_number)

    # Locked so a concurrent sale (fifo_deduct() locks the same
    # InventoryBatch rows via its own .with_for_update()) can't consume
    # from a batch in the window between this check and the delete below —
    # whichever transaction gets here first wins, the other blocks until
    # it commits, closing the race instead of leaving it to chance.
    batch_result = await db.execute(
        select(InventoryBatch)
        .where(InventoryBatch.order_id == order_id)
        .with_for_update()
    )
    batches = list(batch_result.scalars().all())

    for batch in batches:
        if batch.quantity_remaining != batch.quantity_received:
            raise OrderAlreadyConsumedError(order_id, order.order_number)

    if batches:
        consumption_result = await db.execute(
            select(FifoConsumption.id)
            .where(FifoConsumption.batch_id.in_([b.id for b in batches]))
            .limit(1)
        )
        if consumption_result.scalar_one_or_none() is not None:
            raise OrderAlreadyConsumedError(order_id, order.order_number)

    for batch in batches:
        await adjust_stock(
            db,
            product_id=batch.product_id,
            variant_id=batch.variant_id,
            quantity_change=-batch.quantity_received,
            movement_type=MovementType.MANUAL_REMOVE.value,
            reason=f"Reverted delivery of order {order.order_number}",
            user_id=user_id,
            reference_id=order.id,
            reference_type="purchase_order",
        )
        await db.delete(batch)

    for item in order.line_items:
        item.units_remaining = None

    old_status = order.status.value
    order.status = OrderStatus.CLEARED
    order.actual_delivery_date = None
    order.fx_rate_at_delivery = None

    await db.flush()

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=OrderStatus.CLEARED.value,
        transitioned_by=user_id,
        notes="Reverted: order was marked DELIVERED in error",
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()

    await logger.ainfo("order_delivery_reverted", order_id=str(order_id))
    return order


async def reverse_lot_consumption(
    db: AsyncSession, sale_ids: Collection[uuid.UUID]
) -> None:
    """Restore OrderLineItem.units_remaining for every lot the given sales
    consumed via sales/service.py's _deduct_lot_units(), then remove their
    consumption ledger rows.

    Used by void_sale() to undo lot-level consumption exactly, using the
    LotConsumption ledger _deduct_lot_units() wrote — mirrors
    inventory/service.py's reverse_fifo_consumption() (task 166) for this
    parallel units_remaining ledger (task 170).

    A lot that no longer exists is silently skipped — there's nothing to
    restore a deleted lot to.

    Delegates the actual algorithm to reverse_ledger_consumption()
    (src/core/query_helpers.py), shared with reverse_fifo_consumption().
    """
    await reverse_ledger_consumption(
        db,
        sale_ids,
        ledger_model=LotConsumption,
        ledger_sale_id_col=LotConsumption.sale_id,
        ledger_target_id_col=LotConsumption.order_line_item_id,
        ledger_quantity_col=LotConsumption.quantity_consumed,
        target_model=OrderLineItem,
        target_quantity_col=OrderLineItem.units_remaining,
        zero=Decimal("0"),
    )


async def get_status_history(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> list[OrderStatusHistory]:
    """Get status transition history for an order."""
    await get_order(db, order_id)  # ensure order exists
    result = await db.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order_id)
        .order_by(OrderStatusHistory.created_at)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Payment tracking
# ---------------------------------------------------------------------------


async def _sync_payment_status(db: AsyncSession, order: PurchaseOrder) -> None:
    """Recalculate and persist payment_status based on completed payments in the order currency."""
    result = await db.execute(
        select(func.coalesce(func.sum(OrderPayment.amount), Decimal("0")))
        .where(OrderPayment.order_id == order.id)
        .where(OrderPayment.status == PaymentStatus.COMPLETED)
        .where(OrderPayment.currency == order.currency)
    )
    total_paid = result.scalar() or Decimal("0")
    balance = order.total_amount - total_paid
    order.payment_status = derive_payment_status(total_paid, balance)


async def get_paid_totals_for_orders(
    db: AsyncSession, orders: list[PurchaseOrder]
) -> dict[uuid.UUID, Decimal]:
    """Return {order_id: total_paid} in each order's own currency. Used by list endpoint."""
    if not orders:
        return {}
    result = await db.execute(
        select(
            OrderPayment.order_id,
            OrderPayment.currency,
            func.coalesce(func.sum(OrderPayment.amount), Decimal("0")),
        )
        .where(OrderPayment.order_id.in_([o.id for o in orders]))
        .where(OrderPayment.status == PaymentStatus.COMPLETED)
        .group_by(OrderPayment.order_id, OrderPayment.currency)
    )
    currency_by_order = {o.id: o.currency for o in orders}
    totals: dict[uuid.UUID, Decimal] = {}
    for order_id, currency, amount in result.all():
        if currency == currency_by_order.get(order_id):
            totals[order_id] = totals.get(order_id, Decimal("0")) + amount
    return totals


def _convert_to_order_currency(
    amount: Decimal, payment_currency: str, order_currency: str, fx_rate: Decimal
) -> Decimal:
    """Convert a payment amount into the order's own currency.

    fx_rate is always expressed as NGN per unit of whichever side of the
    pair isn't NGN (matches how the FX Rates page and PurchaseOrder's own
    fx_rate_at_creation/fx_rate_at_delivery already quote rates) — so the
    arithmetic direction depends on which side is NGN, not on a single
    fixed multiply/divide.
    """
    if payment_currency == "NGN":
        # rate = NGN per order_currency unit — divide NGN by it to get
        # order_currency (e.g. 4,800,000 NGN / 1480 = $3,243.24)
        converted = amount / fx_rate
    elif order_currency == "NGN":
        # rate = NGN per payment_currency unit — multiply to get NGN
        converted = amount * fx_rate
    else:
        # Neither leg is NGN (e.g. EUR payment on a USD order) — treat the
        # rate as a direct order_currency-per-payment_currency multiplier.
        converted = amount * fx_rate
    return converted.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


async def record_payment(
    db: AsyncSession,
    order_id: uuid.UUID,
    data: PaymentCreate,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> OrderPayment:
    """Record a payment against an order.

    data.amount/currency/fx_rate are what the payer actually paid — amount
    gets converted into the order's own currency before being validated
    against the balance and stored (OrderPayment.amount is always in
    order.currency, matching what every balance/status query assumes).
    The original figures are kept on original_amount/original_currency for
    reference/audit, never used in calculations.
    """
    order = await get_order(db, order_id, business_id)

    original_amount: Decimal | None = None
    original_currency: str | None = None
    if data.currency == order.currency:
        converted_amount = data.amount
    else:
        if not data.fx_rate:
            raise MissingFxRateError(order_id, data.currency, order.currency)
        converted_amount = _convert_to_order_currency(
            data.amount, data.currency, order.currency, data.fx_rate
        )
        original_amount = data.amount
        original_currency = data.currency

    # Check for overpayment — always compares against the converted amount,
    # never the raw payer-currency figure.
    summary = await get_payment_summary(db, order_id, business_id)
    balance = summary.balance_remaining
    if converted_amount > balance:
        raise OverpaymentError(
            order_id, converted_amount, order.total_amount, summary.total_paid
        )

    payment = OrderPayment(
        order_id=order.id,
        amount=converted_amount,
        currency=order.currency,
        fx_rate=data.fx_rate,
        original_amount=original_amount,
        original_currency=original_currency,
        payment_date=data.payment_date,
        payment_method=PaymentMethod(data.payment_method),
        reference=data.reference,
        status=PaymentStatus.COMPLETED,
        notes=data.notes,
        recorded_by=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.flush()
    await _sync_payment_status(db, order)

    await logger.ainfo(
        "payment_recorded",
        order_id=str(order_id),
        amount=str(data.amount),
    )
    return payment


async def list_payments(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> list[OrderPayment]:
    """List all payments for an order."""
    await get_order(db, order_id)
    result = await db.execute(
        select(OrderPayment)
        .where(OrderPayment.order_id == order_id)
        .order_by(OrderPayment.payment_date)
    )
    return list(result.scalars().all())


async def get_payment_summary(
    db: AsyncSession,
    order_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PaymentSummary:
    """Get payment summary for an order."""
    order = await get_order(db, order_id, business_id)
    result = await db.execute(
        select(
            func.coalesce(func.sum(OrderPayment.amount), 0),
            func.count(OrderPayment.id),
        )
        .where(OrderPayment.order_id == order_id)
        .where(OrderPayment.status == PaymentStatus.COMPLETED)
        # record_payment() always converts+stores amount in order.currency,
        # but this filter guards against any legacy row that predates that
        # (or a future write path that doesn't convert) — same filter
        # _sync_payment_status() already applies.
        .where(OrderPayment.currency == order.currency)
    )
    row = result.one()
    total_paid = row[0]
    payment_count = row[1]
    balance = order.total_amount - total_paid

    return PaymentSummary(
        total_due=order.total_amount,
        total_paid=total_paid,
        balance_remaining=balance,
        payment_count=payment_count,
        is_fully_paid=balance <= PAYMENT_BALANCE_TOLERANCE,
    )


async def void_payment(
    db: AsyncSession,
    order_id: uuid.UUID,
    payment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrderPayment:
    """Void a payment record."""
    order = await get_order(db, order_id)
    result = await db.execute(
        select(OrderPayment)
        .where(OrderPayment.id == payment_id)
        .where(OrderPayment.order_id == order_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise PaymentNotFoundError(payment_id, order_id)

    payment.status = PaymentStatus.VOIDED
    await db.flush()
    await _sync_payment_status(db, order)

    await logger.ainfo(
        "payment_voided",
        order_id=str(order_id),
        payment_id=str(payment_id),
    )
    return payment


async def update_payment(
    db: AsyncSession,
    order_id: uuid.UUID,
    payment_id: uuid.UUID,
    data: PaymentUpdate,
    business_id: uuid.UUID | None = None,
) -> OrderPayment:
    """Edit an existing (non-voided) payment — e.g. correcting its fx_rate
    after the fact, such as when the exchange rate used at record time was
    wrong or an updated rate is needed to fully cover the order's balance.

    Same conversion semantics as record_payment(): amount/currency/fx_rate
    describe what was actually paid, converted into the order's own
    currency for storage exactly like on create. Any field omitted from
    `data` keeps its current value — re-deriving the "raw paid" figure
    from original_amount/original_currency (not the already-converted
    amount/currency) when those weren't part of this edit either.

    The overpayment check compares against the balance as if this
    payment's *current* contribution didn't exist yet (balance_remaining +
    payment.amount), not today's balance — otherwise a payment could never
    be edited without first voiding it, since its own existing amount is
    already counted against the balance.
    """
    order = await get_order(db, order_id, business_id)
    result = await db.execute(
        select(OrderPayment)
        .where(OrderPayment.id == payment_id)
        .where(OrderPayment.order_id == order_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise PaymentNotFoundError(payment_id, order_id)
    if payment.status == PaymentStatus.VOIDED:
        raise PaymentAlreadyVoidedError(payment_id, order_id)

    raw_amount = (
        data.amount
        if data.amount is not None
        else (payment.original_amount if payment.original_amount is not None else payment.amount)
    )
    raw_currency = (
        data.currency
        if data.currency is not None
        else (payment.original_currency if payment.original_currency is not None else payment.currency)
    )
    raw_fx_rate = data.fx_rate if data.fx_rate is not None else payment.fx_rate

    if raw_currency == order.currency:
        converted_amount = raw_amount
        original_amount = None
        original_currency = None
    else:
        if not raw_fx_rate:
            raise MissingFxRateError(order_id, raw_currency, order.currency)
        converted_amount = _convert_to_order_currency(
            raw_amount, raw_currency, order.currency, raw_fx_rate
        )
        original_amount = raw_amount
        original_currency = raw_currency

    summary = await get_payment_summary(db, order_id, business_id)
    balance_excluding_this_payment = summary.balance_remaining + payment.amount
    if converted_amount > balance_excluding_this_payment:
        raise OverpaymentError(
            order_id, converted_amount, order.total_amount, summary.total_paid
        )

    payment.amount = converted_amount
    payment.currency = order.currency
    payment.fx_rate = raw_fx_rate
    payment.original_amount = original_amount
    payment.original_currency = original_currency
    if data.payment_date is not None:
        payment.payment_date = data.payment_date
    if data.payment_method is not None:
        payment.payment_method = PaymentMethod(data.payment_method)
    if data.reference is not None:
        payment.reference = data.reference
    if data.notes is not None:
        payment.notes = data.notes

    await db.flush()
    await _sync_payment_status(db, order)

    await logger.ainfo(
        "payment_updated",
        order_id=str(order_id),
        payment_id=str(payment_id),
    )
    return payment


# ---------------------------------------------------------------------------
# Delivered-order cost correction
# ---------------------------------------------------------------------------


async def correct_delivered_order_costs(
    db: AsyncSession,
    order_id: uuid.UUID,
    corrections: list[LineItemCostCorrection],
    business_id: uuid.UUID | None = None,
    fx_rate_at_creation: Decimal | None = None,
    fx_rate_at_delivery: Decimal | None = None,
    shipping_cost: Decimal | None = None,
    clearing_cost: Decimal | None = None,
    shipping_details: str | None = None,
) -> PurchaseOrder:
    """Correct costs on an already-DELIVERED order, cascading the
    correction through InventoryBatch landed costs and every
    already-recorded sale's FIFO COGS/gross-profit.

    update_order() deliberately refuses any edit once an order is DELIVERED
    (see EDITABLE_STATUSES) — that lock is intentional (task 94) and stays
    in place for quantities/supplier/dates. This is a narrow, separate
    operation solely for correcting a delivered order's costs against
    reality (e.g. the real supplier invoice), since neither update_order()
    nor anything else touches InventoryBatch or Sale.fifo_cogs after
    delivery — those are only ever written once, at the DELIVERED
    transition.

    Two independent correction paths, both landing in the same cascade:
    - `corrections`: per-line-item unit_cost, cascading to that
      (order, product, variant)'s own batches only.
    - `fx_rate_at_creation`/`shipping_cost`/`clearing_cost`: order-wide
      fields transition_status()'s DELIVERED handling baked into *every*
      batch's fx_rate_at_arrival/logistics_allocation_per_unit (see that
      function's fx_rate fallback and total_logistics/total_units
      formula, reproduced identically here) — so correcting them cascades
      to every batch on the order, not just the corrected line items'.

    Either way, every touched batch's fifo_cogs impact is re-summed from
    scratch (not a delta) for every sale that consumed from it, across
    that sale's FULL consumption set, since some sales draw from more
    than one order's batches for the same product.
    """
    order = await get_order(db, order_id, business_id)
    if order.status != OrderStatus.DELIVERED:
        raise OrderNotDeliveredError(order_id, order.status.value, order.order_number)

    if shipping_details is not None:
        order.shipping_details = shipping_details

    items_by_id = {item.id: item for item in order.line_items}

    touched_batch_ids: set[uuid.UUID] = set()
    for correction in corrections:
        item = items_by_id.get(correction.line_item_id)
        if item is None:
            raise LineItemNotFoundError(order_id, correction.line_item_id)

        item.unit_cost = correction.new_unit_cost
        item.line_total = (correction.new_unit_cost * item.quantity).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        batch_result = await db.execute(
            select(InventoryBatch).where(
                InventoryBatch.order_id == order_id,
                InventoryBatch.product_id == item.product_id,
                InventoryBatch.variant_id == item.variant_id,
            )
        )
        for batch in batch_result.scalars().all():
            batch.unit_cost_usd = correction.new_unit_cost
            batch.landed_cost_per_unit = compute_landed_cost(
                correction.new_unit_cost,
                batch.fx_rate_at_arrival,
                batch.logistics_allocation_per_unit,
            )
            touched_batch_ids.add(batch.id)

    order.total_amount = sum(
        (item.line_total for item in order.line_items), Decimal("0")
    )

    if (
        fx_rate_at_creation is not None
        or fx_rate_at_delivery is not None
        or shipping_cost is not None
        or clearing_cost is not None
    ):
        if fx_rate_at_creation is not None:
            order.fx_rate_at_creation = fx_rate_at_creation
        if fx_rate_at_delivery is not None:
            order.fx_rate_at_delivery = fx_rate_at_delivery
        if shipping_cost is not None:
            order.shipping_cost = shipping_cost
        if clearing_cost is not None:
            order.clearing_cost = clearing_cost

        # Same fallback/formula as transition_status()'s DELIVERED handling.
        new_fx_rate = (
            order.fx_rate_at_delivery
            or order.fx_rate_at_creation
            or Decimal("1500")
        )
        total_logistics = (order.shipping_cost or Decimal("0")) + (
            order.clearing_cost or Decimal("0")
        )
        total_units = sum(li.quantity for li in order.line_items) or 1
        new_logistics_per_unit = (
            total_logistics / Decimal(str(total_units))
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

        order_batches_result = await db.execute(
            select(InventoryBatch).where(InventoryBatch.order_id == order_id)
        )
        for batch in order_batches_result.scalars().all():
            batch.fx_rate_at_arrival = new_fx_rate
            batch.logistics_allocation_per_unit = new_logistics_per_unit
            batch.landed_cost_per_unit = compute_landed_cost(
                batch.unit_cost_usd, new_fx_rate, new_logistics_per_unit
            )
            touched_batch_ids.add(batch.id)

    await db.flush()  # so the resum below reads the corrected batch costs

    if touched_batch_ids:
        sale_id_result = await db.execute(
            select(FifoConsumption.sale_id)
            .where(FifoConsumption.batch_id.in_(touched_batch_ids))
            .distinct()
        )
        for (sale_id,) in sale_id_result.all():
            consumption_result = await db.execute(
                select(FifoConsumption, InventoryBatch.landed_cost_per_unit)
                .join(InventoryBatch, InventoryBatch.id == FifoConsumption.batch_id)
                .where(FifoConsumption.sale_id == sale_id)
            )
            rows = consumption_result.all()
            new_cogs = sum(
                (fc.quantity_consumed * landed for fc, landed in rows), Decimal("0")
            ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

            sale_result = await db.execute(select(Sale).where(Sale.id == sale_id))
            sale = sale_result.scalar_one()
            sale.fifo_cogs = new_cogs
            sale.fifo_gross_profit = sale.total_amount - new_cogs

    await db.flush()

    await logger.ainfo(
        "order_costs_corrected",
        order_id=str(order_id),
        line_items_corrected=len(corrections),
        batches_touched=len(touched_batch_ids),
    )
    return order


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


async def get_overdue_orders(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> list[PurchaseOrder]:
    """Get orders past their expected delivery date."""
    today = date.today()
    terminal = [OrderStatus.DELIVERED, OrderStatus.CANCELLED]
    query = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(
            PurchaseOrder.expected_delivery_date < today,
            PurchaseOrder.status.notin_(terminal),
        )
        .order_by(PurchaseOrder.expected_delivery_date)
    )
    if business_id is not None:
        query = query.where(PurchaseOrder.business_id == business_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_orders_summary(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Get summary statistics for all orders."""
    # Total count and value
    base_filter = (
        [PurchaseOrder.business_id == business_id] if business_id is not None else []
    )
    result = await db.execute(
        select(
            func.count(PurchaseOrder.id),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0),
        ).where(*base_filter)
    )
    row = result.one()
    total_orders = row[0]
    total_value = row[1]

    # Count by status
    status_query = select(PurchaseOrder.status, func.count(PurchaseOrder.id)).group_by(
        PurchaseOrder.status
    )
    if business_id is not None:
        status_query = status_query.where(PurchaseOrder.business_id == business_id)
    status_result = await db.execute(status_query)
    by_status = {row[0].value: row[1] for row in status_result.all()}

    return {
        "total_orders": total_orders,
        "total_value": total_value,
        "by_status": by_status,
    }


# ---------------------------------------------------------------------------
# Logistics Efficiency
# ---------------------------------------------------------------------------

LOGISTICS_AMBER_THRESHOLD = Decimal("15")
LOGISTICS_RED_THRESHOLD = Decimal("20")


def calculate_logistics_pct(
    shipping_cost: Decimal, clearing_cost: Decimal, total_cogs: Decimal
) -> Decimal:
    """Compute logistics % = (shipping + clearing) / total_cogs × 100."""
    if total_cogs <= 0:
        return Decimal("0")
    return ((shipping_cost + clearing_cost) / total_cogs * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


async def get_logistics_efficiency(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Calculate per-order logistics % and rolling 90-day average."""
    ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).date()

    query = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(
            PurchaseOrder.status != OrderStatus.CANCELLED,
            PurchaseOrder.created_at
            >= datetime.combine(ninety_days_ago, datetime.min.time()).replace(
                tzinfo=timezone.utc
            ),
        )
        .order_by(PurchaseOrder.created_at.desc())
    )
    if business_id is not None:
        query = query.where(PurchaseOrder.business_id == business_id)
    result = await db.execute(query)
    orders = list(result.scalars().all())

    per_order = []
    total_logistics = Decimal("0")
    total_cogs_sum = Decimal("0")

    for order in orders:
        total_cogs = order.total_amount
        logistics_ngn = order.shipping_cost + order.clearing_cost
        lp = calculate_logistics_pct(
            order.shipping_cost, order.clearing_cost, total_cogs
        )
        per_order.append(
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "logistics_pct": lp,
                "logistics_ngn": logistics_ngn,
                "total_cogs_ngn": total_cogs,
            }
        )
        total_logistics += logistics_ngn
        total_cogs_sum += total_cogs

    rolling_avg = calculate_logistics_pct(total_logistics, Decimal("0"), total_cogs_sum)

    if rolling_avg > LOGISTICS_RED_THRESHOLD:
        status = "red"
    elif rolling_avg > LOGISTICS_AMBER_THRESHOLD:
        status = "amber"
    else:
        status = "healthy"

    return {
        "per_order": per_order,
        "rolling_90d_avg_pct": rolling_avg,
        "amber_threshold_pct": LOGISTICS_AMBER_THRESHOLD,
        "red_threshold_pct": LOGISTICS_RED_THRESHOLD,
        "status": status,
    }


async def check_logistics_alerts(db: AsyncSession) -> bool:
    """Check logistics thresholds and create recommendations if breached."""
    data = await get_logistics_efficiency(db)
    avg = data["rolling_90d_avg_pct"]

    if avg <= LOGISTICS_AMBER_THRESHOLD:
        return False

    # Lazy import to avoid circular dependency
    from src.ai_engine.models import (
        AIRecommendation,
        ActionType,
        RecommendationCategory,
        RecommendationPriority,
        RecommendationStatus,
    )

    # Dedup: skip if pending logistics alert exists
    existing = await db.execute(
        select(func.count())
        .select_from(AIRecommendation)
        .where(
            AIRecommendation.category == RecommendationCategory.INVENTORY,
            AIRecommendation.status == RecommendationStatus.PENDING,
            AIRecommendation.action_payload["type"].as_string() == "logistics_alert",
        )
    )
    if (existing.scalar() or 0) > 0:
        return False

    priority = (
        RecommendationPriority.HIGH
        if avg > LOGISTICS_RED_THRESHOLD
        else RecommendationPriority.MEDIUM
    )
    now = datetime.now(timezone.utc)
    rec = AIRecommendation(
        category=RecommendationCategory.INVENTORY,
        action_type=ActionType.REORDER,
        title=f"Logistics costs at {avg}% of COGS",
        description=(
            f"Rolling 90-day logistics (shipping + clearing) is {avg}% of COGS, "
            f"above the {'red' if avg > LOGISTICS_RED_THRESHOLD else 'amber'} "
            f"threshold. Consider consolidating shipments or negotiating rates."
        ),
        priority=priority,
        confidence=Decimal("0.90"),
        expected_impact={"logistics_pct": str(avg)},
        action_payload={"type": "logistics_alert", "avg_pct": str(avg)},
        status=RecommendationStatus.PENDING,
        created_at=now,
        expires_at=now + timedelta(days=14),
    )
    db.add(rec)
    await db.flush()

    await logger.ainfo(
        "logistics_alert_triggered",
        avg_pct=str(avg),
        priority=priority.value,
    )
    return True


# ---------------------------------------------------------------------------
# Convert PO to received purchase
# ---------------------------------------------------------------------------


async def convert_po_to_purchase(
    db: AsyncSession,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PurchaseOrder:
    """Convert a Purchase Order (ORDERED status) to a received purchase.

    Sets is_purchase_order=False and status=PENDING so the order enters
    the normal delivery flow (PENDING → IN_PRODUCTION → ... → DELIVERED),
    at which point inventory is updated.
    """
    query = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == order_id)
    )
    if business_id is not None:
        query = query.where(PurchaseOrder.business_id == business_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise OrderNotFoundError(order_id)

    if not order.is_purchase_order or order.status != OrderStatus.ORDERED:
        raise InvalidStatusTransitionError(
            order_id,
            order.status.value,
            OrderStatus.PENDING.value,
            [OrderStatus.ORDERED.value],
        )

    order.is_purchase_order = False
    order.status = OrderStatus.PENDING
    await db.flush()

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=OrderStatus.ORDERED.value,
        to_status=OrderStatus.PENDING.value,
        transitioned_by=user_id,
        notes="PO converted to received purchase",
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)

    await logger.ainfo(
        "po_converted_to_purchase",
        order_id=str(order_id),
        order_number=order.order_number,
    )
    return order


# ---------------------------------------------------------------------------
# Purchase returns
# ---------------------------------------------------------------------------


async def create_purchase_return(
    db: AsyncSession,
    data: PurchaseReturnCreate,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PurchaseReturn:
    """Record a return of goods against a purchase order."""
    order = await get_order(db, data.original_order_id, business_id)

    # Build a map of (product_id, variant_id) -> unit_cost from the
    # original order — keyed by product_id alone, an order with separate
    # line items for two variants of the same product would collapse to
    # whichever line item's unit_cost happened to be inserted into the
    # dict last.
    cost_map: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal] = {
        (item.product_id, item.variant_id): item.unit_cost for item in order.line_items
    }

    total_amount = Decimal("0")
    for line in data.line_items:
        pid = line.product_id
        key = (pid, line.variant_id)
        if key not in cost_map:
            # Silently falling back to Decimal("0") cost here would
            # understate total_amount, and proceeding to adjust_stock()
            # with the caller's (possibly wrong) variant_id would decrement
            # whichever InventoryLevel row that resolves to — not
            # necessarily the row this order's delivery actually credited.
            raise OrderLineItemError(order.id, [pid])
        unit_cost = cost_map[key]
        total_amount += unit_cost * line.quantity

        # Reverse inventory: deduct returned stock. Scoped to the same
        # variant transition_status() delivered it onto — the aggregate
        # (variant_id=NULL) row is a different row entirely once a PO line
        # item is variant-specific.
        await adjust_stock(
            db,
            product_id=pid,
            variant_id=line.variant_id,
            quantity_change=-line.quantity,
            movement_type=MovementType.MANUAL_REMOVE.value,
            reason=f"Purchase return for order {order.order_number}",
            user_id=user_id,
            reference_id=order.id,
            reference_type="purchase_return",
        )

    year = datetime.now(timezone.utc).year
    ref_no = f"RET-{year}-{str(uuid.uuid4())[:8].upper()}"

    purchase_return = PurchaseReturn(
        original_order_id=data.original_order_id,
        ref_no=ref_no,
        return_date=date.today(),
        notes=data.notes,
        total_amount=total_amount.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        created_by=user_id,
        business_id=business_id,
    )
    db.add(purchase_return)
    await db.flush()

    await logger.ainfo(
        "purchase_return_created",
        return_id=str(purchase_return.id),
        order_id=str(data.original_order_id),
        total=str(total_amount),
    )
    return purchase_return


# ---------------------------------------------------------------------------
# Bulk order import
# ---------------------------------------------------------------------------

_REQUIRED_IMPORT_COLS = {
    "supplier_name",
    "currency",
    "line_item_sku",
    "line_item_quantity",
    "line_item_unit_cost",
}


def build_import_template_csv() -> str:
    """Return a CSV template demonstrating multi-product order grouping.

    Order-level fields (shipping_cost, discount, tax, etc.) go on the FIRST row
    of each order only.  Continuation rows (blank supplier_name) carry only the
    three line-item columns; all other cells must be left empty.
    """
    ordered_cols = [
        # ── Line-item columns (fill on EVERY row) ──────────────────────────
        "supplier_name",  # Leave blank on rows 2+ of the same order
        "currency",  # Leave blank on continuation rows
        "line_item_sku",
        "line_item_quantity",
        "line_item_unit_cost",
        # ── Order-level columns (fill on FIRST row of each order ONLY) ──────
        "supplier_contact",
        "is_purchase_order",  # TRUE or FALSE
        "pay_term_number",
        "pay_term_type",  # days or months
        "shipping_cost",  # Shared across ALL products in this order
        "clearing_cost",  # Shared across ALL products in this order
        "notes",
        "discount_type",  # percentage or fixed
        "discount_amount",
        "tax_rate",
        "supplier_invoice_number",
        "supplier_invoice_date",  # YYYY-MM-DD
    ]

    _blank = {col: "" for col in ordered_cols}

    # ── Example: Order 1 — Acme Imports with 3 products ──────────────────
    order1_row1 = {
        **_blank,
        "supplier_name": "Acme Imports Ltd",
        "currency": "USD",
        "line_item_sku": "SKU-001",
        "line_item_quantity": "10",
        "line_item_unit_cost": "25.00",
        # Order-level fields — set ONCE here, shared across all 3 products
        "supplier_contact": "Jane Doe",
        "is_purchase_order": "FALSE",
        "pay_term_number": "30",
        "pay_term_type": "days",
        "shipping_cost": "500.00",
        "clearing_cost": "200.00",
        "notes": "Urgent shipment",
        "discount_type": "percentage",
        "discount_amount": "5",
        "tax_rate": "7.5",
        "supplier_invoice_number": "INV-2026-001",
        "supplier_invoice_date": "2026-06-15",
    }
    # Continuation rows — supplier_name is blank; only line-item cols filled
    order1_row2 = {
        **_blank,
        "line_item_sku": "SKU-002",
        "line_item_quantity": "5",
        "line_item_unit_cost": "40.00",
    }
    order1_row3 = {
        **_blank,
        "line_item_sku": "SKU-003",
        "line_item_quantity": "3",
        "line_item_unit_cost": "60.00",
    }

    # ── Example: Order 2 — Beta Corp with 2 products ──────────────────────
    order2_row1 = {
        **_blank,
        "supplier_name": "Beta Corp",
        "currency": "NGN",
        "line_item_sku": "SKU-010",
        "line_item_quantity": "20",
        "line_item_unit_cost": "1500.00",
        "supplier_contact": "John Smith",
        "is_purchase_order": "TRUE",
        "shipping_cost": "8000.00",
        "supplier_invoice_number": "INV-2026-002",
        "supplier_invoice_date": "2026-06-20",
    }
    order2_row2 = {
        **_blank,
        "line_item_sku": "SKU-011",
        "line_item_quantity": "8",
        "line_item_unit_cost": "2000.00",
    }

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=ordered_cols)
    writer.writeheader()
    writer.writerows([order1_row1, order1_row2, order1_row3, order2_row1, order2_row2])
    return buf.getvalue()


def _opt_decimal(val: str) -> Decimal | None:
    v = val.strip() if val else ""
    if not v:
        return None
    try:
        return Decimal(v)
    except Exception:
        return None


def _opt_int(val: str) -> int | None:
    v = val.strip() if val else ""
    if not v:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _opt_str(val: str) -> str | None:
    v = val.strip() if val else ""
    return v or None


def _opt_date(val: str) -> date | None:
    v = val.strip() if val else ""
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _parse_csv_bytes(file_bytes: bytes) -> list[dict[str, str]]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _parse_xlsx_bytes(file_bytes: bytes) -> list[dict[str, str]]:
    import openpyxl  # local import — optional dependency already in requirements

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(c).strip() if c is not None else "" for c in rows[0]]
    result = []
    for raw_row in rows[1:]:
        row_dict = {
            headers[i]: (str(v).strip() if v is not None else "")
            for i, v in enumerate(raw_row)
            if i < len(headers)
        }
        result.append(row_dict)
    return result


async def import_orders_from_file(
    db: AsyncSession,
    file_bytes: bytes,
    filename: str,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> BulkImportResult:
    """Parse CSV or XLSX bytes and create multiple purchase orders.

    Groups consecutive rows by supplier_name (empty = continue previous order).
    Never partially commits — if any error exists no orders are created.
    Invalid values for optional numeric/date fields are silently treated as absent.
    """

    errors: list[ImportRowError] = []

    if not file_bytes:
        return BulkImportResult(
            created=0,
            orders=[],
            errors=[ImportRowError(row=0, message="File is empty")],
        )

    # Parse file
    lower = filename.lower()
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        raw_rows = _parse_xlsx_bytes(file_bytes)
    else:
        raw_rows = _parse_csv_bytes(file_bytes)

    if not raw_rows:
        return BulkImportResult(
            created=0,
            orders=[],
            errors=[ImportRowError(row=0, message="File has no data rows")],
        )

    # Validate required columns present
    headers = set(raw_rows[0].keys())
    missing = _REQUIRED_IMPORT_COLS - headers
    if missing:
        return BulkImportResult(
            created=0,
            orders=[],
            errors=[
                ImportRowError(
                    row=0,
                    message=f"Missing required columns: {', '.join(sorted(missing))}",
                )
            ],
        )

    # Group rows into orders by supplier_name
    groups: list[list[tuple[int, dict]]] = []
    for i, row in enumerate(raw_rows, start=2):  # row 1 = header
        supplier = row.get("supplier_name", "").strip()
        if supplier:
            groups.append([(i, row)])
        elif groups:
            groups[-1].append((i, row))
        else:
            errors.append(
                ImportRowError(
                    row=i,
                    message="Row has no supplier_name and no preceding order to attach to",
                )
            )

    if not groups and not errors:
        return BulkImportResult(
            created=0,
            orders=[],
            errors=[ImportRowError(row=0, message="No order rows found")],
        )

    # Validate and resolve each group
    order_creates = []
    for group in groups:
        first_row_num, first_row = group[0]
        header_row = first_row

        line_items = []
        for row_num, row in group:
            sku = row.get("line_item_sku", "").strip()
            if not sku:
                errors.append(
                    ImportRowError(row=row_num, message="line_item_sku is required")
                )
                continue

            # Resolve SKU → product_id
            result = await db.execute(select(Product).where(Product.sku == sku))
            product = result.scalar_one_or_none()
            if product is None:
                errors.append(
                    ImportRowError(
                        row=row_num, message=f"Product SKU '{sku}' not found"
                    )
                )
                continue

            qty_str = row.get("line_item_quantity", "").strip()
            cost_str = row.get("line_item_unit_cost", "").strip()
            try:
                qty = int(qty_str)
                if qty <= 0:
                    raise ValueError("must be positive")
            except (ValueError, TypeError):
                errors.append(
                    ImportRowError(
                        row=row_num,
                        message=f"line_item_quantity '{qty_str}' must be a positive integer",
                    )
                )
                continue
            try:
                unit_cost = Decimal(cost_str)
                if unit_cost <= 0:
                    raise ValueError("must be positive")
            except Exception:
                errors.append(
                    ImportRowError(
                        row=row_num,
                        message=f"line_item_unit_cost '{cost_str}' must be a positive number",
                    )
                )
                continue

            line_items.append(
                {"product_id": product.id, "quantity": qty, "unit_cost": unit_cost}
            )

        if not line_items and not errors:
            errors.append(
                ImportRowError(
                    row=first_row_num,
                    message=f"Order for '{header_row.get('supplier_name')}' has no valid line items",
                )
            )
            continue

        if errors:
            continue  # collect all errors before bailing

        # Build OrderCreate data
        is_po_str = header_row.get("is_purchase_order", "").strip().upper()
        is_po = is_po_str == "TRUE"

        pt_raw = _opt_str(header_row.get("pay_term_type", ""))
        dt_raw = _opt_str(header_row.get("discount_type", ""))

        pay_term_type = (
            PayTermType(pt_raw) if pt_raw in (e.value for e in PayTermType) else None
        )
        discount_type = (
            DiscountType(dt_raw) if dt_raw in (e.value for e in DiscountType) else None
        )

        order_data = OrderCreate(
            supplier_name=header_row["supplier_name"].strip(),
            supplier_contact=_opt_str(header_row.get("supplier_contact", "")),
            currency=header_row.get("currency", "USD").strip() or "USD",
            is_purchase_order=is_po,
            pay_term_number=_opt_int(header_row.get("pay_term_number", "")),
            pay_term_type=pay_term_type,
            shipping_cost=_opt_decimal(header_row.get("shipping_cost", ""))
            or Decimal("0"),
            clearing_cost=_opt_decimal(header_row.get("clearing_cost", ""))
            or Decimal("0"),
            notes=_opt_str(header_row.get("notes", "")),
            discount_type=discount_type,
            discount_amount=_opt_decimal(header_row.get("discount_amount", ""))
            or Decimal("0"),
            tax_rate=_opt_decimal(header_row.get("tax_rate", "")),
            supplier_invoice_number=_opt_str(
                header_row.get("supplier_invoice_number", "")
            ),
            supplier_invoice_date=_opt_date(
                header_row.get("supplier_invoice_date", "")
            ),
            line_items=[
                OrderLineItemCreate(
                    product_id=li["product_id"],
                    quantity=li["quantity"],
                    unit_cost=li["unit_cost"],
                )
                for li in line_items
            ],
        )
        order_creates.append(order_data)

    if errors:
        return BulkImportResult(created=0, orders=[], errors=errors)

    # Create all orders
    created_orders = []
    for order_data in order_creates:
        order = await create_order(db, order_data, user_id, business_id=business_id)
        created_orders.append(order)

    await logger.ainfo("bulk_import_complete", created=len(created_orders))
    return BulkImportResult(
        created=len(created_orders), orders=created_orders, errors=[]
    )


# ---------------------------------------------------------------------------
# Parse products from file (no order creation — feed into the create-order form)
# ---------------------------------------------------------------------------

_PRODUCT_TEMPLATE_COLS = ["sku", "quantity", "unit_cost"]


def build_products_template_csv() -> str:
    """Simple 3-column template: one row per product, no order-level fields."""
    example = {"sku": "SKU-001", "quantity": "10", "unit_cost": "25.00"}
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_PRODUCT_TEMPLATE_COLS)
    writer.writeheader()
    writer.writerow(example)
    writer.writerow({"sku": "SKU-002", "quantity": "5", "unit_cost": "40.00"})
    return buf.getvalue()


async def parse_products_from_file(
    db: AsyncSession,
    file_bytes: bytes,
    filename: str,
) -> ParseProductsResult:
    """Parse a CSV or XLSX file and resolve SKUs to product IDs.

    Returns resolved line items ready to pre-fill the create-order form.
    Does NOT write anything to the database.
    """
    errors: list[ImportRowError] = []

    if not file_bytes:
        return ParseProductsResult(
            items=[], errors=[ImportRowError(row=0, message="File is empty")]
        )

    lower = filename.lower()
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        raw_rows = _parse_xlsx_bytes(file_bytes)
    else:
        raw_rows = _parse_csv_bytes(file_bytes)

    if not raw_rows:
        return ParseProductsResult(
            items=[], errors=[ImportRowError(row=0, message="File has no data rows")]
        )

    headers = set(raw_rows[0].keys())
    required = {"sku", "quantity", "unit_cost"}
    missing = required - headers
    if missing:
        return ParseProductsResult(
            items=[],
            errors=[
                ImportRowError(
                    row=0,
                    message=f"Missing required columns: {', '.join(sorted(missing))}",
                )
            ],
        )

    items: list[ParsedLineItem] = []
    for i, row in enumerate(raw_rows, start=2):
        sku = row.get("sku", "").strip()
        if not sku:
            errors.append(ImportRowError(row=i, message="sku is required"))
            continue

        result = await db.execute(select(Product).where(Product.sku == sku))
        product = result.scalar_one_or_none()
        if product is None:
            errors.append(
                ImportRowError(row=i, message=f"Product SKU '{sku}' not found")
            )
            continue

        qty_str = row.get("quantity", "").strip()
        cost_str = row.get("unit_cost", "").strip()

        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append(
                ImportRowError(
                    row=i,
                    message=f"quantity '{qty_str}' must be a positive integer",
                )
            )
            continue

        unit_cost = _opt_decimal(cost_str)
        if unit_cost is None or unit_cost <= 0:
            errors.append(
                ImportRowError(
                    row=i,
                    message=f"unit_cost '{cost_str}' must be a positive number",
                )
            )
            continue

        items.append(
            ParsedLineItem(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=qty,
                unit_cost=unit_cost,
            )
        )

    return ParseProductsResult(items=items, errors=errors)


async def list_purchase_returns(
    db: AsyncSession,
    order_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[PurchaseReturn], int]:
    """Return a paginated list of purchase returns, optionally filtered by order."""
    base_q = select(PurchaseReturn)
    if order_id:
        base_q = base_q.where(PurchaseReturn.original_order_id == order_id)
    if business_id is not None:
        base_q = base_q.where(PurchaseReturn.business_id == business_id)

    count_result = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = count_result.scalar() or 0

    items_result = await db.execute(
        base_q.order_by(
            PurchaseReturn.return_date.desc(), PurchaseReturn.created_at.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = items_result.scalars().all()
    return list(items), total


async def get_purchase_return(
    db: AsyncSession,
    return_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> PurchaseReturn:
    """Fetch a single purchase return by ID, raise PurchaseReturnNotFoundError if missing."""
    query = select(PurchaseReturn).where(PurchaseReturn.id == return_id)
    if business_id is not None:
        query = query.where(PurchaseReturn.business_id == business_id)
    result = await db.execute(query)
    pr = result.scalar_one_or_none()
    if pr is None:
        raise PurchaseReturnNotFoundError(return_id)
    return pr
