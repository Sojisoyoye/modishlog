"""Settings API routes — thin layer, all logic in service.py."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.settings import service
from src.settings.schemas import (
    ApiKeyStatus,
    ApiKeyUpsert,
    FiscalYearRead,
    FiscalYearUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.post("/api-key", status_code=status.HTTP_200_OK, response_model=ApiKeyStatus)
async def save_api_key(
    body: ApiKeyUpsert,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyStatus:
    """Store an API key encrypted at rest. Never returns the plaintext value."""
    await service.upsert_api_key(db, current_user.id, body.key_name, body.key_value)
    return ApiKeyStatus(key_name=body.key_name, is_configured=True)


@router.get("/api-key/{key_name}", response_model=ApiKeyStatus)
async def get_api_key_status(
    key_name: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyStatus:
    """Return whether a named API key has been configured — never the value itself."""
    configured = await service.get_api_key_status(db, current_user.id, key_name)
    return ApiKeyStatus(key_name=key_name, is_configured=configured)


@router.get("/fiscal-year", response_model=FiscalYearRead)
async def get_fiscal_year(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FiscalYearRead:
    """Return the user's configured fiscal year start (month and day), or nulls if not set."""
    return await service.get_fiscal_year_start(db, current_user.id)


@router.put("/fiscal-year", response_model=FiscalYearRead)
async def put_fiscal_year(
    body: FiscalYearUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FiscalYearRead:
    """Set or clear the user's fiscal year start month and day."""
    return await service.update_fiscal_year_start(
        db, current_user.id, body.fiscal_year_start_month, body.fiscal_year_start_day
    )
