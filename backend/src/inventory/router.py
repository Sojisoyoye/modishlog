"""Inventory API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.inventory.schemas import (
    DepletionForecastRead,
    InventoryLevelRead,
    StockAdjustmentRequest,
    StockMovementRead,
)
from src.inventory.service import (
    adjust_stock,
    calculate_depletion_forecast,
    get_inventory_level,
    get_stock_movements,
    list_inventory_levels,
)

router = APIRouter()


@router.get("", response_model=list[InventoryLevelRead])
async def list_inventory_endpoint(
    low_stock_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List all inventory levels."""
    return await list_inventory_levels(db, low_stock_only=low_stock_only)


@router.get("/low-stock", response_model=list[InventoryLevelRead])
async def low_stock_endpoint(db: AsyncSession = Depends(get_db)):
    """List products at or below their low-stock threshold."""
    return await list_inventory_levels(db, low_stock_only=True)


@router.get("/{product_id}", response_model=InventoryLevelRead)
async def get_inventory_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get inventory level for a specific product."""
    try:
        return await get_inventory_level(db, product_id)
    except ProductStockNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{product_id}/adjust", response_model=InventoryLevelRead)
async def adjust_stock_endpoint(
    product_id: uuid.UUID,
    body: StockAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Manually adjust stock for a product."""
    try:
        return await adjust_stock(
            db,
            product_id=product_id,
            quantity_change=body.quantity_change,
            movement_type=body.movement_type,
            reason=body.reason,
            user_id=current_user.id,
        )
    except ProductStockNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStockAdjustmentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{product_id}/movements", response_model=list[StockMovementRead])
async def get_movements_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get stock movement history for a product."""
    return await get_stock_movements(db, product_id)


@router.get("/{product_id}/depletion-forecast", response_model=DepletionForecastRead)
async def depletion_forecast_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get predicted stock-out date for a product."""
    try:
        return await calculate_depletion_forecast(db, product_id)
    except ProductStockNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
