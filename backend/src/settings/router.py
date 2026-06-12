"""Settings API routes — thin layer, all logic in service.py."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.settings import service
from src.settings.schemas import ApiKeyStatus, ApiKeyUpsert

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
