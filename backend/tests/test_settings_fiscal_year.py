"""Tests for fiscal year start settings: service and endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
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


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _make_prefs(user_id=None, month=None, day=None):
    from src.settings.models import UserPreferences

    prefs = UserPreferences(
        user_id=user_id or uuid.uuid4(),
        fiscal_year_start_month=month,
        fiscal_year_start_day=day,
    )
    prefs.id = uuid.uuid4()
    prefs.created_at = datetime.now(timezone.utc)
    prefs.updated_at = datetime.now(timezone.utc)
    return prefs


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestGetFiscalYearStart:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_prefs_row(self):
        """When user has no preferences row, both fields are None."""
        from src.settings.service import get_fiscal_year_start

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_fiscal_year_start(db, uuid.uuid4())

        assert result.fiscal_year_start_month is None
        assert result.fiscal_year_start_day is None

    @pytest.mark.asyncio
    async def test_returns_configured_values(self):
        """When user has a prefs row, month and day are returned."""
        from src.settings.service import get_fiscal_year_start

        user_id = uuid.uuid4()
        prefs = _make_prefs(user_id=user_id, month=4, day=1)

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prefs
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_fiscal_year_start(db, user_id)

        assert result.fiscal_year_start_month == 4
        assert result.fiscal_year_start_day == 1


class TestUpdateFiscalYearStart:
    @pytest.mark.asyncio
    async def test_upserts_and_returns_values(self):
        """update_fiscal_year_start executes an upsert and returns the stored values."""
        from src.settings.service import update_fiscal_year_start

        user_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())

        result = await update_fiscal_year_start(db, user_id, month=4, day=1)

        db.execute.assert_called_once()
        db.flush.assert_called_once()
        assert result.fiscal_year_start_month == 4
        assert result.fiscal_year_start_day == 1

    @pytest.mark.asyncio
    async def test_clears_fiscal_year_when_none_passed(self):
        """Passing month=None, day=None returns nulls (clears the setting)."""
        from src.settings.service import update_fiscal_year_start

        user_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())

        result = await update_fiscal_year_start(db, user_id, month=None, day=None)

        assert result.fiscal_year_start_month is None
        assert result.fiscal_year_start_day is None

    @pytest.mark.asyncio
    async def test_overwrites_existing_values(self):
        """Calling update twice with different values returns the latest values."""
        from src.settings.service import update_fiscal_year_start

        user_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())

        result = await update_fiscal_year_start(db, user_id, month=7, day=15)

        assert result.fiscal_year_start_month == 7
        assert result.fiscal_year_start_day == 15


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestFiscalYearEndpoints:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_db(self, db_mock):
        from src.auth.dependencies import get_current_active_user
        from src.core.database import get_db

        async def _fake_db():
            yield db_mock

        user = _make_user()
        self._test_user = user

        def _fake_user():
            return user

        self.app.dependency_overrides[get_db] = _fake_db
        self.app.dependency_overrides[get_current_active_user] = _fake_user

    def test_get_fiscal_year_returns_nulls_when_unconfigured(self):
        """GET /settings/fiscal-year returns 200 with null fields when not configured."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/settings/fiscal-year")

        assert resp.status_code == 200
        body = resp.json()
        assert body["fiscal_year_start_month"] is None
        assert body["fiscal_year_start_day"] is None

    def test_get_fiscal_year_returns_configured_values(self):
        """GET /settings/fiscal-year returns month and day when configured."""
        db = _mock_db()
        user = _make_user()
        prefs = _make_prefs(user_id=user.id, month=4, day=1)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prefs
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/settings/fiscal-year")

        assert resp.status_code == 200
        body = resp.json()
        assert body["fiscal_year_start_month"] == 4
        assert body["fiscal_year_start_day"] == 1

    def test_put_fiscal_year_valid_saves_and_returns(self):
        """PUT /settings/fiscal-year with valid month/day returns 200."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 4, "fiscal_year_start_day": 1},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["fiscal_year_start_month"] == 4
        assert body["fiscal_year_start_day"] == 1

    def test_put_fiscal_year_clear_with_nulls(self):
        """PUT /settings/fiscal-year with null values clears the setting."""
        db = _mock_db()
        prefs = _make_prefs(month=4, day=1)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prefs
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": None, "fiscal_year_start_day": None},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["fiscal_year_start_month"] is None
        assert body["fiscal_year_start_day"] is None

    def test_put_fiscal_year_invalid_month_returns_422(self):
        """PUT /settings/fiscal-year with month=13 returns 422."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 13, "fiscal_year_start_day": 1},
            )

        assert resp.status_code == 422

    def test_put_fiscal_year_invalid_day_returns_422(self):
        """PUT /settings/fiscal-year with day=32 returns 422."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 1, "fiscal_year_start_day": 32},
            )

        assert resp.status_code == 422

    def test_put_fiscal_year_month_without_day_returns_422(self):
        """PUT /settings/fiscal-year with only month set returns 422."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 4, "fiscal_year_start_day": None},
            )

        assert resp.status_code == 422

    def test_put_fiscal_year_day_without_month_returns_422(self):
        """PUT /settings/fiscal-year with only day set returns 422."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": None, "fiscal_year_start_day": 1},
            )

        assert resp.status_code == 422

    def test_put_fiscal_year_impossible_date_returns_422(self):
        """PUT /settings/fiscal-year with month=2 day=30 returns 422 (Feb has max 29 days)."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 2, "fiscal_year_start_day": 30},
            )

        assert resp.status_code == 422

    def test_put_fiscal_year_feb_28_valid(self):
        """PUT /settings/fiscal-year with month=2 day=28 returns 200 (always valid)."""
        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 2, "fiscal_year_start_day": 28},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["fiscal_year_start_month"] == 2
        assert body["fiscal_year_start_day"] == 28

    def test_put_fiscal_year_april_31_returns_422(self):
        """PUT /settings/fiscal-year with month=4 day=31 returns 422 (April has 30 days)."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/settings/fiscal-year",
                json={"fiscal_year_start_month": 4, "fiscal_year_start_day": 31},
            )

        assert resp.status_code == 422
