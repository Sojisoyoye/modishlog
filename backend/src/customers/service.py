"""Customers domain business logic."""

import csv
import io
import uuid
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.exceptions import CustomerHasLinkedSalesError, CustomerNotFoundError
from src.customers.models import Customer
from src.customers.schemas import (
    CustomerActivityEntry,
    CustomerCreate,
    CustomerLedgerEntry,
    CustomerUpdate,
)

logger = structlog.get_logger()


async def create_customer(
    db: AsyncSession,
    data: CustomerCreate,
    user_id: uuid.UUID,
) -> Customer:
    """Create a new customer record."""
    customer = Customer(
        name=data.name,
        contact_number=data.contact_number,
        alternate_number=data.alternate_number,
        email=data.email,
        address=data.address,
        city=data.city,
        state=data.state,
        country=data.country,
        zip_code=data.zip_code,
        tax_number=data.tax_number,
        pay_term_number=data.pay_term_number,
        pay_term_type=data.pay_term_type,
        opening_balance=data.opening_balance,
        credit_limit=data.credit_limit,
        is_active=data.is_active,
        customer_group=data.customer_group,
        notes=data.notes,
        created_by=user_id,
    )
    db.add(customer)
    await db.flush()
    await logger.ainfo(
        "customer_created", customer_id=str(customer.id), name=customer.name
    )
    return customer


async def list_customers(
    db: AsyncSession,
    *,
    search: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Customer], int]:
    """List customers with optional name search and active filter."""
    query = select(Customer)
    count_query = select(func.count()).select_from(Customer)

    if search:
        like = f"%{search}%"
        query = query.where(Customer.name.ilike(like))
        count_query = count_query.where(Customer.name.ilike(like))

    if is_active is not None:
        query = query.where(Customer.is_active == is_active)
        count_query = count_query.where(Customer.is_active == is_active)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Customer.name.asc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_customer(
    db: AsyncSession,
    customer_id: uuid.UUID,
) -> Customer:
    """Fetch a single customer by ID."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise CustomerNotFoundError(customer_id)
    return customer


async def update_customer(
    db: AsyncSession,
    customer_id: uuid.UUID,
    data: CustomerUpdate,
) -> Customer:
    """Update a customer record."""
    customer = await get_customer(db, customer_id)
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(customer, field, value)
    await db.flush()
    await logger.ainfo("customer_updated", customer_id=str(customer_id))
    return customer


async def deactivate_customer(
    db: AsyncSession,
    customer_id: uuid.UUID,
) -> Customer:
    """Soft-delete a customer (set is_active=False).

    Raises CustomerHasLinkedSalesError if the customer has any linked sales.
    """
    from src.sales.models import Sale

    customer = await get_customer(db, customer_id)

    count_result = await db.execute(
        select(func.count()).select_from(Sale).where(Sale.customer_id == customer_id)
    )
    if (count_result.scalar() or 0) > 0:
        raise CustomerHasLinkedSalesError(customer_id)

    customer.is_active = False
    await db.flush()
    await logger.ainfo("customer_deactivated", customer_id=str(customer_id))
    return customer


async def get_customer_sales(
    db: AsyncSession,
    customer_id: uuid.UUID,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list, int]:
    """Paginated list of sales for a customer."""
    from src.sales.models import Sale

    count_result = await db.execute(
        select(func.count()).select_from(Sale).where(Sale.customer_id == customer_id)
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Sale)
        .where(Sale.customer_id == customer_id)
        .order_by(Sale.sale_date.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return items, total


async def get_customer_ledger(
    db: AsyncSession,
    customer_id: uuid.UUID,
) -> list[CustomerLedgerEntry]:
    """Build a running debit ledger for a customer from their sales."""
    from src.sales.models import Sale

    customer = await get_customer(db, customer_id)

    sales_result = await db.execute(
        select(Sale)
        .where(Sale.customer_id == customer_id)
        .order_by(Sale.sale_date.asc())
    )
    sales = list(sales_result.scalars().all())

    entries: list[CustomerLedgerEntry] = []
    running_balance = Decimal("0")

    if customer.opening_balance:
        running_balance = customer.opening_balance
        entries.append(
            CustomerLedgerEntry(
                date=customer.created_at,
                description="Opening balance",
                debit=running_balance,
                credit=Decimal("0"),
                balance=running_balance,
            )
        )

    for sale in sales:
        amount = sale.total_amount
        running_balance += amount
        ref = sale.invoice_number or str(sale.id)[:8]
        entries.append(
            CustomerLedgerEntry(
                date=sale.created_at,
                description=f"Sale {ref}",
                debit=amount,
                credit=Decimal("0"),
                balance=running_balance,
            )
        )

    return entries


async def get_customer_activities(
    db: AsyncSession,
    customer_id: uuid.UUID,
    limit: int = 20,
) -> list[CustomerActivityEntry]:
    """Recent activity feed for a customer — sales events."""
    from src.sales.models import Sale

    result = await db.execute(
        select(Sale)
        .where(Sale.customer_id == customer_id)
        .order_by(Sale.created_at.desc())
        .limit(limit)
    )
    sales = list(result.scalars().all())

    return [
        CustomerActivityEntry(
            timestamp=sale.created_at,
            event_type="sale",
            description=f"Sale recorded — {sale.invoice_number or str(sale.id)[:8]}",
            amount=sale.total_amount,
            reference=sale.invoice_number,
        )
        for sale in sales
    ]


async def export_customers_csv(
    db: AsyncSession,
    search: str | None = None,
    is_active: bool | None = None,
) -> str:
    """Export customer list as a CSV string."""
    items, _ = await list_customers(
        db, search=search, is_active=is_active, page=1, page_size=10_000
    )
    output = io.StringIO()
    fieldnames = [
        "name",
        "email",
        "contact_number",
        "city",
        "country",
        "opening_balance",
        "credit_limit",
        "is_active",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for c in items:
        writer.writerow(
            {
                "name": c.name,
                "email": c.email or "",
                "contact_number": c.contact_number or "",
                "city": c.city or "",
                "country": c.country or "",
                "opening_balance": str(c.opening_balance),
                "credit_limit": str(c.credit_limit)
                if c.credit_limit is not None
                else "",
                "is_active": "Yes" if c.is_active else "No",
            }
        )
    return output.getvalue()
