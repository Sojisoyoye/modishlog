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
from src.orders.models import OrderLineItem, PurchaseOrder
from src.products.models import Product
from src.sales.exceptions import (
    BulkUploadJobNotFoundError,
    InvalidCSVFormatError,
    SaleAlreadyVoidedError,
    SaleNotFoundError,
    SalePermissionError,
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
    SaleTransactionUpdate,
    SaleUpdate,
)
from src.inventory.models import InventoryBatch

logger = structlog.get_logger()

REQUIRED_CSV_HEADERS = {"product_id", "quantity", "unit_price", "sale_date", "channel"}


# ---------------------------------------------------------------------------
# Lot-level FIFO deduction helper
# ---------------------------------------------------------------------------


async def _deduct_lot_units(
    db: AsyncSession,
    product_id: uuid.UUID,
    quantity: Decimal,
) -> None:
    """Deduct quantity from active order lots FIFO (oldest order_date first)."""
    result = await db.execute(
        select(OrderLineItem)
        .join(PurchaseOrder, OrderLineItem.order_id == PurchaseOrder.id)
        .where(
            OrderLineItem.product_id == product_id,
            OrderLineItem.units_remaining > 0,
        )
        .order_by(PurchaseOrder.order_date.asc(), PurchaseOrder.created_at.asc())
    )
    lots = result.scalars().all()

    remaining = quantity
    deducted_any = False
    for lot in lots:
        if remaining <= 0:
            break
        deduct = min(lot.units_remaining, remaining)
        lot.units_remaining -= deduct
        remaining -= deduct
        deducted_any = True

    if deducted_any:
        await db.flush()

    if remaining > 0:
        await logger.awarning(
            "lot_units_not_fully_covered",
            product_id=str(product_id),
            uncovered_quantity=str(remaining),
        )


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

    # If customer_id is provided, look up and denormalize name/contact
    resolved_customer_name = data.customer_name
    resolved_contact_number = data.contact_number
    if data.customer_id is not None:
        from src.customers.models import Customer

        customer_result = await db.execute(
            select(Customer).where(Customer.id == data.customer_id)
        )
        customer_obj = customer_result.scalar_one_or_none()
        if customer_obj:
            resolved_customer_name = customer_obj.name
            resolved_contact_number = customer_obj.contact_number

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
        customer_id=data.customer_id,
        customer_name=resolved_customer_name,
        contact_number=resolved_contact_number,
        payment_method=data.payment_method,
        payment_status=data.payment_status or "paid",
        payment_amount=data.payment_amount,
        payment_date=data.payment_date,
        notes=data.notes,
        location_id=data.location_id,
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

    # Lot-level FIFO deduction: deplete units_remaining on delivered order lots
    await _deduct_lot_units(db, data.product_id, Decimal(str(data.quantity)))

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

    # Recalculate total if quantity, price, or discount changed
    if "quantity" in update_fields or "unit_price" in update_fields or "discount_amount" in update_fields:
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


