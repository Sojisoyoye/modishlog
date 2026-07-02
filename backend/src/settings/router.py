"""Settings API routes — thin layer, all logic in service.py."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.settings import service
from src.settings.schemas import (
    ApiKeyStatus,
    ApiKeyTestResult,
    ApiKeyUpsert,
    AppSettingRead,
    AppSettingWrite,
    BusinessProfileRead,
    BusinessProfileUpdate,
    FiscalYearRead,
    FiscalYearUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/business-profile", response_model=BusinessProfileRead)
async def get_business_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessProfileRead:
    profile = await service.get_business_profile(db)
    return BusinessProfileRead.model_validate(profile)


@router.put("/business-profile", response_model=BusinessProfileRead)
async def update_business_profile(
    body: BusinessProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessProfileRead:
    profile = await service.update_business_profile(db, body, current_user.id)
    return BusinessProfileRead.model_validate(profile)


@router.get("/app", response_model=dict)
async def get_app_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_app_settings(db)


@router.put("/app/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def update_app_setting(
    key: str,
    body: AppSettingWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.update_app_setting(db, key, body.value or "", current_user.id)


@router.post("/api-key", status_code=status.HTTP_200_OK, response_model=ApiKeyStatus)
async def save_api_key(
    body: ApiKeyUpsert,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyStatus:
    """Store an API key encrypted at rest. Never returns the plaintext value."""
    await service.upsert_api_key(db, current_user.id, body.key_name, body.key_value)
    return ApiKeyStatus(key_name=body.key_name, is_configured=True)


@router.get("/api-key/anthropic/test", response_model=ApiKeyTestResult)
async def test_anthropic_api_key(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyTestResult:
    """Test the stored Anthropic API key by making a live API call."""
    result = await service.test_anthropic_api_key(db, current_user.id)
    return ApiKeyTestResult(**result)


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
