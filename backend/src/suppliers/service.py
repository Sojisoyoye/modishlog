"""Suppliers domain business logic."""

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.suppliers.exceptions import SupplierNotFoundError
from src.suppliers.models import Supplier
from src.suppliers.schemas import (
    ActivityEntry,
    LedgerEntry,
    StockReportItem,
    SupplierCreate,
    SupplierUpdate,
)

logger = structlog.get_logger()


async def create_supplier(
    db: AsyncSession,
    data: SupplierCreate,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> Supplier:
    supplier = Supplier(
        name=data.name,
        contact_person=data.contact_person,
        email=data.email,
        mobile=data.mobile,
        alternate_number=data.alternate_number,
        tax_number=data.tax_number,
        address_line_1=data.address_line_1,
        address_line_2=data.address_line_2,
        city=data.city,
        state=data.state,
        country=data.country,
        zip_code=data.zip_code,
        pay_term_number=data.pay_term_number,
        pay_term_type=data.pay_term_type,
        opening_balance=data.opening_balance,
        notes=data.notes,
        is_active=True,
        created_by=user_id,
        business_id=business_id,
    )
    db.add(supplier)
    await db.flush()
    await logger.ainfo(
        "supplier_created", supplier_id=str(supplier.id), name=supplier.name
    )
    return supplier


async def get_supplier(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    business_id: uuid.UUID,
) -> Supplier:
    result = await db.execute(
        select(Supplier)
        .where(Supplier.id == supplier_id, Supplier.business_id == business_id)
        .options(selectinload(Supplier.products))
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise SupplierNotFoundError(supplier_id)
    return supplier


async def list_suppliers(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    search: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Supplier], int]:
    query = select(Supplier).where(Supplier.business_id == business_id)
    count_query = select(func.count()).select_from(Supplier).where(
        Supplier.business_id == business_id
    )

    if search:
        like = f"%{search}%"
        query = query.where(Supplier.name.ilike(like))
        count_query = count_query.where(Supplier.name.ilike(like))

    if active_only:
        query = query.where(Supplier.is_active.is_(True))
        count_query = count_query.where(Supplier.is_active.is_(True))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Supplier.name.asc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def update_supplier(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    data: SupplierUpdate,
    business_id: uuid.UUID,
) -> Supplier:
    supplier = await get_supplier(db, supplier_id, business_id)
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(supplier, field, value)
    await db.flush()
    await logger.ainfo("supplier_updated", supplier_id=str(supplier_id))
    return supplier


async def get_supplier_purchases(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list:
    """Return purchase orders linked to this supplier, scoped to the business."""
    from src.orders.models import PurchaseOrder

    result = await db.execute(
        select(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(
            PurchaseOrder.supplier_id == supplier_id,
            Supplier.business_id == business_id,
        )
        .options(selectinload(PurchaseOrder.line_items))
        .order_by(PurchaseOrder.created_at.desc())
    )
    return list(result.scalars().all())


async def get_supplier_ledger(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list[LedgerEntry]:
    """Build a running debit/credit ledger for the supplier from orders and payments."""
    from src.orders.models import PurchaseOrder

    orders_result = await db.execute(
        select(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(
            PurchaseOrder.supplier_id == supplier_id,
            Supplier.business_id == business_id,
        )
        .options(selectinload(PurchaseOrder.payments))
        .order_by(PurchaseOrder.created_at.asc())
    )
    orders = list(orders_result.scalars().all())

    entries: list[LedgerEntry] = []
    running_balance = Decimal("0")

    # Opening balance
    supplier_result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.business_id == business_id
        )
    )
    supplier = supplier_result.scalar_one_or_none()
    if supplier and supplier.opening_balance:
        running_balance = supplier.opening_balance
        entries.append(
            LedgerEntry(
                date=supplier.created_at,
                description="Opening balance",
                debit=Decimal("0"),
                credit=running_balance,
                balance=running_balance,
            )
        )

    for order in orders:
        amount = order.total_amount
        running_balance += amount
        entries.append(
            LedgerEntry(
                date=order.created_at,
                description=f"Purchase #{order.order_number}",
                debit=amount,
                credit=Decimal("0"),
                balance=running_balance,
            )
        )
        for payment in order.payments:
            paid = payment.amount
            running_balance -= paid
            entries.append(
                LedgerEntry(
                    date=payment.created_at,
                    description=f"Payment for #{order.order_number}",
                    debit=Decimal("0"),
                    credit=paid,
                    balance=running_balance,
                )
            )

    return entries


async def get_supplier_stock_report(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list[StockReportItem]:
    """Products with current stock that were sourced from this supplier."""
    from src.inventory.models import InventoryLevel
    from src.orders.models import OrderLineItem, PurchaseOrder
    from src.products.models import Product

    # A product can have more than one InventoryLevel row (one per variant,
    # plus an optional variant_id=NULL aggregate row) — sum them per product
    # so this per-product report doesn't list the same SKU multiple times
    # with different quantities.
    inventory_subq = (
        select(
            InventoryLevel.product_id,
            func.sum(InventoryLevel.quantity_on_hand).label("quantity_on_hand"),
        )
        .group_by(InventoryLevel.product_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.unit_cost,
            inventory_subq.c.quantity_on_hand,
        )
        .join(OrderLineItem, OrderLineItem.product_id == Product.id)
        .join(PurchaseOrder, PurchaseOrder.id == OrderLineItem.order_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .join(inventory_subq, inventory_subq.c.product_id == Product.id)
        .where(
            PurchaseOrder.supplier_id == supplier_id,
            Supplier.business_id == business_id,
        )
        .distinct()
    )
    rows = result.all()
    items = []
    for row in rows:
        unit_cost = Decimal(str(row.unit_cost or 0))
        qty = row.quantity_on_hand or 0
        items.append(
            StockReportItem(
                product_id=row.id,
                sku=row.sku,
                product_name=row.name,
                quantity_on_hand=qty,
                unit_cost=unit_cost,
                stock_value=unit_cost * qty,
            )
        )
    return items


async def get_supplier_activities(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list[ActivityEntry]:
    """Timeline of all activity for a supplier — purchases and payments."""
    from src.orders.models import PurchaseOrder

    orders_result = await db.execute(
        select(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(
            PurchaseOrder.supplier_id == supplier_id,
            Supplier.business_id == business_id,
        )
        .options(selectinload(PurchaseOrder.payments))
        .order_by(PurchaseOrder.created_at.desc())
    )
    orders = list(orders_result.scalars().all())

    activities: list[ActivityEntry] = []
    for order in orders:
        activities.append(
            ActivityEntry(
                timestamp=order.created_at,
                event_type="purchase",
                description=f"Purchase order #{order.order_number} created",
                amount=order.total_amount,
                reference=order.order_number,
            )
        )
        for payment in order.payments:
            activities.append(
                ActivityEntry(
                    timestamp=payment.created_at,
                    event_type="payment",
                    description=f"Payment recorded for #{order.order_number}",
                    amount=payment.amount,
                    reference=payment.reference,
                )
            )

    activities.sort(key=lambda e: e.timestamp, reverse=True)
    return activities
