"""Tests for business isolation dependency."""

import uuid
import pytest
from types import SimpleNamespace
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_current_business_id_returns_uuid():
    """get_current_business_id returns business_id UUID when user is associated with a business."""
    from src.auth.dependencies import get_current_business_id

    business_id = uuid.uuid4()
    user = SimpleNamespace(is_active=True, business_id=business_id)

    result = await get_current_business_id(current_user=user)
    assert result == business_id


@pytest.mark.asyncio
async def test_get_current_business_id_raises_400_when_none():
    """get_current_business_id raises HTTP 400 when user has no business_id."""
    from src.auth.dependencies import get_current_business_id

    user = SimpleNamespace(is_active=True, business_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_business_id(current_user=user)

    assert exc_info.value.status_code == 400
    assert "not associated with a business" in exc_info.value.detail
