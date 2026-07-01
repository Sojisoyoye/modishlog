"""Customers domain business logic."""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.exceptions import CustomerNotFoundError
from src.customers.models import Customer
from src.customers.schemas import CustomerCreate, CustomerUpdate

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
