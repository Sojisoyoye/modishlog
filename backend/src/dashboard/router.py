"""Dashboard domain — KPI summary router."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.core.database import get_db
from src.dashboard.schemas import DashboardSummaryResponse
from src.dashboard.service import get_dashboard_summary

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    location_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummaryResponse:
    """Return aggregated KPI totals for the authenticated user's business."""
    return await get_dashboard_summary(
        db=db,
        user_id=current_user.id,
        location_id=location_id,
        date_from=date_from,
        date_to=date_to,
    )
