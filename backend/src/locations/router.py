"""Locations API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.locations.exceptions import DuplicateLocationCodeError, LocationNotFoundError
from src.locations.schemas import (
    LocationCreate,
    LocationListResponse,
    LocationRead,
    LocationUpdate,
)
from src.locations.service import (
    create_location,
    get_location,
    list_locations,
    update_location,
)

router = APIRouter()


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location_endpoint(
    body: LocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new business location."""
    try:
        location = await create_location(db, body, current_user.id)
        return location
    except DuplicateLocationCodeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("", response_model=LocationListResponse)
async def list_locations_endpoint(
    search: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List business locations, optionally filtered by name search."""
    items, total = await list_locations(
        db, user_id=current_user.id, search=search, active_only=active_only, page=page, page_size=page_size
    )
    return LocationListResponse(items=items, total=total)


@router.get("/{location_id}", response_model=LocationRead)
async def get_location_endpoint(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single business location by ID."""
    try:
        return await get_location(db, location_id)
    except LocationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{location_id}", response_model=LocationRead)
async def update_location_endpoint(
    location_id: uuid.UUID,
    body: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a business location record."""
    try:
        return await update_location(db, location_id, body)
    except LocationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
