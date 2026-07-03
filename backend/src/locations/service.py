"""Locations domain business logic."""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.locations.exceptions import DuplicateLocationCodeError, LocationNotFoundError
from src.locations.models import BusinessLocation
from src.locations.schemas import LocationCreate, LocationUpdate

logger = structlog.get_logger()


async def create_location(
    db: AsyncSession,
    data: LocationCreate,
    user_id: uuid.UUID,
    *,
    business_id: uuid.UUID,
) -> BusinessLocation:
    """Create a new business location record scoped to a business."""
    # Check for duplicate location_code scoped to this business
    existing_result = await db.execute(
        select(BusinessLocation).where(
            BusinessLocation.location_code == data.location_code,
            BusinessLocation.business_id == business_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise DuplicateLocationCodeError(data.location_code)

    location = BusinessLocation(
        name=data.name,
        location_code=data.location_code,
        mobile=data.mobile,
        alternate_number=data.alternate_number,
        email=data.email,
        website=data.website,
        landmark=data.landmark,
        city=data.city,
        state=data.state,
        country=data.country,
        zip_code=data.zip_code,
        timezone=data.timezone,
        currency=data.currency,
        tax_number=data.tax_number,
        location_type=data.location_type,
        created_by=user_id,
        business_id=business_id,
    )
    db.add(location)
    await db.flush()
    await logger.ainfo(
        "location_created",
        location_id=str(location.id),
        name=location.name,
        code=location.location_code,
        business_id=str(business_id),
    )
    return location


async def get_location(
    db: AsyncSession,
    location_id: uuid.UUID,
    *,
    business_id: uuid.UUID,
) -> BusinessLocation:
    """Fetch a single location by ID, scoped to the given business."""
    result = await db.execute(
        select(BusinessLocation).where(
            BusinessLocation.id == location_id,
            BusinessLocation.business_id == business_id,
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise LocationNotFoundError(location_id)
    return location


async def list_locations(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    search: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[BusinessLocation], int]:
    """List locations for a business with optional search and active filter."""
    query = select(BusinessLocation).where(
        BusinessLocation.business_id == business_id
    )
    count_query = select(func.count()).select_from(BusinessLocation).where(
        BusinessLocation.business_id == business_id
    )

    if search:
        like = f"%{search}%"
        query = query.where(BusinessLocation.name.ilike(like))
        count_query = count_query.where(BusinessLocation.name.ilike(like))

    if active_only:
        query = query.where(BusinessLocation.is_active.is_(True))
        count_query = count_query.where(BusinessLocation.is_active.is_(True))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(BusinessLocation.name.asc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_location(
    db: AsyncSession,
    location_id: uuid.UUID,
    data: LocationUpdate,
    *,
    business_id: uuid.UUID,
) -> BusinessLocation:
    """Update a business location record, scoped to the given business."""
    location = await get_location(db, location_id, business_id=business_id)
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(location, field, value)
    await db.flush()
    await logger.ainfo(
        "location_updated",
        location_id=str(location_id),
        business_id=str(business_id),
    )
    return location
