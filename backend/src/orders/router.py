"""Orders API routes."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    OrderLineItemError,
    OrderNotEditableError,
    OrderNotFoundError,
    OverpaymentError,
    PaymentNotFoundError,
)
from src.orders.schemas import (
    LogisticsEfficiencyResponse,
    OrderCreate,
    OrderDetailRead,
    OrderListResponse,
    OrderRead,
    OrdersSummary,
    OrderUpdate,
    PaymentCreate,
    PaymentRead,
    PaymentSummary,
    StatusHistoryRead,
    StatusTransition,
)
from src.orders.service import (
    cancel_order,
    check_logistics_alerts,
    create_order,
    get_logistics_efficiency,
    get_order,
    get_orders_summary,
    get_overdue_orders,
    get_payment_summary,
    get_status_history,
    list_orders,
    list_payments,
    record_payment,
    transition_status,
    update_order,
    void_payment,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Purchase order CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order_endpoint(
    body: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new purchase order."""
    try:
        return await create_order(db, body, current_user.id)
    except OrderLineItemError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=OrderListResponse)
async def list_orders_endpoint(
    order_status: str | None = None,
    supplier_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List orders with optional filters."""
    items, total = await list_orders(
        db,
        status=order_status,
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return OrderListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/summary", response_model=OrdersSummary)
async def orders_summary_endpoint(db: AsyncSession = Depends(get_db)):
    """Get order summary statistics."""
    data = await get_orders_summary(db)
    return OrdersSummary(**data)


@router.get("/overdue", response_model=list[OrderRead])
async def overdue_orders_endpoint(db: AsyncSession = Depends(get_db)):
    """List overdue orders."""
    return await get_overdue_orders(db)


@router.get("/{order_id}", response_model=OrderDetailRead)
async def get_order_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get order details with payment summary."""
    try:
        order = await get_order(db, order_id)
        summary = await get_payment_summary(db, order_id)
        # Build response with payment summary
        order_data = OrderDetailRead.model_validate(order)
        order_data.payment_summary = summary
        return order_data
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{order_id}", response_model=OrderRead)
async def update_order_endpoint(
    order_id: uuid.UUID,
    body: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update an order (only Pending/In Production)."""
    try:
        return await update_order(db, order_id, body, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except OrderNotEditableError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except OrderLineItemError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{order_id}", response_model=OrderRead)
async def cancel_order_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel an order (only Pending)."""
    try:
        return await cancel_order(db, order_id, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Status workflow
# ---------------------------------------------------------------------------


@router.put("/{order_id}/status", response_model=OrderRead)
async def transition_status_endpoint(
    order_id: uuid.UUID,
    body: StatusTransition,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Transition an order to the next status."""
    try:
        return await transition_status(db, order_id, body, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (ProductStockNotFoundError, InvalidStockAdjustmentError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{order_id}/status-history", response_model=list[StatusHistoryRead])
async def status_history_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get status transition history."""
    try:
        return await get_status_history(db, order_id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Payment tracking
# ---------------------------------------------------------------------------


@router.post("/{order_id}/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def record_payment_endpoint(
    order_id: uuid.UUID,
    body: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a payment against an order."""
    try:
        return await record_payment(db, order_id, body, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except OverpaymentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{order_id}/payments", response_model=list[PaymentRead])
async def list_payments_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all payments for an order."""
    try:
        return await list_payments(db, order_id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{order_id}/payment-summary", response_model=PaymentSummary)
async def payment_summary_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get payment summary for an order."""
    try:
        return await get_payment_summary(db, order_id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{order_id}/payments/{payment_id}", response_model=PaymentRead)
async def void_payment_endpoint(
    order_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Void a payment record."""
    try:
        return await void_payment(db, order_id, payment_id, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Logistics Efficiency
# ---------------------------------------------------------------------------


@router.get("/logistics-efficiency", response_model=LogisticsEfficiencyResponse)
async def logistics_efficiency_endpoint(db: AsyncSession = Depends(get_db)):
    """Get logistics cost efficiency metrics (per-order and rolling 90d average)."""
    data = await get_logistics_efficiency(db)
    return LogisticsEfficiencyResponse(**data)