async def update_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
    data: SaleTransactionUpdate,
    user_id: uuid.UUID,
    is_admin: bool = False,
) -> list[Sale]:
    """Update transaction-level fields (payment_method, payment_status, notes) across all Sale records in a group."""
    result = await db.execute(
        select(Sale).where(Sale.transaction_id == transaction_id).order_by(Sale.created_at)
    )
    sales = list(result.scalars().all())

    if not sales:
        raise SaleNotFoundError(transaction_id)

    owner_id: uuid.UUID = sales[0].recorded_by
    if not is_admin and owner_id != user_id:
        raise SalePermissionError(transaction_id)

    active_sales = [s for s in sales if s.status != SaleStatus.VOIDED]
    if not active_sales:
        raise SaleAlreadyVoidedError(transaction_id)

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        return sales

    for sale in active_sales:
        field_changes = {}
        for field, value in update_fields.items():
            old_value = getattr(sale, field)
            if old_value != value:
                field_changes[field] = {
                    "old": str(old_value) if old_value is not None else None,
                    "new": str(value) if value is not None else None,
                }
                setattr(sale, field, value)
        if field_changes:
            audit = SaleAuditEntry(
                sale_id=sale.id,
                action="transaction_updated",
                field_changes=field_changes,
                performed_by=user_id,
                reason=None,
                created_at=datetime.now(timezone.utc),
            )
            db.add(audit)

    await db.flush()
    await logger.ainfo("transaction_updated", transaction_id=str(transaction_id))
    return sales


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

    active_items = [s for s in items if s.status != SaleStatus.VOIDED]
    total_amount = sum((s.total_amount for s in active_items), Decimal("0"))
    sale_date = items[0].sale_date if items else date.today()
    created_at = (
        min(s.created_at for s in items) if items else datetime.now(timezone.utc)
    )
    currency = items[0].currency if items else "NGN"

    # Use customer/payment info from the first non-voided item (consistent per txn)
    first = next(iter(active_items), items[0] if items else None)
    customer_id = first.customer_id if first else None
    customer_name = first.customer_name if first else None
    contact_number = first.contact_number if first else None
    payment_method = first.payment_method if first else None
    payment_status = first.payment_status if first else None
    payment_amount = first.payment_amount if first else None
    payment_date = first.payment_date if first else None
    notes = first.notes if first else None

    # total_paid: use the recorded payment_amount when available;
    # fall back to inferring from payment_status (paid → full amount, else → 0).
    if payment_amount is not None:
        total_paid = payment_amount
    elif payment_status == "paid":
        total_paid = total_amount
    else:
        total_paid = Decimal("0")
    sale_due = max(Decimal("0"), total_amount - total_paid)

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
            status=s.status.value,
            customer_name=s.customer_name,
            contact_number=s.contact_number,
            payment_method=s.payment_method,
            notes=s.notes,
        )
        for s in items
    ]

    return SaleTransactionRead(
        transaction_id=transaction_id,
        sale_date=sale_date,
        item_count=len(active_items),
        total_amount=total_amount,
        total_paid=total_paid,
        sale_due=sale_due,
        currency=currency,
        status=status,
        customer_id=customer_id,
        customer_name=customer_name,
        contact_number=contact_number,
        payment_method=payment_method,
        payment_status=payment_status,
        payment_amount=payment_amount,
        payment_date=payment_date,
        notes=notes,
        items=item_reads,
        created_at=created_at,
    )


async def list_transactions(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    location_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    customer_name: str | None = None,
    payment_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list, int]:
    """List sales grouped by transaction_id (most recent first)."""

    base_where = [Sale.transaction_id.isnot(None)]
    if location_id is not None:
        base_where.append(Sale.location_id == location_id)
    if customer_id is not None:
        base_where.append(Sale.customer_id == customer_id)
    if customer_name is not None:
        escaped = customer_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base_where.append(Sale.customer_name.ilike(f"%{escaped}%"))
    if payment_status is not None:
        base_where.append(Sale.payment_status == payment_status)
    if date_from is not None:
        base_where.append(Sale.sale_date >= date_from)
    if date_to is not None:
        base_where.append(Sale.sale_date <= date_to)

    count_result = await db.execute(
        select(func.count(func.distinct(Sale.transaction_id))).where(*base_where)
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    txn_id_rows = await db.execute(
        select(Sale.transaction_id)
        .where(*base_where)
        .group_by(Sale.transaction_id)
        .order_by(func.min(Sale.created_at).desc())
        .offset(offset)
        .limit(page_size)
    )
    txn_ids = [row[0] for row in txn_id_rows.all()]

    if not txn_ids:
        return [], total

    # Single IN query instead of one query per transaction (eliminates N+1)
    bulk_result = await db.execute(
        select(Sale)
        .where(Sale.transaction_id.in_(txn_ids))
        .order_by(Sale.transaction_id, Sale.created_at)
    )
    all_items = bulk_result.scalars().all()

    # Group by transaction_id in Python
    txn_map: dict[uuid.UUID, list[Sale]] = {}
    for item in all_items:
        txn_map.setdefault(item.transaction_id, []).append(item)

    # Preserve the page ordering (min created_at desc) from txn_ids
    transactions = [
        _build_transaction_read(txn_id, txn_map.get(txn_id, []))
        for txn_id in txn_ids
    ]
    return transactions, total


async def get_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
) -> "SaleTransactionRead":
    """Get all Sale records for a given transaction_id."""
    result = await db.execute(
        select(Sale).where(Sale.transaction_id == transaction_id).order_by(Sale.created_at)
    )
    items = list(result.scalars().all())
    if not items:
        raise SaleNotFoundError(transaction_id)
    return _build_transaction_read(transaction_id, items)
