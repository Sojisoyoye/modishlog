"""Sales domain business logic."""

import csv
import io
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.inventory.models import MovementType
from src.inventory.service import adjust_stock, fifo_deduct
from src.products.models import Product
from src.sales.exceptions import (
    BulkUploadJobNotFoundError,
    InvalidCSVFormatError,
    SaleAlreadyVoidedError,
    SaleNotFoundError,
)
from src.sales.models import (
    Sale,
    SaleAuditEntry,
    SaleBulkUploadJob,
    SaleChannel,
    SaleStatus,
    UploadJobStatus,
)
from src.sales.schemas import (
    QuickQuoteResponse,
    SaleCreate,
    SalesHistoryEntry,
    SalesSummary,
    SaleTransactionItemRead,
    SaleTransactionRead,
    SaleUpdate,
)
from src.inventory.models import InventoryBatch

logger = structlog.get_logger()

REQUIRED_CSV_HEADERS = {"product_id", "quantity", "unit_price", "sale_date", "channel"}


# ---------------------------------------------------------------------------
# Daily sales entry
# ---------------------------------------------------------------------------


async def create_sale(
    db: AsyncSession,
    data: SaleCreate,
    user_id: uuid.UUID,
) -> Sale:
    """Record a sale and deplete inventory atomically."""
    # Validate product exists and is active
    result = await db.execute(select(Product).where(Product.id == data.product_id))
    product = result.scalar_one_or_none()
    if not product:
        from src.products.exceptions import ProductNotFoundError

        raise ProductNotFoundError(product_id=data.product_id)
    if not product.is_active:
        from src.sales.exceptions import SaleValidationError

        raise SaleValidationError(
            "product_id", str(data.product_id), "Product is inactive"
        )

    gross = data.unit_price * data.quantity
    discount = data.discount_amount or Decimal("0")
    if discount > gross:
        from src.sales.exceptions import SaleValidationError

        raise SaleValidationError(
            "discount_amount",
            str(discount),
            "Discount cannot exceed gross amount",
        )
    total_amount = gross - discount

    sale = Sale(
        product_id=data.product_id,
        quantity=data.quantity,
        unit_price=data.unit_price,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        transaction_id=data.transaction_id,
        currency=product.currency,
        sale_date=data.sale_date,
        channel=SaleChannel(data.channel),
        status=SaleStatus.COMPLETED,
        notes=data.notes,
        recorded_by=user_id,
    )
    db.add(sale)
    await db.flush()

    # Audit entry
    audit = SaleAuditEntry(
        sale_id=sale.id,
        action="created",
        field_changes=None,
        performed_by=user_id,
        reason=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)

    # Deplete inventory
    await adjust_stock(
        db,
        product_id=data.product_id,
        quantity_change=-data.quantity,
        movement_type=MovementType.SALE_DEPLETION.value,
        reason=f"Sale {sale.id}",
        user_id=user_id,
        reference_id=sale.id,
        reference_type="sale",
    )

    # FIFO cost matching
    cogs_result = await fifo_deduct(db, data.product_id, data.quantity)
    sale.fifo_cogs = cogs_result
    sale.fifo_gross_profit = sale.total_amount - cogs_result
    await db.flush()

    await logger.ainfo(
        "sale_created",
        sale_id=str(sale.id),
        product_id=str(data.product_id),
        quantity=data.quantity,
        total=str(total_amount),
    )
    return sale


async def get_sale(db: AsyncSession, sale_id: uuid.UUID) -> Sale:
    """Get a single sale by ID."""
    result = await db.execute(select(Sale).where(Sale.id == sale_id))
    sale = result.scalar_one_or_none()
    if not sale:
        raise SaleNotFoundError(sale_id)
    return sale


