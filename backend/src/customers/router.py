"""Customers API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.customers.exceptions import CustomerNotFoundError
from src.customers.schemas import (
    CustomerCreate,
    CustomerListResponse,
    CustomerRead,
    CustomerUpdate,
)
from src.customers.service import (
    create_customer,
    get_customer,
    list_customers,
    update_customer,
)

router = APIRouter()


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer_endpoint(
    body: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new customer."""
    customer = await create_customer(db, body, current_user.id)
    return customer


@router.get("", response_model=CustomerListResponse)
async def list_customers_endpoint(
    search: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List customers, optionally filtered by name search and active status."""
    items, total = await list_customers(
        db, search=search, is_active=is_active, page=page, page_size=page_size
    )
    return CustomerListResponse(items=items, total=total)


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer_endpoint(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single customer by ID."""
    try:
        return await get_customer(db, customer_id)
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{customer_id}", response_model=CustomerRead)
async def update_customer_endpoint(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a customer record."""
    try:
        return await update_customer(db, customer_id, body)
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
