"""Suppliers API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.suppliers.exceptions import SupplierNotFoundError
from src.suppliers.schemas import (
    ActivityEntry,
    LedgerEntry,
    StockReportItem,
    SupplierCreate,
    SupplierListResponse,
    SupplierRead,
    SupplierUpdate,
)
from src.suppliers.service import (
    create_supplier,
    get_supplier,
    get_supplier_activities,
    get_supplier_ledger,
    get_supplier_purchases,
    get_supplier_stock_report,
    list_suppliers,
    update_supplier,
)

router = APIRouter()


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier_endpoint(
    body: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await create_supplier(db, body, current_user.id)


@router.get("", response_model=SupplierListResponse)
async def list_suppliers_endpoint(
    search: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    items, total = await list_suppliers(
        db, search=search, active_only=active_only, page=page, page_size=page_size
    )
    return SupplierListResponse(items=items, total=total)


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier_endpoint(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return await get_supplier(db, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{supplier_id}", response_model=SupplierRead)
async def update_supplier_endpoint(
    supplier_id: uuid.UUID,
    body: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return await update_supplier(db, supplier_id, body)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{supplier_id}/purchases")
async def get_supplier_purchases_endpoint(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        await get_supplier(db, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    purchases = await get_supplier_purchases(db, supplier_id)
    return {"items": purchases, "total": len(purchases)}


@router.get("/{supplier_id}/ledger", response_model=list[LedgerEntry])
async def get_supplier_ledger_endpoint(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        await get_supplier(db, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return await get_supplier_ledger(db, supplier_id)


@router.get("/{supplier_id}/stock-report", response_model=list[StockReportItem])
async def get_supplier_stock_report_endpoint(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        await get_supplier(db, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return await get_supplier_stock_report(db, supplier_id)


@router.get("/{supplier_id}/activities", response_model=list[ActivityEntry])
async def get_supplier_activities_endpoint(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        await get_supplier(db, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return await get_supplier_activities(db, supplier_id)
