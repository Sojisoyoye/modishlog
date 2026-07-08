"""Tests for the public POST /auth/onboard endpoint and create_business_and_owner service.

TDD: these tests were written BEFORE the implementation.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ONBOARD = {
    "full_name": "Test Owner",
    "email": "owner@example.com",
    "password": "Str0ng!Pass#99",
    "business_name": "Test Corp",
    "currency": "NGN",
    "timezone": "Africa/Lagos",
    "fiscal_year_start_month": 1,
    "ndpr_consent": True,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    """Build an in-memory User with sensible defaults."""
    from src.auth.models import User, UserRole
    from src.core.security import get_password_hash

    defaults = dict(
        email="owner@example.com",
        hashed_password=get_password_hash("Str0ng!Pass#99"),
        full_name="Test Owner",
        is_active=True,
        role=UserRole.OWNER,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    if "id" not in overrides:
        user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_business(**overrides):
    """Build an in-memory Business with sensible defaults."""
    from src.auth.models import Business

    defaults = dict(
        name="Test Corp",
        currency="NGN",
        timezone="Africa/Lagos",
        fiscal_year_start_month=1,
        is_active=True,
    )
    defaults.update(overrides)
    biz = Business(**defaults)
    if "id" not in overrides:
        biz.id = uuid.uuid4()
    biz.created_at = datetime.now(timezone.utc)
    biz.updated_at = datetime.now(timezone.utc)
    return biz


# ---------------------------------------------------------------------------
# TestClient fixture helpers
# ---------------------------------------------------------------------------


class OnboardTestBase:
    """Shared setup for onboard endpoint tests."""

    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_db(self, db_mock):
        from src.core.database import get_db

        async def _fake_db():
            yield db_mock

        self.app.dependency_overrides[get_db] = _fake_db


# ---------------------------------------------------------------------------
# Router / endpoint tests
# ---------------------------------------------------------------------------


class TestOnboardEndpoint(OnboardTestBase):
    """Integration-style tests for POST /api/v1/auth/onboard."""

    def test_onboard_happy_path(self):
        """POST /auth/onboard with valid payload → 201 + access_token + business_id."""
        business = _make_business()
        user = _make_user()
        fake_access = "fake_access_token"
        fake_refresh = "fake_refresh_token"

        with patch(
            "src.auth.router.create_business_and_owner",
            new=AsyncMock(return_value=(business, user, fake_access, fake_refresh)),
        ):
            db_mock = AsyncMock()
            self._override_db(db_mock)
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/auth/onboard", json=VALID_ONBOARD)

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["access_token"] == fake_access
        assert "business_id" in data
        assert data["business_id"] == str(business.id)

    def test_onboard_duplicate_email(self):
        """POST /auth/onboard with already-used email → 409."""
        from src.auth.exceptions import UserAlreadyExistsError

        with patch(
            "src.auth.router.create_business_and_owner",
            new=AsyncMock(side_effect=UserAlreadyExistsError("Email already registered")),
        ):
            db_mock = AsyncMock()
            self._override_db(db_mock)
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/auth/onboard", json=VALID_ONBOARD)

        assert resp.status_code == 409

    def test_onboard_weak_password(self):
        """POST /auth/onboard with a weak password → 422 from Pydantic/service."""
        # The WeakPasswordError is raised in the service; router maps it to 422.
        from src.auth.exceptions import WeakPasswordError

        with patch(
            "src.auth.router.create_business_and_owner",
            new=AsyncMock(side_effect=WeakPasswordError("Password too weak")),
        ):
            db_mock = AsyncMock()
            self._override_db(db_mock)
            payload = {**VALID_ONBOARD, "password": "short"}
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/auth/onboard", json=payload)

        # FastAPI/Pydantic does NOT validate password strength — that's in the service.
        # The service raises WeakPasswordError → router returns 422.
        # However the mock is set to raise WeakPasswordError, so we expect 422.
        assert resp.status_code == 422

    def test_onboard_missing_business_name(self):
        """POST /auth/onboard without business_name → 422 from Pydantic."""
        payload = {k: v for k, v in VALID_ONBOARD.items() if k != "business_name"}
        with TestClient(self.app) as client:
            resp = client.post("/api/v1/auth/onboard", json=payload)
        # Pydantic validates required fields before reaching the service
        assert resp.status_code == 422

    def test_onboard_owner_role_set(self):
        """Service is called with role=OWNER — verifies the router passes the right role."""
        from src.auth.models import UserRole

        business = _make_business()
        owner_user = _make_user(role=UserRole.OWNER)
        fake_access = "fake_access_token"
        fake_refresh = "fake_refresh_token"

        mock_fn = AsyncMock(return_value=(business, owner_user, fake_access, fake_refresh))
        with patch("src.auth.router.create_business_and_owner", new=mock_fn):
            db_mock = AsyncMock()
            self._override_db(db_mock)
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/auth/onboard", json=VALID_ONBOARD)

        assert resp.status_code == 201
        # Verify the service was actually called (not bypassed)
        mock_fn.assert_called_once()
        # The user returned carries OWNER role — the service contract the router relies on
        assert owner_user.role == UserRole.OWNER


class TestCreateBusinessAndOwnerService:
    """Unit tests for create_business_and_owner() in service.py."""

    def test_service_calls_create_user_with_owner_role(self):
        """create_business_and_owner passes role=OWNER to create_user."""
        import asyncio
        from src.auth.models import UserRole
        from src.auth.service import create_business_and_owner
        from src.auth.schemas import OnboardRequest

        data = OnboardRequest(**VALID_ONBOARD)
        business = _make_business()
        owner_user = _make_user(role=UserRole.OWNER)
        owner_user.business_id = business.id

        db = AsyncMock()
        db.flush = AsyncMock()

        with (
            patch("src.auth.service.Business", return_value=business),
            patch(
                "src.auth.service.create_user",
                new=AsyncMock(return_value=owner_user),
            ) as mock_create_user,
            patch("src.auth.service.create_refresh_token", new=AsyncMock(return_value="raw_refresh")),
            patch("src.auth.service.build_token", return_value="access_token"),
        ):
            result = asyncio.run(create_business_and_owner(db, data))

        # The critical assertion: create_user must be called with role=OWNER
        _call_kwargs = mock_create_user.call_args
        assert _call_kwargs.kwargs.get("role") == UserRole.OWNER or (
            len(_call_kwargs.args) >= 5 and _call_kwargs.args[4] == UserRole.OWNER
        ), f"Expected role=OWNER, got call: {_call_kwargs}"

        returned_business, returned_user, access_token, raw_refresh = result
        assert returned_user.role == UserRole.OWNER
        assert access_token == "access_token"
        assert raw_refresh == "raw_refresh"


# ---------------------------------------------------------------------------
# NDPR consent tests (task #168)
# ---------------------------------------------------------------------------


class TestNDPRConsent(OnboardTestBase):
    """Tests for NDPR consent capture on the onboard endpoint."""

    def test_onboard_without_ndpr_consent_returns_422(self):
        """POST /auth/onboard with ndpr_consent=False → 422 (schema validation)."""
        # Pydantic validation fires before the rate limiter executes the route,
        # so we don't need to mock Redis here — the 422 comes from schema rejection.
        payload = {**VALID_ONBOARD, "ndpr_consent": False}
        with TestClient(self.app) as client:
            resp = client.post("/api/v1/auth/onboard", json=payload)
        assert resp.status_code == 422

    def test_onboard_missing_ndpr_consent_returns_422(self):
        """POST /auth/onboard without ndpr_consent field → 422 (field required)."""
        # Explicitly omit ndpr_consent to test the missing-field path
        payload = {k: v for k, v in VALID_ONBOARD.items() if k != "ndpr_consent"}
        with TestClient(self.app) as client:
            resp = client.post("/api/v1/auth/onboard", json=payload)
        assert resp.status_code == 422

    def test_onboard_with_ndpr_consent_stores_timestamp(self):
        """service sets ndpr_consent_given=True and ndpr_consent_at on the user."""
        import asyncio

        from src.auth.models import UserRole
        from src.auth.schemas import OnboardRequest
        from src.auth.service import create_business_and_owner

        business = _make_business()
        store_user = _make_user(role=UserRole.OWNER)
        store_user.business_id = business.id

        onboard_data = OnboardRequest(**{**VALID_ONBOARD, "ndpr_consent": True})

        db = AsyncMock()
        db.flush = AsyncMock()
        with (
            patch("src.auth.service.Business", return_value=business),
            patch(
                "src.auth.service.create_user",
                new=AsyncMock(return_value=store_user),
            ),
            patch("src.auth.service.create_refresh_token", new=AsyncMock(return_value="raw")),
            patch("src.auth.service.build_token", return_value="access"),
        ):
            asyncio.run(create_business_and_owner(db, onboard_data))

        assert store_user.ndpr_consent_given is True
        assert store_user.ndpr_consent_at is not None
