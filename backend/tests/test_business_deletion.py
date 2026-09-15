"""Tests for self-service business account deletion (task #252)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.models import Business, User, UserRole
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides) -> User:
    defaults = dict(
        email="owner@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test Owner",
        is_active=True,
        role=UserRole.OWNER,
        email_verified=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    if "id" not in overrides:
        user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_business(**overrides) -> Business:
    defaults = dict(name="Test Traders", currency="NGN")
    defaults.update(overrides)
    business = Business(**defaults)
    if "id" not in overrides:
        business.id = uuid.uuid4()
    return business


def _mock_db_lookup(business=None):
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = business
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


class TestRequestBusinessDeletion:
    @pytest.mark.asyncio
    async def test_schedules_deletion_and_sets_purge_at(self):
        from src.auth.service import request_business_deletion

        business = _make_business()
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            result = await request_business_deletion(db, business.id, owner.id)

        assert result.deletion_requested_at is not None
        assert result.purge_at is not None
        expected_purge = result.deletion_requested_at + timedelta(days=30)
        assert abs((result.purge_at - expected_purge).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_revokes_all_business_refresh_tokens(self):
        from src.auth.service import request_business_deletion

        business = _make_business()
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            await request_business_deletion(db, business.id, owner.id)

        # At least one execute call beyond the business lookup should be a
        # RefreshToken deletion scoped to this business's users.
        delete_calls = [
            c for c in db.execute.call_args_list
            if "refresh_tokens" in str(c.args[0]).lower()
        ]
        assert len(delete_calls) >= 1

    @pytest.mark.asyncio
    async def test_records_audit_event(self):
        from src.auth.service import request_business_deletion

        business = _make_business()
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            await request_business_deletion(db, business.id, owner.id)

        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["business_id"] == business.id
        assert kwargs["actor_user_id"] == owner.id
        assert kwargs["action"] == "business_deletion_scheduled"
        assert kwargs["entity_type"] == "business"
        assert kwargs["entity_id"] == business.id

    @pytest.mark.asyncio
    async def test_already_scheduled_raises(self):
        from src.auth.exceptions import DeletionAlreadyScheduledError
        from src.auth.service import request_business_deletion

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with pytest.raises(DeletionAlreadyScheduledError):
            await request_business_deletion(db, business.id, owner.id)

    @pytest.mark.asyncio
    async def test_business_not_found_raises(self):
        from src.auth.exceptions import UserNotFoundError
        from src.auth.service import request_business_deletion

        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await request_business_deletion(db, uuid.uuid4(), uuid.uuid4())


class TestCancelBusinessDeletion:
    @pytest.mark.asyncio
    async def test_clears_deletion_fields(self):
        from src.auth.service import cancel_business_deletion

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            result = await cancel_business_deletion(db, business.id, owner.id)

        assert result.deletion_requested_at is None
        assert result.purge_at is None

    @pytest.mark.asyncio
    async def test_records_audit_event(self):
        from src.auth.service import cancel_business_deletion

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            await cancel_business_deletion(db, business.id, owner.id)

        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["action"] == "business_deletion_cancelled"

    @pytest.mark.asyncio
    async def test_not_scheduled_raises(self):
        from src.auth.exceptions import DeletionNotScheduledError
        from src.auth.service import cancel_business_deletion

        business = _make_business()
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with pytest.raises(DeletionNotScheduledError):
            await cancel_business_deletion(db, business.id, owner.id)

    @pytest.mark.asyncio
    async def test_already_purged_raises(self):
        """Once the background purge job (task #260) has anonymized a
        business, cancelling must be refused -- there's nothing meaningful
        left to restore, and reactivating anonymized data would be
        misleading."""
        from src.auth.exceptions import BusinessAlreadyPurgedError
        from src.auth.service import cancel_business_deletion

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
            purge_at=datetime.now(timezone.utc) - timedelta(days=1),
            purged_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        owner = _make_user(business_id=business.id)
        db = _mock_db_lookup(business)

        with pytest.raises(BusinessAlreadyPurgedError):
            await cancel_business_deletion(db, business.id, owner.id)


class TestAuthenticateUserBlocksPendingDeletion:
    @pytest.mark.asyncio
    async def test_login_blocked_while_deletion_pending(self):
        from src.auth.exceptions import BusinessPendingDeletionError
        from src.auth.service import authenticate_user

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        user = _make_user(business_id=business.id)
        user.business = business

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(BusinessPendingDeletionError):
            await authenticate_user(db, user.email, VALID_PASSWORD)

    @pytest.mark.asyncio
    async def test_login_allowed_when_no_deletion_pending(self):
        from src.auth.service import authenticate_user

        business = _make_business()
        user = _make_user(business_id=business.id, email_verified=True)
        user.business = business

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        result = await authenticate_user(db, user.email, VALID_PASSWORD)
        assert result is user


class TestGetCurrentActiveUserBlocksNonOwnerMidSession:
    """Refresh-token revocation stops renewal, but an already-issued access
    token (up to 24h lifetime) stays validly signed until it expires --
    'immediately revoke all active sessions' (task #252) needs a per-
    request check too, not just a login-time one. Owner is exempted so they
    can still reach the cancel-deletion endpoint during the grace period."""

    @pytest.mark.asyncio
    async def test_non_owner_blocked_mid_session(self):
        from fastapi import HTTPException

        from src.auth.dependencies import get_current_active_user
        from src.auth.models import UserRole

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        staff = _make_user(role=UserRole.SALES_MANAGER, business_id=business.id)
        staff.business = business

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(staff)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_not_blocked_mid_session(self):
        from src.auth.dependencies import get_current_active_user
        from src.auth.models import UserRole

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        owner = _make_user(role=UserRole.OWNER, business_id=business.id)
        owner.business = business

        result = await get_current_active_user(owner)
        assert result is owner

    @pytest.mark.asyncio
    async def test_no_deletion_pending_not_blocked(self):
        from src.auth.dependencies import get_current_active_user
        from src.auth.models import UserRole

        business = _make_business()
        staff = _make_user(role=UserRole.SALES_MANAGER, business_id=business.id)
        staff.business = business

        result = await get_current_active_user(staff)
        assert result is staff


class TestBusinessDeletionEndpoints:
    """Only UserRole.OWNER may schedule or cancel deletion -- ADMIN is not
    sufficient, unlike most other admin-gated endpoints in this codebase."""

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

    def _override_auth_as(self, user, business_id):
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        async def _fake_auth():
            return user

        async def _fake_business_id():
            return business_id

        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_admin_cannot_close_business(self):
        """ADMIN (not OWNER) must be refused with 403."""
        business = _make_business()
        admin = _make_user(role=UserRole.ADMIN, business_id=business.id)
        self._override_db(_mock_db_lookup(business))
        self._override_auth_as(admin, business.id)

        with TestClient(self.app) as client:
            resp = client.post("/api/v1/auth/business/close")
        assert resp.status_code == 403

    def test_owner_can_close_business(self):
        business = _make_business()
        owner = _make_user(role=UserRole.OWNER, business_id=business.id)
        self._override_db(_mock_db_lookup(business))
        self._override_auth_as(owner, business.id)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/auth/business/close")
        assert resp.status_code == 200
        assert resp.json()["purge_at"] is not None

    def test_owner_can_cancel_deletion(self):
        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc),
            purge_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        owner = _make_user(role=UserRole.OWNER, business_id=business.id)
        self._override_db(_mock_db_lookup(business))
        self._override_auth_as(owner, business.id)

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/auth/business/cancel-deletion")
        assert resp.status_code == 200
