"""Stock count API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.stockcount.exceptions import StockCountFinalizedError, StockCountNotFoundError
from src.stockcount.schemas import (
    StockCountCreate,
    StockCountItemRead,
    StockCountItemUpdate,
    StockCountListRead,
    StockCountRead,
)
from src.stockcount.service import (
    create_stock_count,
    finalize_stock_count,
    get_stock_count,
    list_stock_counts,
    update_count_item,
)

router = APIRouter()


# Static routes before parameterised routes


@router.get("/", response_model=list[StockCountListRead])
async def list_stock_counts_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all stock count sessions, newest first."""
    counts = await list_stock_counts(db)
    return [
        StockCountListRead(
            id=sc.id,
            count_date=sc.count_date,
            count_type=sc.count_type.value,
            status=sc.status.value,
            notes=sc.notes,
            created_at=sc.created_at,
            finalized_at=sc.finalized_at,
            item_count=len(sc.items),
        )
        for sc in counts
    ]


@router.post("/", response_model=StockCountRead, status_code=status.HTTP_201_CREATED)
async def create_stock_count_endpoint(
    body: StockCountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new DRAFT stock count session."""
    sc = await create_stock_count(
        db, body.count_date, body.count_type, body.notes, current_user.id
    )
    sc_with_items = await get_stock_count(db, sc.id)
    return sc_with_items


@router.get("/{stock_count_id}", response_model=StockCountRead)
async def get_stock_count_endpoint(
    stock_count_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return a stock count session with all its items."""
    try:
        return await get_stock_count(db, stock_count_id)
    except StockCountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{stock_count_id}/items/{item_id}", response_model=StockCountItemRead)
async def update_item_endpoint(
    stock_count_id: uuid.UUID,
    item_id: uuid.UUID,
    body: StockCountItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update the counted_quantity for one item. Only allowed while DRAFT."""
    try:
        return await update_count_item(
            db, stock_count_id, item_id, body.counted_quantity
        )
    except StockCountFinalizedError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except StockCountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{stock_count_id}/finalize", response_model=StockCountRead)
async def finalize_endpoint(
    stock_count_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Snapshot system stock into items and lock the session as FINALIZED."""
    try:
        return await finalize_stock_count(db, stock_count_id)
    except StockCountFinalizedError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except StockCountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
