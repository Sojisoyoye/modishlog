"""Dashboard domain — KPI summary router."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user, get_current_business_id
from src.auth.models import User
from src.core.database import get_db
from src.dashboard.schemas import DashboardSummaryResponse
from src.dashboard.service import get_dashboard_summary
from src.locations.models import BusinessLocation

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    response: Response,
    location_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
) -> DashboardSummaryResponse:
    """Return aggregated KPI totals for the authenticated user's business."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422, detail="date_from must not be after date_to"
        )
    if location_id is not None:
        # Verify the location belongs to the same business by checking that its
        # creator is a member of the current user's business.
        owned = await db.scalar(
            select(BusinessLocation.id)
            .join(User, User.id == BusinessLocation.created_by)
            .where(
                BusinessLocation.id == location_id,
                BusinessLocation.business_id == business_id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Location not found")
    response.headers["Cache-Control"] = "no-store, private"
    return await get_dashboard_summary(
        db=db,
        business_id=business_id,
        location_id=location_id,
        date_from=date_from,
        date_to=date_to,
    )
