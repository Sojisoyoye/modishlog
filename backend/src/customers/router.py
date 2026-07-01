"""Customers API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.customers.exceptions import CustomerHasLinkedSalesError, CustomerNotFoundError
from src.customers.schemas import (
    CustomerActivityEntry,
    CustomerCreate,
    CustomerLedgerEntry,
    CustomerListResponse,
    CustomerRead,
    CustomerUpdate,
)
from src.customers.service import (
    create_customer,
    deactivate_customer,
    export_customers_csv,
    get_customer,
    get_customer_activities,
    get_customer_ledger,
    get_customer_sales,
    list_customers,
    update_customer,
)
from src.sales.schemas import SaleListResponse, SaleRead

router = APIRouter()


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer_endpoint(
    body: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new customer."""
    return await create_customer(db, body, current_user.id)


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


# Static route — must be before /{customer_id}
@router.get("/export.csv", response_class=PlainTextResponse)
async def export_customers_endpoint(
    search: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Export the customer list as a CSV file."""
    csv_text = await export_customers_csv(db, search=search, is_active=is_active)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customers.csv"},
    )


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


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_endpoint(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a customer (sets is_active=False).

    Returns 409 Conflict if the customer has linked sales.
    """
    try:
        await deactivate_customer(db, customer_id)
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CustomerHasLinkedSalesError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/{customer_id}/sales", response_model=SaleListResponse)
async def get_customer_sales_endpoint(
    customer_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Paginated list of sales for a customer."""
    items, total = await get_customer_sales(
        db, customer_id, page=page, page_size=page_size
    )
    return SaleListResponse(
        items=[SaleRead.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{customer_id}/ledger", response_model=list[CustomerLedgerEntry])
async def get_customer_ledger_endpoint(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Running balance ledger for a customer."""
    try:
        return await get_customer_ledger(db, customer_id)
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{customer_id}/activities", response_model=list[CustomerActivityEntry])
async def get_customer_activities_endpoint(
    customer_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Recent activity feed for a customer."""
    return await get_customer_activities(db, customer_id, limit=limit)
