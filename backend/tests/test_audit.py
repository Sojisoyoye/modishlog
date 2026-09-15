"""Tests for the audit trail domain (task #246)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.audit.models import AuditLog
from src.audit.service import list_audit_events, record_audit_event
from src.core.security import get_password_hash

VALID_PASSWORD = "SuperSecret123!"


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test User",
        is_active=True,
        role=UserRole.ADMIN,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    return user


class TestRecordAuditEvent:
    @pytest.mark.asyncio
    async def test_record_audit_event_writes_expected_fields(self):
        """Happy path: a call writes an AuditLog row with the given fields."""
        db = _mock_db()
        business_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        entry = await record_audit_event(
            db,
            business_id=business_id,
            actor_user_id=actor_id,
            action="sell_return_created",
            entity_type="sell_return",
            entity_id=entity_id,
            details={"sale_id": "abc"},
        )

        db.add.assert_called_once()
        added = db.add.call_args.args[0]
        assert isinstance(added, AuditLog)
        assert added.business_id == business_id
        assert added.actor_user_id == actor_id
        assert added.action == "sell_return_created"
        assert added.entity_type == "sell_return"
        assert added.entity_id == entity_id
        assert added.details == {"sale_id": "abc"}
        db.flush.assert_called_once()
        assert entry is added

    @pytest.mark.asyncio
    async def test_record_audit_event_details_optional(self):
        """details is optional and defaults to None -- doesn't error without it."""
        db = _mock_db()

        entry = await record_audit_event(
            db,
            business_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
            action="user_deactivated",
            entity_type="user",
            entity_id=uuid.uuid4(),
        )

        assert entry.details is None


class TestListAuditEvents:
    @pytest.mark.asyncio
    async def test_list_audit_events_scoped_to_business(self):
        """Only returns events for the given business_id, not other businesses'."""
        own_business_id = uuid.uuid4()
        entry = AuditLog(
            id=uuid.uuid4(),
            business_id=own_business_id,
            actor_user_id=uuid.uuid4(),
            action="sell_return_created",
            entity_type="sell_return",
            entity_id=uuid.uuid4(),
        )

        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await list_audit_events(db, own_business_id, page=1, page_size=25)

        assert total == 1
        assert items == [entry]
        # Both queries (count + list) must filter by business_id.
        for call in db.execute.call_args_list:
            compiled = str(call.args[0].compile(compile_kwargs={"literal_binds": False}))
            assert "audit_logs.business_id" in compiled

    @pytest.mark.asyncio
    async def test_list_audit_events_empty_business_returns_empty(self):
        """A business with no audit events gets an empty list, not an error."""
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await list_audit_events(db, uuid.uuid4())

        assert items == []
        assert total == 0


class TestAuditLogEndpointAuthorization:
    """The audit log read endpoint must be admin/owner-only, like the
    sensitive actions it records."""

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

    def _override_auth_as(self, user):
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        _business_id = uuid.uuid4()

        async def _fake_auth():
            return user

        async def _fake_business_id():
            return _business_id

        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_sales_manager_cannot_list_audit_log(self):
        from src.auth.models import UserRole

        self._override_db(_mock_db())
        self._override_auth_as(_make_user(role=UserRole.SALES_MANAGER))

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/audit-log")
        assert resp.status_code == 403

    def test_admin_can_list_audit_log(self):
        from src.auth.models import UserRole

        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        self._override_db(db)
        self._override_auth_as(_make_user(role=UserRole.ADMIN))

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/audit-log")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0, "page": 1, "page_size": 25}