async def list_sales(
    db: AsyncSession,
    *,
    product_id: uuid.UUID | None = None,
    channel: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Sale], int]:
    """List sales with filtering and pagination."""
    query = select(Sale)
    count_query = select(func.count()).select_from(Sale)

    if product_id is not None:
        query = query.where(Sale.product_id == product_id)
        count_query = count_query.where(Sale.product_id == product_id)
    if channel is not None:
        query = query.where(Sale.channel == SaleChannel(channel))
        count_query = count_query.where(Sale.channel == SaleChannel(channel))
    if status is not None:
        query = query.where(Sale.status == SaleStatus(status))
        count_query = count_query.where(Sale.status == SaleStatus(status))
    if date_from is not None:
        query = query.where(Sale.sale_date >= date_from)
        count_query = count_query.where(Sale.sale_date >= date_from)
    if date_to is not None:
        query = query.where(Sale.sale_date <= date_to)
        count_query = count_query.where(Sale.sale_date <= date_to)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Sale.sale_date.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_sale(
    db: AsyncSession,
    sale_id: uuid.UUID,
    data: SaleUpdate,
    user_id: uuid.UUID,
) -> Sale:
    """Update a sale. Adjusts inventory if quantity changes."""
    sale = await get_sale(db, sale_id)

    if sale.status == SaleStatus.VOIDED:
        raise SaleAlreadyVoidedError(sale_id)

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        return sale

    # Track changes for audit
    field_changes = {}
    old_quantity = sale.quantity
    quantity_changed = False

    for field, value in update_fields.items():
        old_value = getattr(sale, field)
        if old_value != value:
            field_changes[field] = {"old": str(old_value), "new": str(value)}

    # Apply updates
    for field, value in update_fields.items():
        if field == "channel":
            setattr(sale, field, SaleChannel(value))
        else:
            setattr(sale, field, value)

    # Recalculate total if quantity or price changed (preserve discount)
    if "quantity" in update_fields or "unit_price" in update_fields:
        sale.total_amount = sale.unit_price * sale.quantity - (
            sale.discount_amount or Decimal("0")
        )

    if "quantity" in update_fields and update_fields["quantity"] != old_quantity:
        quantity_changed = True

    await db.flush()

    # Audit entry
    if field_changes:
        audit = SaleAuditEntry(
            sale_id=sale.id,
            action="updated",
            field_changes=field_changes,
            performed_by=user_id,
            reason=None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)

    # Adjust inventory if quantity changed
    if quantity_changed:
        quantity_diff = (
            old_quantity - sale.quantity
        )  # positive = restoring, negative = depleting more
        await adjust_stock(
            db,
            product_id=sale.product_id,
            quantity_change=quantity_diff,
            movement_type=MovementType.SALE_DEPLETION.value,
            reason=f"Sale {sale.id} quantity updated from {old_quantity} to {sale.quantity}",
            user_id=user_id,
            reference_id=sale.id,
            reference_type="sale_update",
        )

    await logger.ainfo("sale_updated", sale_id=str(sale_id), changes=field_changes)
    return sale


async def void_sale(
    db: AsyncSession,
    sale_id: uuid.UUID,
    reason: str,
    user_id: uuid.UUID,
) -> Sale:
    """Void a sale and restore inventory."""
    sale = await get_sale(db, sale_id)

    if sale.status == SaleStatus.VOIDED:
        raise SaleAlreadyVoidedError(sale_id)

    sale.status = SaleStatus.VOIDED
    await db.flush()

    # Audit entry
    audit = SaleAuditEntry(
        sale_id=sale.id,
        action="voided",
        field_changes={"status": {"old": "completed", "new": "voided"}},
        performed_by=user_id,
        reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)

    # Restore inventory
    await adjust_stock(
        db,
        product_id=sale.product_id,
        quantity_change=sale.quantity,
        movement_type=MovementType.SALE_REVERSAL.value,
        reason=f"Voided sale {sale.id}: {reason}",
        user_id=user_id,
        reference_id=sale.id,
        reference_type="sale_void",
    )

    await logger.ainfo("sale_voided", sale_id=str(sale_id), reason=reason)
    return sale


# ---------------------------------------------------------------------------
# Bulk CSV upload
# ---------------------------------------------------------------------------


