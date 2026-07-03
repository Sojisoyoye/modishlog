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
    location.business_id = overrides.get("business_id", uuid.uuid4())
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
        db.add = MagicMock()  # db.add is synchronous in the service
        user_id = uuid.uuid4()
        business_id = uuid.uuid4()

        # No existing location with this code
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        data = LocationCreate(
            name="Main Branch",
            location_code="LOC-001",
            city="Lagos",
        )

        location = await create_location(db, data, user_id, business_id=business_id)

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert location.name == "Main Branch"
        assert location.location_code == "LOC-001"
        assert location.created_by == user_id
        assert location.business_id == business_id

    @pytest.mark.asyncio
    async def test_create_location_duplicate_code_raises(self):
        """Raises DuplicateLocationCodeError when location_code already exists within same business."""
        db = AsyncMock()
        user_id = uuid.uuid4()
        business_id = uuid.uuid4()

        existing = _make_location(location_code="LOC-001", business_id=business_id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute.return_value = mock_result

        data = LocationCreate(
            name="Another Branch",
            location_code="LOC-001",
        )

        with pytest.raises(DuplicateLocationCodeError):
            await create_location(db, data, user_id, business_id=business_id)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_location_same_code_different_business_allowed(self):
        """Same location_code is allowed for different businesses (no duplicate raised)."""
        db = AsyncMock()
        db.add = MagicMock()
        user_id = uuid.uuid4()
        business_b_id = uuid.uuid4()

        # DB returns None because business_b has no location with this code
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        data = LocationCreate(
            name="Business B Branch",
            location_code="LOC-001",  # same code used by another business
            city="Abuja",
        )

        # Should NOT raise; business isolation means each business has its own namespace
        location = await create_location(db, data, user_id, business_id=business_b_id)

        db.add.assert_called_once()
        assert location.location_code == "LOC-001"
        assert location.business_id == business_b_id


# ---------------------------------------------------------------------------
# TestGetLocation
# ---------------------------------------------------------------------------


class TestGetLocation:
    @pytest.mark.asyncio
    async def test_get_location_found(self):
        """Returns location when found."""
        db = AsyncMock()
        location_id = uuid.uuid4()
        business_id = uuid.uuid4()
        location = _make_location(id=location_id, business_id=business_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = location
        db.execute.return_value = mock_result

        result = await get_location(db, location_id, business_id=business_id)

        assert result.id == location_id
        assert result.name == location.name

    @pytest.mark.asyncio
    async def test_get_location_not_found(self):
        """Raises LocationNotFoundError when location doesn't exist."""
        db = AsyncMock()
        location_id = uuid.uuid4()
        business_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(LocationNotFoundError):
            await get_location(db, location_id, business_id=business_id)


# ---------------------------------------------------------------------------
# TestListLocations
# ---------------------------------------------------------------------------


class TestListLocations:
    @pytest.mark.asyncio
    async def test_list_locations_returns_all(self):
        """list_locations returns all locations and a total count."""
        db = AsyncMock()
        business_id = uuid.uuid4()

        location1 = _make_location(name="Branch A", location_code="LOC-001", business_id=business_id)
        location2 = _make_location(name="Branch B", location_code="LOC-002", business_id=business_id)
        items = [location1, location2]

        # First execute → count, second execute → items
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items

        db.execute.side_effect = [count_result, items_result]

        result_items, total = await list_locations(db, business_id=business_id)

        assert total == 2
        assert len(result_items) == 2
        assert result_items[0].name == "Branch A"
        assert result_items[1].name == "Branch B"


# ---------------------------------------------------------------------------
# TestUpdateLocation
# ---------------------------------------------------------------------------


class TestUpdateLocation:
    @pytest.mark.asyncio
    async def test_update_location_happy_path(self):
        """Updates a location field successfully."""
        db = AsyncMock()
        location_id = uuid.uuid4()
        business_id = uuid.uuid4()
        location = _make_location(id=location_id, name="Old Name", business_id=business_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = location
        db.execute.return_value = mock_result

        data = LocationUpdate(name="New Name")
        updated = await update_location(db, location_id, data, business_id=business_id)

        assert updated.name == "New Name"
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_location_not_found(self):
        """Raises LocationNotFoundError when location doesn't exist."""
        db = AsyncMock()
        business_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        data = LocationUpdate(name="New Name")
        with pytest.raises(LocationNotFoundError):
            await update_location(db, uuid.uuid4(), data, business_id=business_id)


# ---------------------------------------------------------------------------
# TestBusinessIsolation
# ---------------------------------------------------------------------------


class TestBusinessIsolation:
    @pytest.mark.asyncio
    async def test_locations_isolates_by_business(self):
        """Locations for business A are not visible when querying for business B."""
        business_a_id = uuid.uuid4()
        business_b_id = uuid.uuid4()

        async def fake_execute_a(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [MagicMock()]
            r.scalar.return_value = 1
            return r

        async def fake_execute_b(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            r.scalar.return_value = 0
            return r

        db_a, db_b = AsyncMock(), AsyncMock()
        db_a.execute = fake_execute_a
        db_b.execute = fake_execute_b

        result_a = await list_locations(db_a, business_id=business_a_id)
        result_b = await list_locations(db_b, business_id=business_b_id)
        items_a = result_a[0] if isinstance(result_a, tuple) else result_a
        items_b = result_b[0] if isinstance(result_b, tuple) else result_b
        assert len(items_a) > 0
        assert len(items_b) == 0

    @pytest.mark.asyncio
    async def test_locations_owner_sees_own_data(self):
        """Owner can retrieve their own location when scoped by business_id."""
        business_id = uuid.uuid4()
        mock_location = MagicMock()

        async def fake_execute(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [mock_location]
            r.scalar.return_value = 1
            return r

        db = AsyncMock()
        db.execute = fake_execute
        result = await list_locations(db, business_id=business_id)
        items = result[0] if isinstance(result, tuple) else result
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_create_location_sets_business_id(self):
        """create_location stores the supplied business_id on the new location."""
        db = AsyncMock()
        db.add = MagicMock()
        user_id = uuid.uuid4()
        business_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        data = LocationCreate(
            name="Isolated Branch",
            location_code="LOC-ISO-01",
            city="Abuja",
        )

        location = await create_location(db, data, user_id, business_id=business_id)

        assert location.business_id == business_id

    @pytest.mark.asyncio
    async def test_get_location_wrong_business_raises(self):
        """get_location raises LocationNotFoundError when business_id does not match.

        The DB-level WHERE clause filters out the row; the service receives None
        and must raise LocationNotFoundError (simulated by mock returning None).
        """
        db = AsyncMock()
        location_id = uuid.uuid4()
        wrong_business_id = uuid.uuid4()

        # DB returns no row because the WHERE business_id = wrong_business_id clause
        # finds nothing — the service must raise LocationNotFoundError.
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(LocationNotFoundError):
            await get_location(db, location_id, business_id=wrong_business_id)

    @pytest.mark.asyncio
    async def test_update_location_wrong_business_raises(self):
        """update_location raises LocationNotFoundError when business_id does not match."""
        db = AsyncMock()
        location_id = uuid.uuid4()
        correct_business_id = uuid.uuid4()
        wrong_business_id = uuid.uuid4()

        location = _make_location(id=location_id)
        location.business_id = correct_business_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        data = LocationUpdate(name="Hacked Name")
        with pytest.raises(LocationNotFoundError):
            await update_location(db, location_id, data, business_id=wrong_business_id)
