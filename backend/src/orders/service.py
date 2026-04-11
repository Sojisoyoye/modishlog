"""Orders domain business logic."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.inventory.models import MovementType
from src.inventory.service import adjust_stock
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    OrderLineItemError,
    OrderNotEditableError,
    OrderNotFoundError,
    OverpaymentError,
    PaymentNotFoundError,
)
from src.orders.models import (
    OrderLineItem,
    OrderPayment,
    OrderStatus,
    OrderStatusHistory,
    PaymentMethod,
    PaymentStatus,
    PurchaseOrder,
)
from src.orders.schemas import (
    OrderCreate,
    OrderUpdate,
    PaymentCreate,
    PaymentSummary,
    StatusTransition,
)
from src.products.models import Product

logger = structlog.get_logger()

# Valid status transitions
VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.PENDING: [OrderStatus.IN_PRODUCTION, OrderStatus.CANCELLED],
    OrderStatus.IN_PRODUCTION: [OrderStatus.SHIPPING],
    OrderStatus.SHIPPING: [OrderStatus.CLEARED],
    OrderStatus.CLEARED: [OrderStatus.DELIVERED],
}

# Statuses that allow order editing
EDITABLE_STATUSES = {OrderStatus.PENDING, OrderStatus.IN_PRODUCTION}


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
    if expected_delivery is None and any([
        data.production_days, data.shipping_days, data.clearing_days
    ]):
        total_days = (data.production_days or 0) + (data.shipping_days or 0) + (data.clearing_days or 0)
        expected_delivery = date.today() + timedelta(days=total_days)

    order = PurchaseOrder(
        order_number=order_number,
        supplier_name=data.supplier_name,
        supplier_contact=data.supplier_contact,
        status=OrderStatus.PENDING,
        total_amount=total_amount,
        currency=data.currency,
        fx_rate_at_creation=data.fx_rate_at_creation,
        shipping_cost=data.shipping_cost,
        clearing_cost=data.clearing_cost,
        expected_delivery_date=expected_delivery,
        notes=data.notes,
        created_by=user_id,
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
            line_total=item_data.unit_cost * item_data.quantity,
            notes=item_data.notes,
        )
        db.add(line_item)

    # Initial status history
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=None,
        to_status=OrderStatus.PENDING.value,
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
    return order


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
        query = query.where(PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time()))
        count_query = count_query.where(PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        query = query.where(PurchaseOrder.created_at <= datetime.combine(date_to, datetime.max.time()))
        count_query = count_query.where(PurchaseOrder.created_at <= datetime.combine(date_to, datetime.max.time()))
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
    query = query.order_by(PurchaseOrder.created_at.desc()).offset(offset).limit(page_size)
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
            line_item = OrderLineItem(
                order_id=order.id,
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                unit_cost=Decimal(str(item_data["unit_cost"])),
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

        # Restock inventory for each line item
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
        select(func.count(PurchaseOrder.id), func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
    )
    row = result.one()
    total_orders = row[0]
    total_value = row[1]

    # Count by status
    status_result = await db.execute(
        select(PurchaseOrder.status, func.count(PurchaseOrder.id)).group_by(PurchaseOrder.status)
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
    return (
        (shipping_cost + clearing_cost) / total_cogs * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def get_logistics_efficiency(db: AsyncSession) -> dict:
    """Calculate per-order logistics % and rolling 90-day average."""
    ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).date()

    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(
            PurchaseOrder.status != OrderStatus.CANCELLED,
            PurchaseOrder.created_at >= datetime.combine(
                ninety_days_ago, datetime.min.time()
            ).replace(tzinfo=timezone.utc),
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
        per_order.append({
            "order_id": order.id,
            "order_number": order.order_number,
            "logistics_pct": lp,
            "logistics_ngn": logistics_ngn,
            "total_cogs_ngn": total_cogs,
        })
        total_logistics += logistics_ngn
        total_cogs_sum += total_cogs

    rolling_avg = calculate_logistics_pct(
        total_logistics, Decimal("0"), total_cogs_sum
    )

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
        select(func.count()).select_from(AIRecommendation).where(
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
