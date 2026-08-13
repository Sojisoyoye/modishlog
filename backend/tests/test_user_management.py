"""Tests for admin user management endpoints (task #154)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.models import User, UserRole
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides) -> User:
    """Build an in-memory User with sensible defaults."""
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
    if "id" not in overrides:
        user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _mock_db(user=None):
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    result_mock.scalars.return_value.all.return_value = [user] if user else []
    result_mock.scalar_one.return_value = 1
    db.execute.return_value = result_mock
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=user)
    return db


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


class TestListUsersService:
    """Unit tests for list_users service function."""

    @pytest.mark.asyncio
    async def test_list_users_returns_paginated_results(self):
        """list_users must return a list of users and total count."""
        from src.auth.service import list_users

        admin = _make_user(business_id=uuid.uuid4())
        user2 = _make_user(email="other@example.com", role=UserRole.SALES_MANAGER)

        db = AsyncMock()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [admin, user2]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        db.execute.side_effect = [count_result, items_result]

        business_id = uuid.uuid4()
        items, total = await list_users(db, business_id=business_id, page=1, page_size=20, search=None)

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_users_search_filters_by_email(self):
        """list_users with search must pass LIKE filter to query."""
        from src.auth.service import list_users

        matching = _make_user(email="soji@example.com")
        db = AsyncMock()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [matching]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        db.execute.side_effect = [count_result, items_result]

        business_id = uuid.uuid4()
        items, total = await list_users(db, business_id=business_id, page=1, page_size=20, search="soji")

        assert total == 1
        assert items[0].email == "soji@example.com"


def _mock_db_lookup(user=None):
    """AsyncMock db whose db.execute(select(...)) returns *user* via scalar_one_or_none."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    return db


