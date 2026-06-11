"""Orders domain business logic."""

import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.inventory.models import MovementType
from src.inventory.service import adjust_stock, create_batch
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    OrderLineItemError,
    OrderNotEditableError,
    OrderNotFoundError,
    OverpaymentError,
    PaymentNotFoundError,
)
from src.orders.models import (
    DiscountType,
    OrderLineItem,
    OrderPayment,
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
    OrderCreate,
    OrderLineItemCreate,
    OrderUpdate,
    ParsedLineItem,
    ParseProductsResult,
    PaymentCreate,
    PaymentSummary,
    PurchaseReturnCreate,
    StatusTransition,
)
from src.products.models import Product

logger = structlog.get_logger()

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
) -> PurchaseOrder:
    """Create a purchase order with line items."""
    # Validate all products exist
    product_ids = [item.product_id for item in data.line_items]
    for pid in product_ids:
        result = await db.execute(select(Product).where(Product.id == pid))
        if not result.scalar_one_or_none():
            raise OrderLineItemError(None, [pid])

    order_number = await _generate_order_number(db)

    # Calculate total
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
        notes=data.notes,
        created_by=user_id,
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

    # Create line items
    for item_data in data.line_items:
        line_item = OrderLineItem(
            order_id=order.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            unit_cost=item_data.unit_cost,
            unit_cost_ngn=item_data.unit_cost_ngn,
            line_total=item_data.unit_cost * item_data.quantity,
            notes=item_data.notes,
        )
        db.add(line_item)

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
) -> PurchaseOrder:
    """Get a purchase order with related data loaded."""
    result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.payments),
            selectinload(PurchaseOrder.status_history),
        )
        .where(PurchaseOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise OrderNotFoundError(order_id)
    return order


async def list_orders(
    db: AsyncSession,
    *,
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
    query = (
        query.order_by(PurchaseOrder.created_at.desc()).offset(offset).limit(page_size)
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

    # Replace line items if provided
    if line_items_data is not None:
        # Validate products
        for item_data in line_items_data:
            result = await db.execute(
                select(Product).where(Product.id == item_data["product_id"])
            )
            if not result.scalar_one_or_none():
                raise OrderLineItemError(order_id, [item_data["product_id"]])

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
            line_item = OrderLineItem(
                order_id=order.id,
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                unit_cost=Decimal(str(item_data["unit_cost"])),
                unit_cost_ngn=Decimal(str(raw_ngn)) if raw_ngn is not None else None,
                line_total=line_total,
                notes=item_data.get("notes"),
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
            await adjust_stock(
                db,
                product_id=item.product_id,
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


async def record_payment(
    db: AsyncSession,
    order_id: uuid.UUID,
    data: PaymentCreate,
    user_id: uuid.UUID,
) -> OrderPayment:
    """Record a payment against an order."""
    order = await get_order(db, order_id)

    # Check for overpayment
    summary = await get_payment_summary(db, order_id)
    balance = summary.balance_remaining
    if data.amount > balance:
        raise OverpaymentError(
            order_id, data.amount, order.total_amount, summary.total_paid
        )

    payment = OrderPayment(
        order_id=order.id,
        amount=data.amount,
        currency=data.currency,
        fx_rate=data.fx_rate,
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
) -> PaymentSummary:
    """Get payment summary for an order."""
    order = await get_order(db, order_id)
    result = await db.execute(
        select(
            func.coalesce(func.sum(OrderPayment.amount), 0),
            func.count(OrderPayment.id),
        )
        .where(OrderPayment.order_id == order_id)
        .where(OrderPayment.status == PaymentStatus.COMPLETED)
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
        is_fully_paid=balance <= 0,
    )


async def void_payment(
    db: AsyncSession,
    order_id: uuid.UUID,
    payment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrderPayment:
    """Void a payment record."""
    await get_order(db, order_id)
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

    await logger.ainfo(
        "payment_voided",
        order_id=str(order_id),
        payment_id=str(payment_id),
    )
    return payment


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


async def get_overdue_orders(db: AsyncSession) -> list[PurchaseOrder]:
    """Get orders past their expected delivery date."""
    today = date.today()
    terminal = [OrderStatus.DELIVERED, OrderStatus.CANCELLED]
    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(
            PurchaseOrder.expected_delivery_date < today,
            PurchaseOrder.status.notin_(terminal),
        )
        .order_by(PurchaseOrder.expected_delivery_date)
    )
    return list(result.scalars().all())


async def get_orders_summary(db: AsyncSession) -> dict:
    """Get summary statistics for all orders."""
    # Total count and value
    result = await db.execute(
        select(
            func.count(PurchaseOrder.id),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0),
        )
    )
    row = result.one()
    total_orders = row[0]
    total_value = row[1]

    # Count by status
    status_result = await db.execute(
        select(PurchaseOrder.status, func.count(PurchaseOrder.id)).group_by(
            PurchaseOrder.status
        )
    )
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


async def get_logistics_efficiency(db: AsyncSession) -> dict:
    """Calculate per-order logistics % and rolling 90-day average."""
    ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).date()

    result = await db.execute(
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
) -> PurchaseOrder:
    """Convert a Purchase Order (ORDERED status) to a received purchase.

    Sets is_purchase_order=False and status=PENDING so the order enters
    the normal delivery flow (PENDING → IN_PRODUCTION → ... → DELIVERED),
    at which point inventory is updated.
    """
    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == order_id)
    )
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
) -> PurchaseReturn:
    """Record a return of goods against a purchase order."""
    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == data.original_order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise OrderNotFoundError(data.original_order_id)

    # Build a map of product_id -> unit_cost from the original order
    cost_map: dict[uuid.UUID, Decimal] = {
        item.product_id: item.unit_cost for item in order.line_items
    }

    total_amount = Decimal("0")
    for line in data.line_items:
        pid = line.product_id
        unit_cost = cost_map.get(pid, Decimal("0"))
        total_amount += unit_cost * line.quantity

        # Reverse inventory: deduct returned stock
        await adjust_stock(
            db,
            product_id=pid,
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
        order = await create_order(db, order_data, user_id)
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
