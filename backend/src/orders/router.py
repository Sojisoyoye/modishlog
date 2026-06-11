"""Orders API routes."""

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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
from fastapi import File, UploadFile

from src.orders.schemas import (
    BulkImportResult,
    LogisticsEfficiencyResponse,
    LotRead,
    ParseProductsResult,
    OrderCreate,
    OrderDetailRead,
    OrderListResponse,
    OrderRead,
    OrdersSummary,
    OrderUpdate,
    PaymentCreate,
    PaymentRead,
    PaymentSummary,
    PurchaseReturnCreate,
    PurchaseReturnRead,
    StatusHistoryRead,
    StatusTransition,
)
from src.orders.service import (
    build_import_template_csv,
    build_products_template_csv,
    cancel_order,
    convert_po_to_purchase,
    create_order,
    create_purchase_return,
    get_logistics_efficiency,
    get_order,
    get_orders_summary,
    get_overdue_orders,
    get_paid_totals_for_orders,
    get_payment_summary,
    get_status_history,
    import_orders_from_file,
    list_orders,
    parse_products_from_file,
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

    paid_map = await get_paid_totals_for_orders(db, items)

    order_reads = []
    for order in items:
        r = OrderRead.model_validate(order)
        r.total_paid = paid_map.get(order.id, Decimal("0"))
        r.balance_remaining = order.total_amount - r.total_paid
        if r.total_paid == 0:
            r.payment_status = "UNPAID"
        elif r.balance_remaining <= 0:
            r.payment_status = "PAID"
        else:
            r.payment_status = "PARTIAL"
        order_reads.append(r)

    return OrderListResponse(
        items=order_reads, total=total, page=page, page_size=page_size
    )


@router.get("/parse-products/template")
async def get_products_template_endpoint():
    """Download the simple 3-column product import template (sku, quantity, unit_cost)."""
    content = build_products_template_csv()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=products_import_template.csv"
        },
    )


@router.post(
    "/parse-products",
    response_model=ParseProductsResult,
    status_code=status.HTTP_200_OK,
)
async def parse_products_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Parse a CSV or XLSX file and return resolved line items for the create-order form.

    Does NOT create any orders — use this to pre-fill the product table.
    """
    file_bytes = await file.read()
    return await parse_products_from_file(db, file_bytes, file.filename or "upload.csv")


@router.get("/import/template")
async def get_import_template_endpoint():
    """Download a CSV template with all supported import columns and an example row."""
    content = build_import_template_csv()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=orders_import_template.csv"
        },
    )


@router.post("/import", response_model=BulkImportResult, status_code=status.HTTP_200_OK)
async def import_orders_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Import multiple purchase orders from a CSV or Excel file."""
    allowed = {
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
    }
    if file.content_type and file.content_type not in allowed:
        # Check by extension as browsers sometimes send wrong content-type
        fname = (file.filename or "").lower()
        if not (
            fname.endswith(".csv") or fname.endswith(".xlsx") or fname.endswith(".xls")
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only CSV and Excel (.xlsx) files are supported",
            )

    file_bytes = await file.read()
    return await import_orders_from_file(
        db, file_bytes, file.filename or "upload.csv", current_user.id
    )


@router.get("/logistics-efficiency", response_model=LogisticsEfficiencyResponse)
async def logistics_efficiency_endpoint(db: AsyncSession = Depends(get_db)):
    """Get logistics cost efficiency metrics (per-order and rolling 90d average)."""
    data = await get_logistics_efficiency(db)
    return LogisticsEfficiencyResponse(**data)


@router.get("/summary", response_model=OrdersSummary)
async def orders_summary_endpoint(db: AsyncSession = Depends(get_db)):
    """Get order summary statistics."""
    data = await get_orders_summary(db)
    return OrdersSummary(**data)


@router.get("/overdue", response_model=list[OrderRead])
async def overdue_orders_endpoint(db: AsyncSession = Depends(get_db)):
    """List overdue orders."""
    return await get_overdue_orders(db)


@router.get("/export.csv")
async def export_orders_csv_endpoint(
    order_status: str | None = None,
    supplier_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export purchase orders as a CSV file matching current filter params."""
    items, _ = await list_orders(
        db,
        status=order_status,
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=100_000,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "order_number",
            "supplier_name",
            "status",
            "total_amount",
            "currency",
            "expected_delivery_date",
            "actual_delivery_date",
        ]
    )
    for order in items:
        writer.writerow(
            [
                str(order.id),
                order.order_number,
                order.supplier_name,
                order.status.value if order.status else "",
                str(order.total_amount),
                order.currency,
                str(order.expected_delivery_date)
                if order.expected_delivery_date
                else "",
                str(order.actual_delivery_date) if order.actual_delivery_date else "",
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_export.csv"},
    )


@router.post(
    "/returns", response_model=PurchaseReturnRead, status_code=status.HTTP_201_CREATED
)
async def create_purchase_return_endpoint(
    body: PurchaseReturnCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a return of goods against a received purchase order."""
    try:
        return await create_purchase_return(db, body, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{order_id}/lots", response_model=list[LotRead])
async def get_order_lots_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return lot inventory (units_remaining) for each line item in a delivered order."""
    try:
        order = await get_order(db, order_id)
        return [LotRead.model_validate(item) for item in order.line_items]
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{order_id}", response_model=OrderDetailRead)
async def get_order_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get order details with payment summary."""
    try:
        order = await get_order(db, order_id)
        summary = await get_payment_summary(db, order_id)
        order_data = OrderDetailRead.model_validate(order)
        order_data.payment_summary = summary
        order_data.total_paid = summary.total_paid
        order_data.balance_remaining = summary.balance_remaining
        if summary.total_paid == 0:
            order_data.payment_status = "UNPAID"
        elif summary.is_fully_paid:
            order_data.payment_status = "PAID"
        else:
            order_data.payment_status = "PARTIAL"
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
        await update_order(db, order_id, body, current_user.id)
        # Expire identity map so the re-fetch loads fresh line_items from DB
        db.expire_all()
        return await get_order(db, order_id)
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


@router.post(
    "/{order_id}/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
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


@router.post("/{order_id}/convert-to-purchase", response_model=OrderRead)
async def convert_po_to_purchase_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Convert a Purchase Order (ORDERED status) to a received purchase."""
    try:
        return await convert_po_to_purchase(db, order_id, current_user.id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