async def process_bulk_upload(
    db: AsyncSession,
    file_content: bytes,
    filename: str,
    user_id: uuid.UUID,
) -> SaleBulkUploadJob:
    """Parse and process a CSV file of sales records."""
    # Create job record
    job = SaleBulkUploadJob(
        filename=filename,
        status=UploadJobStatus.PROCESSING,
        total_rows=0,
        processed_rows=0,
        successful_rows=0,
        failed_rows=0,
        uploaded_by=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    # Parse CSV
    try:
        text = file_content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise InvalidCSVFormatError(filename, "Empty CSV file")

        headers = set(reader.fieldnames)
        missing = REQUIRED_CSV_HEADERS - headers
        if missing:
            raise InvalidCSVFormatError(
                filename, f"Missing required headers: {', '.join(sorted(missing))}"
            )

        rows = list(reader)
    except UnicodeDecodeError:
        raise InvalidCSVFormatError(filename, "File is not valid UTF-8")

    job.total_rows = len(rows)
    errors: list[dict] = []

    for i, row in enumerate(rows, start=1):
        job.processed_rows = i
        try:
            sale_data = SaleCreate(
                product_id=uuid.UUID(row["product_id"]),
                quantity=int(row["quantity"]),
                unit_price=Decimal(row["unit_price"]),
                sale_date=date.fromisoformat(row["sale_date"]),
                channel=row["channel"],
                notes=row.get("notes"),
            )
            await create_sale(db, sale_data, user_id)
            job.successful_rows += 1
        except (ValueError, InvalidOperation, KeyError) as e:
            job.failed_rows += 1
            errors.append({"row": i, "error": str(e)})
        except Exception as e:
            job.failed_rows += 1
            errors.append({"row": i, "error": str(e)})

    # Set final status
    if job.failed_rows == 0:
        job.status = UploadJobStatus.COMPLETED
    elif job.successful_rows == 0:
        job.status = UploadJobStatus.FAILED
    else:
        job.status = UploadJobStatus.PARTIAL

    if errors:
        job.error_details = {"errors": errors}

    job.completed_at = datetime.now(timezone.utc)
    await db.flush()

    await logger.ainfo(
        "bulk_upload_completed",
        job_id=str(job.id),
        total=job.total_rows,
        successful=job.successful_rows,
        failed=job.failed_rows,
    )
    return job


async def get_upload_status(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> SaleBulkUploadJob:
    """Get the status of a bulk upload job."""
    result = await db.execute(
        select(SaleBulkUploadJob).where(SaleBulkUploadJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise BulkUploadJobNotFoundError(job_id)
    return job


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


async def get_sale_audit_trail(
    db: AsyncSession,
    sale_id: uuid.UUID,
) -> list[SaleAuditEntry]:
    """Get the full audit trail for a sale."""
    await get_sale(db, sale_id)  # ensure sale exists
    result = await db.execute(
        select(SaleAuditEntry)
        .where(SaleAuditEntry.sale_id == sale_id)
        .order_by(SaleAuditEntry.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Sales reporting
# ---------------------------------------------------------------------------


async def get_sales_summary(
    db: AsyncSession,
    date_from: date,
    date_to: date,
) -> SalesSummary:
    """Get sales summary for a date range."""
    base_filter = (
        (Sale.sale_date >= date_from)
        & (Sale.sale_date <= date_to)
        & (Sale.status == SaleStatus.COMPLETED)
    )

    result = await db.execute(
        select(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.quantity), 0),
            func.count(Sale.id),
        ).where(base_filter)
    )
    row = result.one()

    return SalesSummary(
        period=f"{date_from} to {date_to}",
        total_revenue=row[0],
        total_units_sold=row[1],
        transaction_count=row[2],
    )


async def get_sales_history(
    db: AsyncSession,
    date_from: date,
    date_to: date,
) -> list[SalesHistoryEntry]:
    """Get daily aggregated sales history."""
    result = await db.execute(
        select(
            Sale.sale_date,
            func.sum(Sale.total_amount),
            func.sum(Sale.quantity),
            func.count(Sale.id),
        )
        .where(
            (Sale.sale_date >= date_from)
            & (Sale.sale_date <= date_to)
            & (Sale.status == SaleStatus.COMPLETED)
        )
        .group_by(Sale.sale_date)
        .order_by(Sale.sale_date)
    )
    rows = result.all()
    return [
        SalesHistoryEntry(
            date=row[0],
            revenue=row[1],
            units_sold=row[2],
            transaction_count=row[3],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Quick Quote
# ---------------------------------------------------------------------------

DEFAULT_FLOOR_MARGIN_PCT = Decimal("15")


async def quick_quote(
    db: AsyncSession,
    product_id: uuid.UUID,
    quantity: int,
    floor_margin_pct: Decimal = DEFAULT_FLOOR_MARGIN_PCT,
) -> QuickQuoteResponse:
    """Calculate minimum sell price using FIFO weighted-average landed cost.

    Queries FIFO batches (oldest first with quantity_remaining > 0),
    computes a weighted average landed cost for the requested quantity,
    then applies the floor margin to derive the minimum sell price.
    """
    result = await db.execute(
        select(InventoryBatch)
        .where(
            InventoryBatch.product_id == product_id,
            InventoryBatch.quantity_remaining > 0,
        )
        .order_by(InventoryBatch.received_at.asc())
    )
    batches = list(result.scalars().all())

    if not batches:
        zero = Decimal("0")
        return QuickQuoteResponse(
            product_id=product_id,
            quantity=quantity,
            fifo_landed_cost_per_unit=zero,
            floor_margin_pct=floor_margin_pct,
            min_sell_price_per_unit=zero,
            total_min_price=zero,
        )

    remaining = quantity
    total_cost = Decimal("0")
    units_costed = 0

    for batch in batches:
        if remaining <= 0:
            break
        consume = min(remaining, batch.quantity_remaining)
        total_cost += Decimal(str(consume)) * batch.landed_cost_per_unit
        units_costed += consume
        remaining -= consume

    if units_costed > 0:
        avg_cost = (total_cost / Decimal(str(units_costed))).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    else:
        avg_cost = Decimal("0")

    margin_multiplier = Decimal("1") + floor_margin_pct / Decimal("100")
    min_sell = (avg_cost * margin_multiplier).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    total_min = (min_sell * Decimal(str(quantity))).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )

    await logger.ainfo(
        "quick_quote_calculated",
        product_id=str(product_id),
        quantity=quantity,
        avg_cost=str(avg_cost),
        min_sell=str(min_sell),
    )

    return QuickQuoteResponse(
        product_id=product_id,
        quantity=quantity,
        fifo_landed_cost_per_unit=avg_cost,
        floor_margin_pct=floor_margin_pct,
        min_sell_price_per_unit=min_sell,
        total_min_price=total_min,
    )


# ---------------------------------------------------------------------------
# Transaction grouping
# ---------------------------------------------------------------------------


def _build_transaction_read(
    transaction_id: uuid.UUID,
    items: list[Sale],
) -> "SaleTransactionRead":
    """Build a SaleTransactionRead from a list of Sale records."""

    total_amount = sum(s.total_amount for s in items)
    sale_date = items[0].sale_date if items else date.today()
    created_at = (
        min(s.created_at for s in items) if items else datetime.now(timezone.utc)
    )
    currency = items[0].currency if items else "NGN"

    statuses = {s.status for s in items}
    if statuses == {SaleStatus.VOIDED}:
        status = "voided"
    elif SaleStatus.VOIDED in statuses:
        status = "partial"
    else:
        status = "completed"

    item_reads = [
        SaleTransactionItemRead(
            id=s.id,
            product_id=s.product_id,
            quantity=s.quantity,
            unit_price=s.unit_price,
            discount_amount=s.discount_amount,
            total_amount=s.total_amount,
            currency=s.currency,
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            notes=s.notes,
        )
        for s in items
    ]

    return SaleTransactionRead(
        transaction_id=transaction_id,
        sale_date=sale_date,
        item_count=len(items),
        total_amount=total_amount,
        currency=currency,
        status=status,
        items=item_reads,
        created_at=created_at,
    )


async def list_transactions(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """List sales grouped by transaction_id (most recent first)."""

    count_result = await db.execute(
        select(func.count(func.distinct(Sale.transaction_id))).where(
            Sale.transaction_id.isnot(None)
        )
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    txn_id_rows = await db.execute(
        select(Sale.transaction_id)
        .where(Sale.transaction_id.isnot(None))
        .group_by(Sale.transaction_id)
        .order_by(func.min(Sale.created_at).desc())
        .offset(offset)
        .limit(page_size)
    )
    txn_ids = [row[0] for row in txn_id_rows.all()]

    transactions = []
    for txn_id in txn_ids:
        result = await db.execute(select(Sale).where(Sale.transaction_id == txn_id))
        items = list(result.scalars().all())
        transactions.append(_build_transaction_read(txn_id, items))

    return transactions, total


async def get_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
) -> "SaleTransactionRead":
    """Get all Sale records for a given transaction_id."""
    result = await db.execute(select(Sale).where(Sale.transaction_id == transaction_id))
    items = list(result.scalars().all())
    if not items:
        raise SaleNotFoundError(transaction_id)
    return _build_transaction_read(transaction_id, items)