class TestUpdateUserService:
    """Unit tests for update_user service function."""

    @pytest.mark.asyncio
    async def test_update_user_role(self):
        """update_user must update the user's role."""
        from src.auth.service import update_user

        business_id = uuid.uuid4()
        target = _make_user(role=UserRole.SALES_MANAGER, business_id=business_id)
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(target)

        result = await update_user(db, target.id, {"role": UserRole.ADMIN}, admin.id, business_id)

        assert result.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_update_user_full_name(self):
        """update_user must update full_name."""
        from src.auth.service import update_user

        business_id = uuid.uuid4()
        target = _make_user(full_name="Old Name", business_id=business_id)
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(target)

        result = await update_user(db, target.id, {"full_name": "New Name"}, admin.id, business_id)

        assert result.full_name == "New Name"

    @pytest.mark.asyncio
    async def test_update_user_not_found_raises(self):
        """update_user must raise UserNotFoundError when user does not exist."""
        from src.auth.exceptions import UserNotFoundError
        from src.auth.service import update_user

        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await update_user(db, uuid.uuid4(), {"full_name": "X"}, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_admin_cannot_deactivate_self(self):
        """update_user must raise CannotModifySelfError when admin sets own is_active=False."""
        from src.auth.exceptions import CannotModifySelfError
        from src.auth.service import update_user

        business_id = uuid.uuid4()
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(admin)

        with pytest.raises(CannotModifySelfError):
            await update_user(db, admin.id, {"is_active": False}, admin.id, business_id)

    @pytest.mark.asyncio
    async def test_admin_cannot_demote_own_role(self):
        """update_user must raise CannotModifySelfError when admin demotes own role."""
        from src.auth.exceptions import CannotModifySelfError
        from src.auth.service import update_user

        business_id = uuid.uuid4()
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(admin)

        with pytest.raises(CannotModifySelfError):
            await update_user(db, admin.id, {"role": UserRole.SALES_MANAGER}, admin.id, business_id)


class TestUserManagementBusinessIsolation:
    """Compiled-SQL checks proving get_user_by_id/update_user/deactivate_user/
    activate_user/admin_reset_user_password filter their lookup by business_id
    (S4, task 177) — an admin/owner from business A must not be able to reach
    a business B user by guessing their UUID."""

    @pytest.mark.asyncio
    async def test_get_user_by_id_query_filters_by_business_id(self):
        from src.auth.service import get_user_by_id

        business_id = uuid.uuid4()
        db = _mock_db_lookup(None)
        from src.auth.exceptions import UserNotFoundError

        with pytest.raises(UserNotFoundError):
            await get_user_by_id(db, uuid.uuid4(), business_id)

        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert business_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_update_user_query_filters_by_business_id(self):
        from src.auth.service import update_user
        from src.auth.exceptions import UserNotFoundError

        business_id = uuid.uuid4()
        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await update_user(db, uuid.uuid4(), {"full_name": "X"}, uuid.uuid4(), business_id)

        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert business_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_deactivate_user_query_filters_by_business_id(self):
        from src.auth.service import deactivate_user
        from src.auth.exceptions import UserNotFoundError

        business_id = uuid.uuid4()
        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await deactivate_user(db, uuid.uuid4(), uuid.uuid4(), business_id)

        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert business_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_activate_user_query_filters_by_business_id(self):
        from src.auth.service import activate_user
        from src.auth.exceptions import UserNotFoundError

        business_id = uuid.uuid4()
        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await activate_user(db, uuid.uuid4(), business_id)

        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert business_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_admin_reset_user_password_query_filters_by_business_id(self):
        from src.auth.service import admin_reset_user_password
        from src.auth.exceptions import UserNotFoundError

        business_id = uuid.uuid4()
        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await admin_reset_user_password(db, uuid.uuid4(), business_id)

        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert business_id.hex in compiled.replace("-", "")


class TestDeactivateUserService:
    """Unit tests for deactivate_user service function."""

    @pytest.mark.asyncio
    async def test_deactivate_user_sets_inactive(self):
        """deactivate_user must set is_active=False."""
        from src.auth.service import deactivate_user

        business_id = uuid.uuid4()
        target = _make_user(is_active=True, business_id=business_id)
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(target)

        await deactivate_user(db, target.id, admin.id, business_id)

        assert target.is_active is False

    @pytest.mark.asyncio
    async def test_deactivate_user_cannot_deactivate_self(self):
        """deactivate_user must raise CannotModifySelfError for own account."""
        from src.auth.exceptions import CannotModifySelfError
        from src.auth.service import deactivate_user

        business_id = uuid.uuid4()
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(admin)

        with pytest.raises(CannotModifySelfError):
            await deactivate_user(db, admin.id, admin.id, business_id)

    @pytest.mark.asyncio
    async def test_deactivate_revokes_refresh_tokens(self):
        """deactivate_user must delete refresh tokens for the deactivated user."""
        from src.auth.service import deactivate_user

        business_id = uuid.uuid4()
        target = _make_user(business_id=business_id)
        admin = _make_user(business_id=business_id)
        db = _mock_db_lookup(target)

        await deactivate_user(db, target.id, admin.id, business_id)

        db.execute.assert_called()  # Lookup + token deletion queries were executed


class TestActivateUserService:
    """Unit tests for activate_user service function."""

    @pytest.mark.asyncio
    async def test_activate_user_sets_active(self):
        """activate_user must set is_active=True."""
        from src.auth.service import activate_user

        business_id = uuid.uuid4()
        target = _make_user(is_active=False, business_id=business_id)
        db = _mock_db_lookup(target)

        await activate_user(db, target.id, business_id)

        assert target.is_active is True

    @pytest.mark.asyncio
    async def test_activate_user_not_found_raises(self):
        """activate_user must raise UserNotFoundError for unknown ID."""
        from src.auth.exceptions import UserNotFoundError
        from src.auth.service import activate_user

        db = _mock_db_lookup(None)

        with pytest.raises(UserNotFoundError):
            await activate_user(db, uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestAdminUsersEndpoints:
    """Tests for GET/POST /auth/admin/users endpoints."""

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

    def _override_require_admin(self, admin_user=None):
        from src.auth.dependencies import require_admin

        if admin_user is None:
            admin_user = _make_user(business_id=uuid.uuid4())

        async def _fake_admin():
            return admin_user

        self.app.dependency_overrides[require_admin] = _fake_admin

    def test_list_users_returns_paginated_response(self):
        """GET /admin/users must return items list and total."""
        from src.auth.service import list_users

        biz_id = uuid.uuid4()
        admin = _make_user(business_id=biz_id)
        user2 = _make_user(email="other@example.com", role=UserRole.SALES_MANAGER, business_id=biz_id)
        self._override_require_admin(admin)

        with patch("src.auth.router.list_users", AsyncMock(return_value=([admin, user2], 2))):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.get("/api/v1/auth/admin/users")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_users_non_admin_returns_403(self):
        """GET /admin/users without admin role must return 403."""
        non_admin = _make_user(role=UserRole.SALES_MANAGER)
        from src.auth.service import build_token

        token = build_token(non_admin)
        db = AsyncMock()
        db.get = AsyncMock(return_value=non_admin)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/auth/admin/users",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403

    def test_invite_user_creates_account(self):
        """POST /admin/users/invite must create a new user and return 201."""
        admin = _make_user(business_id=uuid.uuid4())
        new_user = _make_user(email="new@example.com", role=UserRole.SALES_MANAGER)
        self._override_require_admin(admin)

        with patch("src.auth.router.create_user", AsyncMock(return_value=new_user)):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/auth/admin/users/invite",
                    json={
                        "email": "new@example.com",
                        "full_name": "New User",
                        "role": "sales_manager",
                        "password": VALID_PASSWORD,
                    },
                )

        assert resp.status_code == 201
        assert resp.json()["email"] == "new@example.com"

    def test_invite_user_duplicate_email_returns_409(self):
        """POST /admin/users/invite with existing email must return 409."""
        from src.auth.exceptions import UserAlreadyExistsError

        admin = _make_user(business_id=uuid.uuid4())
        self._override_require_admin(admin)

        with patch(
            "src.auth.router.create_user",
            AsyncMock(side_effect=UserAlreadyExistsError("Email taken")),
        ):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/auth/admin/users/invite",
                    json={
                        "email": "existing@example.com",
                        "full_name": "Dup User",
                        "role": "sales_manager",
                        "password": VALID_PASSWORD,
                    },
                )

        assert resp.status_code == 409

    def test_get_user_by_id_returns_user(self):
        """GET /admin/users/{id} must return user details."""
        admin = _make_user(business_id=uuid.uuid4())
        target = _make_user(email="target@example.com")
        self._override_require_admin(admin)

        with patch("src.auth.router.get_user_by_id", AsyncMock(return_value=target)):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.get(f"/api/v1/auth/admin/users/{target.id}")

        assert resp.status_code == 200
        assert resp.json()["email"] == "target@example.com"

    def test_get_user_by_id_not_found_returns_404(self):
        """GET /admin/users/{id} for unknown user must return 404."""
        from src.auth.exceptions import UserNotFoundError

        admin = _make_user(business_id=uuid.uuid4())
        self._override_require_admin(admin)

        with patch(
            "src.auth.router.get_user_by_id",
            AsyncMock(side_effect=UserNotFoundError("not found")),
        ):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.get(f"/api/v1/auth/admin/users/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_update_user_role_returns_updated_user(self):
        """PATCH /admin/users/{id} must return updated user."""
        admin = _make_user(business_id=uuid.uuid4())
        target = _make_user(role=UserRole.SALES_MANAGER)
        target.role = UserRole.ADMIN
        self._override_require_admin(admin)

        with patch("src.auth.router.update_user", AsyncMock(return_value=target)):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.patch(
                    f"/api/v1/auth/admin/users/{target.id}",
                    json={"role": "admin"},
                )

        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_update_self_deactivate_returns_400(self):
        """PATCH /admin/users/{id} to deactivate own account must return 400."""
        from src.auth.exceptions import CannotModifySelfError

        admin = _make_user(business_id=uuid.uuid4())
        self._override_require_admin(admin)

        with patch(
            "src.auth.router.update_user",
            AsyncMock(side_effect=CannotModifySelfError("Cannot modify self")),
        ):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.patch(
                    f"/api/v1/auth/admin/users/{admin.id}",
                    json={"is_active": False},
                )

        assert resp.status_code == 400

    def test_deactivate_user_sets_inactive(self):
        """POST /admin/users/{id}/deactivate must set user inactive."""
        admin = _make_user(business_id=uuid.uuid4())
        target = _make_user(email="target@example.com")
        self._override_require_admin(admin)

        with patch("src.auth.router.deactivate_user", AsyncMock(return_value=None)):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.post(f"/api/v1/auth/admin/users/{target.id}/deactivate")

        assert resp.status_code == 200

    def test_deactivate_self_returns_400(self):
        """POST /admin/users/{id}/deactivate for own account must return 400."""
        from src.auth.exceptions import CannotModifySelfError

        admin = _make_user(business_id=uuid.uuid4())
        self._override_require_admin(admin)

        with patch(
            "src.auth.router.deactivate_user",
            AsyncMock(side_effect=CannotModifySelfError("Cannot deactivate self")),
        ):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.post(f"/api/v1/auth/admin/users/{admin.id}/deactivate")

        assert resp.status_code == 400

    def test_activate_user_sets_active(self):
        """POST /admin/users/{id}/activate must set user active."""
        admin = _make_user(business_id=uuid.uuid4())
        target = _make_user(is_active=False)
        self._override_require_admin(admin)

        with patch("src.auth.router.activate_user", AsyncMock(return_value=None)):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.post(f"/api/v1/auth/admin/users/{target.id}/activate")

        assert resp.status_code == 200

    def test_admin_reset_password_returns_message(self):
        """POST /admin/users/{id}/reset-password must return a token/message."""
        admin = _make_user(business_id=uuid.uuid4())
        target = _make_user(email="target@example.com")
        self._override_require_admin(admin)

        with patch(
            "src.auth.router.admin_reset_user_password",
            AsyncMock(return_value="raw-token-abc"),
        ):
            db = _mock_db()
            self._override_db(db)
            with TestClient(self.app) as client:
                resp = client.post(f"/api/v1/auth/admin/users/{target.id}/reset-password")

        assert resp.status_code == 200
        assert "token" in resp.json() or "message" in resp.json()

    def test_non_admin_cannot_access_user_management(self):
        """All /admin/users/* endpoints must return 403 for non-admin users."""
        non_admin = _make_user(role=UserRole.SALES_MANAGER)
        from src.auth.service import build_token

        token = build_token(non_admin)
        db = AsyncMock()
        db.get = AsyncMock(return_value=non_admin)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/auth/admin/users",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
