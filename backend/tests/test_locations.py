"""Tests for business locations CRUD operations."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.locations.exceptions import DuplicateLocationCodeError, LocationNotFoundError
from src.locations.models import BusinessLocation
from src.locations.schemas import LocationCreate, LocationUpdate
from src.locations.service import (
    create_location,
    get_location,
    list_locations,
    update_location,
)


def _make_user(**overrides):
    """Build a minimal User for tests."""
    from src.auth.models import User, UserRole
    from src.core.security import get_password_hash

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash("Str0ng!Pass#99"),
        full_name="Test User",
        is_active=True,
        role=UserRole.ADMIN,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_location(**overrides):
    """Build a minimal BusinessLocation for tests."""
    defaults = dict(
        name="Main Branch",
        location_code="LOC-001",
        mobile="08012345678",
        email="main@example.com",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        is_active=True,
    )
    defaults.update(overrides)
    location = BusinessLocation(**defaults)
    location.id = overrides.get("id", uuid.uuid4())
    location.created_by = overrides.get("created_by", uuid.uuid4())
    location.created_at = datetime.now(timezone.utc)
    location.updated_at = datetime.now(timezone.utc)
    return location


# ---------------------------------------------------------------------------
# TestCreateLocation
# ---------------------------------------------------------------------------

class TestCreateLocation:
    @pytest.mark.asyncio
    async def test_create_location_happy_path(self):
        """Creates a location successfully, db.add should be called."""
        db = AsyncMock()
        user_id = uuid.uuid4()

        # No existing location with this code
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        data = LocationCreate(
            name="Main Branch",
            location_code="LOC-001",
            city="Lagos",
        )

        location = await create_location(db, data, user_id)

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert location.name == "Main Branch"
        assert location.location_code == "LOC-001"
        assert location.created_by == user_id

    @pytest.mark.asyncio
    async def test_create_location_duplicate_code_raises(self):
        """Raises DuplicateLocationCodeError when location_code already exists."""
        db = AsyncMock()
        user_id = uuid.uuid4()

        existing = _make_location(location_code="LOC-001")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute.return_value = mock_result

        data = LocationCreate(
            name="Another Branch",
            location_code="LOC-001",
        )

        with pytest.raises(DuplicateLocationCodeError):
            await create_location(db, data, user_id)

        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetLocation
# ---------------------------------------------------------------------------

class TestGetLocation:
    @pytest.mark.asyncio
    async def test_get_location_found(self):
        """Returns location when found."""
        db = AsyncMock()
        location_id = uuid.uuid4()
        location = _make_location(id=location_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = location
        db.execute.return_value = mock_result

        result = await get_location(db, location_id)

        assert result.id == location_id
        assert result.name == location.name

    @pytest.mark.asyncio
    async def test_get_location_not_found(self):
        """Raises LocationNotFoundError when location doesn't exist."""
        db = AsyncMock()
        location_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(LocationNotFoundError):
            await get_location(db, location_id)


# ---------------------------------------------------------------------------
# TestListLocations
# ---------------------------------------------------------------------------

class TestListLocations:
    @pytest.mark.asyncio
    async def test_list_locations_returns_all(self):
        """list_locations returns all locations and a total count."""
        db = AsyncMock()

        location1 = _make_location(name="Branch A", location_code="LOC-001")
        location2 = _make_location(name="Branch B", location_code="LOC-002")
        items = [location1, location2]

        # First execute → count, second execute → items
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items

        db.execute.side_effect = [count_result, items_result]

        result_items, total = await list_locations(db)

        assert total == 2
        assert len(result_items) == 2
        assert result_items[0].name == "Branch A"
        assert result_items[1].name == "Branch B"
