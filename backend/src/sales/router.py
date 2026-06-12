"""Sales API routes."""

import csv
import io
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user, require_any_role
from src.auth.models import User, UserRole
from src.core.database import get_db
from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.products.exceptions import ProductNotFoundError
from src.sales.exceptions import (
    BulkUploadJobNotFoundError,
    InvalidCSVFormatError,
    SaleAlreadyVoidedError,
    SaleNotFoundError,
    SaleValidationError,
)
from src.sales.schemas import (
    AuditEntryRead,
    BulkUploadResponse,
    BulkUploadStatus,
    DailyEntryRequest,
    QuickQuoteRequest,
    QuickQuoteResponse,
    SaleCreate,
    SaleListResponse,
    SaleRead,
    SalesHistoryEntry,
    SalesSummary,
    SaleTransactionListResponse,
    SaleTransactionRead,
    SaleUpdate,
)
from src.sales.service import (
    create_sale,
    get_sale,
    get_sale_audit_trail,
    get_sales_history,
    get_sales_summary,
    get_transaction,
    get_upload_status,
    list_sales,
    list_transactions,
    process_bulk_upload,
    quick_quote,
    update_sale,
    void_sale,
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])


def _check_ownership(resource_owner_id: uuid.UUID, current_user: User) -> None:
    """Raise 403 if non-admin user tries to access a resource they don't own."""
    if current_user.role != UserRole.ADMIN and resource_owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you can only access your own resources",
        )


# ---------------------------------------------------------------------------
# Daily sales entry
# ---------------------------------------------------------------------------


@router.post("", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
async def create_sale_endpoint(
    body: SaleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a new sale."""
    try:
        return await create_sale(db, body, current_user.id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SaleValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (ProductStockNotFoundError, InvalidStockAdjustmentError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/daily-entry", response_model=list[SaleRead], status_code=status.HTTP_201_CREATED
)
async def daily_entry_endpoint(
    body: DailyEntryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record multiple sales from daily entry form.

    Looks up each product's selling_price for unit_price and defaults channel to retail.
    """
    from src.products.models import Product
    from sqlalchemy import select

    transaction_id = uuid.uuid4()
    results = []
    for entry in body.entries:
        result = await db.execute(select(Product).where(Product.id == entry.product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found: {entry.product_id}",
            )
        sale_data = SaleCreate(
            product_id=entry.product_id,
            quantity=entry.quantity,
            unit_price=product.selling_price,
            sale_date=entry.sale_date,
            channel="retail",
            discount_amount=entry.discount_amount,
            transaction_id=transaction_id,
            customer_id=entry.customer_id,
            customer_name=entry.customer_name,
            contact_number=entry.contact_number,
            payment_method=entry.payment_method,
            payment_status=entry.payment_status,
        )
        try:
            sale = await create_sale(db, sale_data, current_user.id)
            results.append(sale)
        except (ProductNotFoundError, SaleValidationError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except (ProductStockNotFoundError, InvalidStockAdjustmentError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return results


@router.get("", response_model=SaleListResponse)
async def list_sales_endpoint(
    product_id: uuid.UUID | None = None,
    channel: str | None = None,
    sale_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List sales with optional filters."""
    items, total = await list_sales(
        db,
        product_id=product_id,
        channel=channel,
        status=sale_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return SaleListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/summary", response_model=SalesSummary)
async def sales_summary_endpoint(
    date_from: date = None,
    date_to: date = None,
    db: AsyncSession = Depends(get_db),
):
    """Get sales summary for a date range."""
    if date_from is None:
        date_from = date.today() - timedelta(days=30)
    if date_to is None:
        date_to = date.today()
    return await get_sales_summary(db, date_from, date_to)


@router.get("/history", response_model=list[SalesHistoryEntry])
async def sales_history_endpoint(
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
):
    """Get daily aggregated sales history."""
    return await get_sales_history(db, date_from, date_to)


@router.post("/quick-quote", response_model=QuickQuoteResponse)
async def quick_quote_endpoint(
    body: QuickQuoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    """Calculate minimum sell price using FIFO weighted-average landed cost."""
    return await quick_quote(db, body.product_id, body.quantity)


@router.post("/upload", response_model=BulkUploadResponse)
async def upload_sales_csv_endpoint(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a CSV file of sales records."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted",
        )
    try:
        content = await file.read()
        job = await process_bulk_upload(db, content, file.filename, current_user.id)
        return BulkUploadResponse(
            job_id=job.id,
            status=job.status.value,
            message=f"Processed {job.total_rows} rows: {job.successful_rows} successful, {job.failed_rows} failed",
        )
    except InvalidCSVFormatError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/upload/{job_id}/status", response_model=BulkUploadStatus)
async def upload_status_endpoint(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Check the status of a bulk upload job."""
    try:
        return await get_upload_status(db, job_id)
    except BulkUploadJobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/transactions", response_model=SaleTransactionListResponse)
async def list_transactions_endpoint(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List sales grouped by transaction (most recent first)."""
    items, total = await list_transactions(db, page=page, page_size=page_size)
    return SaleTransactionListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/transactions/{transaction_id}", response_model=SaleTransactionRead)
async def get_transaction_endpoint(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all sale items for a given transaction."""
    try:
        return await get_transaction(db, transaction_id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/export.csv")
async def export_sales_csv_endpoint(
    product_id: uuid.UUID | None = None,
    channel: str | None = None,
    sale_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export sales as a CSV file matching current filter params."""
    items, _ = await list_sales(
        db,
        product_id=product_id,
        channel=channel,
        status=sale_status,
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
            "sale_date",
            "product_id",
            "quantity",
            "unit_price",
            "total_amount",
            "discount_amount",
            "channel",
            "status",
            "currency",
        ]
    )
    for sale in items:
        writer.writerow(
            [
                str(sale.id),
                str(sale.sale_date),
                str(sale.product_id),
                sale.quantity,
                str(sale.unit_price),
                str(sale.total_amount),
                str(sale.discount_amount) if sale.discount_amount is not None else "",
                sale.channel.value if sale.channel else "",
                sale.status.value if sale.status else "",
                sale.currency,
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_export.csv"},
    )


@router.get("/{sale_id}", response_model=SaleRead)
async def get_sale_endpoint(
    sale_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single sale by ID."""
    try:
        sale = await get_sale(db, sale_id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    _check_ownership(sale.recorded_by, current_user)
    return sale


@router.put("/{sale_id}", response_model=SaleRead)
async def update_sale_endpoint(
    sale_id: uuid.UUID,
    body: SaleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a sale record."""
    try:
        existing = await get_sale(db, sale_id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    _check_ownership(existing.recorded_by, current_user)
    try:
        return await update_sale(db, sale_id, body, current_user.id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SaleAlreadyVoidedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (ProductStockNotFoundError, InvalidStockAdjustmentError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{sale_id}", response_model=SaleRead)
async def void_sale_endpoint(
    sale_id: uuid.UUID,
    reason: str = "No reason provided",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Void a sale (soft-delete with inventory reversal)."""
    try:
        existing = await get_sale(db, sale_id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    _check_ownership(existing.recorded_by, current_user)
    try:
        return await void_sale(db, sale_id, reason, current_user.id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SaleAlreadyVoidedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{sale_id}/audit", response_model=list[AuditEntryRead])
async def sale_audit_trail_endpoint(
    sale_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the audit trail for a specific sale."""
    try:
        sale = await get_sale(db, sale_id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    _check_ownership(sale.recorded_by, current_user)
    try:
        return await get_sale_audit_trail(db, sale_id)
    except SaleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
