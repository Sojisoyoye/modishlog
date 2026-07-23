"""Tests for the authentication system."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from src.auth.models import User
from src.auth.service import (
    LOCKOUT_THRESHOLD,
    authenticate_user,
    build_token,
    create_user,
    validate_password,
)
from src.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_PASSWORD = "Str0ng!Pass#99"
WEAK_PASSWORDS = [
    "short1!A",          # too short (< 12)
    "alllowercaseonly1!", # no uppercase
    "ALLUPPERCASEONLY1!", # no lowercase
    "NoDigitsHere!!!!!", # no digit
    "NoSpecial12345Ab",  # no special char
]


def _make_user(**overrides) -> User:
    """Build an in-memory User with sensible defaults."""
    from src.auth.models import UserRole

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
    # Set fields that aren't constructor args
    if "id" not in overrides:
        user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _mock_db(user: User | None = None) -> AsyncMock:
    """Return an AsyncMock db session.

    If *user* is provided, ``db.execute().scalar_one_or_none()`` returns it.
    """
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db.execute.return_value = result_mock
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _mock_lockout_factory():
    """Return (factory_mock, lockout_db_mock) for patching async_session_factory.

    The factory is used as an async context manager in the lockout write path.
    """
    lockout_db = AsyncMock()
    lockout_db.execute = AsyncMock()
    lockout_db.commit = AsyncMock()
    factory_mock = MagicMock()
    factory_mock.return_value.__aenter__ = AsyncMock(return_value=lockout_db)
    factory_mock.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory_mock, lockout_db


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------


class TestValidatePassword:
    def test_valid_password_passes(self):
        validate_password(VALID_PASSWORD)

    @pytest.mark.parametrize("pwd", WEAK_PASSWORDS)
    def test_weak_password_raises(self, pwd):
        with pytest.raises(WeakPasswordError):
            validate_password(pwd)

    def test_empty_password_raises(self):
        with pytest.raises(WeakPasswordError):
            validate_password("")


# ---------------------------------------------------------------------------
# Password hashing (core/security)
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_is_different_from_plain(self):
        h = get_password_hash(VALID_PASSWORD)
        assert h != VALID_PASSWORD

    def test_verify_correct_password(self):
        h = get_password_hash(VALID_PASSWORD)
        assert verify_password(VALID_PASSWORD, h) is True

    def test_verify_wrong_password(self):
        h = get_password_hash(VALID_PASSWORD)
        assert verify_password("WrongPassword!1", h) is False


# ---------------------------------------------------------------------------
# JWT tokens (core/security)
# ---------------------------------------------------------------------------


class TestJWT:
    def test_create_and_decode_token(self):
        uid = str(uuid.uuid4())
        token = create_access_token(data={"sub": uid})
        payload = decode_access_token(token)
        assert payload["sub"] == uid
        assert "exp" in payload

    def test_expired_token_raises(self):
        token = create_access_token(
            data={"sub": "x"}, expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token(token)

    def test_tampered_token_raises(self):
        token = create_access_token(data={"sub": "x"})
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token(token + "tampered")


# ---------------------------------------------------------------------------
# create_user service
# ---------------------------------------------------------------------------


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_creates_user_successfully(self):
        db = _mock_db(user=None)  # no existing user
        user = await create_user(db, "new@example.com", VALID_PASSWORD, "New User")
        assert user.email == "new@example.com"
        assert user.full_name == "New User"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_email_raises(self):
        existing = _make_user(email="dup@example.com")
        db = _mock_db(user=existing)
        with pytest.raises(UserAlreadyExistsError):
            await create_user(db, "dup@example.com", VALID_PASSWORD, "Dup")

    @pytest.mark.asyncio
    async def test_weak_password_raises(self):
        db = _mock_db(user=None)
        with pytest.raises(WeakPasswordError):
            await create_user(db, "a@b.com", "weak", "Name")

    @pytest.mark.asyncio
    async def test_new_user_does_not_default_to_admin_role(self):
        """create_user must not grant ADMIN role by default — privilege escalation risk."""
        from src.auth.models import UserRole

        db = _mock_db(user=None)
        user = await create_user(db, "role@example.com", VALID_PASSWORD, "Role Test")
        assert user.role != UserRole.ADMIN, (
            "New users must not be created with ADMIN role by default"
        )

    @pytest.mark.asyncio
    async def test_new_user_has_sales_manager_role(self):
        from src.auth.models import UserRole

        db = _mock_db(user=None)
        user = await create_user(db, "sm@example.com", VALID_PASSWORD, "SM Test")
        assert user.role == UserRole.SALES_MANAGER


# ---------------------------------------------------------------------------
# authenticate_user service
# ---------------------------------------------------------------------------


class TestAuthenticateUser:
    @pytest.mark.asyncio
    async def test_valid_credentials_succeeds(self):
        user = _make_user()
        db = _mock_db(user=user)
        result = await authenticate_user(db, user.email, VALID_PASSWORD)
        assert result.email == user.email
        assert result.failed_login_attempts == 0

    @pytest.mark.asyncio
    async def test_unknown_email_raises(self):
        db = _mock_db(user=None)
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(db, "unknown@x.com", VALID_PASSWORD)

    @pytest.mark.asyncio
    async def test_wrong_password_increments_attempts(self):
        user = _make_user(failed_login_attempts=0)
        db = _mock_db(user=user)
        factory_mock, lockout_db = _mock_lockout_factory()
        with patch("src.auth.service.async_session_factory", factory_mock):
            with pytest.raises(InvalidCredentialsError):
                await authenticate_user(db, user.email, "WrongPassword!1")
        # Verify the counter was written via the independent session (not mutated in-place)
        lockout_db.execute.assert_called_once()
        lockout_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_lockout_after_threshold(self):
        user = _make_user(failed_login_attempts=LOCKOUT_THRESHOLD - 1)
        db = _mock_db(user=user)
        factory_mock, lockout_db = _mock_lockout_factory()
        with patch("src.auth.service.async_session_factory", factory_mock):
            with pytest.raises(InvalidCredentialsError):
                await authenticate_user(db, user.email, "WrongPassword!1")
        # Verify the lockout timestamp was written via the independent session
        lockout_db.execute.assert_called_once()
        lockout_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_locked_account_raises(self):
        # Use naive UTC to match the DB column (TIMESTAMP WITHOUT TIME ZONE)
        locked_until = datetime.utcnow() + timedelta(minutes=10)
        user = _make_user(locked_until=locked_until)
        db = _mock_db(user=user)
        with pytest.raises(AccountLockedError) as exc_info:
            await authenticate_user(db, user.email, VALID_PASSWORD)
        assert exc_info.value.locked_until == locked_until

    @pytest.mark.asyncio
    async def test_expired_lockout_allows_login(self):
        # Use naive UTC to match the DB column (TIMESTAMP WITHOUT TIME ZONE)
        expired = datetime.utcnow() - timedelta(minutes=1)
        user = _make_user(locked_until=expired)
        db = _mock_db(user=user)
        result = await authenticate_user(db, user.email, VALID_PASSWORD)
        assert result.failed_login_attempts == 0
        assert result.locked_until is None

    @pytest.mark.asyncio
    async def test_successful_login_resets_counters(self):
        user = _make_user(failed_login_attempts=2)
        db = _mock_db(user=user)
        result = await authenticate_user(db, user.email, VALID_PASSWORD)
        assert result.failed_login_attempts == 0
        assert result.locked_until is None


# ---------------------------------------------------------------------------
# build_token service
# ---------------------------------------------------------------------------


class TestBuildToken:
    def test_returns_decodable_jwt(self):
        user = _make_user()
        token = build_token(user)
        payload = decode_access_token(token)
        assert payload["sub"] == str(user.id)


# ---------------------------------------------------------------------------
# Auth exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_account_locked_stores_timestamp(self):
        ts = datetime.now(timezone.utc)
        err = AccountLockedError(ts)
        assert err.locked_until == ts
        assert str(ts) in str(err)


# ---------------------------------------------------------------------------
# Router / endpoint tests (using FastAPI TestClient)
# ---------------------------------------------------------------------------


class TestAuthEndpoints:
    """Integration-style tests using FastAPI TestClient with mocked DB."""

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
        """Bypass the require_admin dependency, returning a pre-built admin user."""
        from src.auth.dependencies import require_admin

        if admin_user is None:
            admin_user = _make_user()

        async def _fake_admin():
            return admin_user

        self.app.dependency_overrides[require_admin] = _fake_admin

    # -- Register --------------------------------------------------------

    def test_register_success(self):
        db = _mock_db(user=None)

        # Simulate what the real DB does on flush: set id + timestamps
        original_add = db.add

        def _add_and_patch(user):
            user.id = uuid.uuid4()
            user.created_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)
            return original_add(user)

        db.add = _add_and_patch
        self._override_db(db)
        self._override_require_admin()
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "reg@example.com",
                    "password": VALID_PASSWORD,
                    "full_name": "Reg User",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "reg@example.com"
        assert "hashed_password" not in data

    def test_register_weak_password_400(self):
        db = _mock_db(user=None)
        self._override_db(db)
        self._override_require_admin()
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "reg@example.com",
                    "password": "weak",
                    "full_name": "Reg User",
                },
            )
        assert resp.status_code == 400

    def test_register_duplicate_409(self):
        existing = _make_user(email="dup@example.com")
        db = _mock_db(user=existing)
        self._override_db(db)
        self._override_require_admin()
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "dup@example.com",
                    "password": VALID_PASSWORD,
                    "full_name": "Dup",
                },
            )
        assert resp.status_code == 409

    # -- Login -----------------------------------------------------------

    def test_login_success(self):
        user = _make_user()
        db = _mock_db(user=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password_401(self):
        user = _make_user()
        db = _mock_db(user=user)
        self._override_db(db)
        factory_mock, _ = _mock_lockout_factory()
        with patch("src.auth.service.async_session_factory", factory_mock):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/auth/login",
                    json={"email": user.email, "password": "WrongPassword!1"},
                )
        assert resp.status_code == 401

    def test_login_unknown_user_401(self):
        db = _mock_db(user=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": "ghost@example.com", "password": VALID_PASSWORD},
            )
        assert resp.status_code == 401

    def test_login_locked_account_429(self):
        # Use naive UTC to match the DB column (TIMESTAMP WITHOUT TIME ZONE)
        locked_until = datetime.utcnow() + timedelta(minutes=10)
        user = _make_user(locked_until=locked_until)
        db = _mock_db(user=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )
        assert resp.status_code == 429
        assert "locked" in resp.json()["detail"].lower()

    def test_login_locked_returns_locked_until(self):
        """429 response body should include locked_until ISO timestamp."""
        # Use naive UTC to match the DB column (TIMESTAMP WITHOUT TIME ZONE)
        locked_until = datetime.utcnow() + timedelta(minutes=10)
        user = _make_user(locked_until=locked_until)
        db = _mock_db(user=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )
        assert resp.status_code == 429
        data = resp.json()
        assert "locked_until" in data
        # Verify it's a valid ISO timestamp matching what we set
        parsed = datetime.fromisoformat(data["locked_until"])
        # Allow 1-second tolerance for rounding; locked_until is naive UTC so add tzinfo before comparing
        assert abs((parsed - locked_until.replace(tzinfo=timezone.utc)).total_seconds()) < 1

    # -- /me -------------------------------------------------------------

    def test_me_authenticated(self):
        user = _make_user()
        token = build_token(user)
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == user.email

    def test_me_no_token_401(self):
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token_401(self):
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid.token.here"},
            )
        assert resp.status_code == 401

    def test_me_inactive_user_403(self):
        user = _make_user(is_active=False)
        token = build_token(user)
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Register endpoint — admin auth gate
# ---------------------------------------------------------------------------


class TestRegisterAdminAuth:
    """Verify that /register is gated behind the admin auth requirement."""

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
            admin_user = _make_user()

        async def _fake_admin():
            return admin_user

        self.app.dependency_overrides[require_admin] = _fake_admin

    def test_unauthenticated_register_returns_401(self):
        """POST /register without any token must be rejected with 401."""
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "anon@example.com",
                    "password": VALID_PASSWORD,
                    "full_name": "Anonymous",
                },
            )
        assert resp.status_code == 401

    def test_admin_can_register_new_user(self):
        """An authenticated admin must be able to register a new user."""
        from src.auth.models import UserRole

        admin = _make_user(role=UserRole.ADMIN)
        db = _mock_db(user=None)
        original_add = db.add

        def _add_and_patch(user):
            user.id = uuid.uuid4()
            user.created_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)
            return original_add(user)

        db.add = _add_and_patch
        self._override_db(db)
        self._override_require_admin(admin)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "newuser@example.com",
                    "password": VALID_PASSWORD,
                    "full_name": "New User",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@example.com"

    def test_non_admin_register_returns_403(self):
        """A non-admin authenticated user must be refused with 403."""
        from src.auth.models import UserRole
        from src.auth.dependencies import require_admin

        non_admin = _make_user(role=UserRole.SALES_MANAGER)

        # Do NOT override require_admin — let the real one run, but give it a real token
        token = build_token(non_admin)
        db = AsyncMock()
        db.get = AsyncMock(return_value=non_admin)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/register",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "email": "noadmin@example.com",
                    "password": VALID_PASSWORD,
                    "full_name": "No Admin",
                },
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Forgot / Reset password
# ---------------------------------------------------------------------------


def _mock_db_multi(results_sequence: list) -> AsyncMock:
    """Return an AsyncMock db session that returns different results per execute call.

    Each entry in *results_sequence* is the value that
    ``result.scalar_one_or_none()`` will return for the Nth call to
    ``db.execute()``.
    """
    db = AsyncMock()

    result_mocks = []
    for val in results_sequence:
        rm = MagicMock()
        rm.scalar_one_or_none.return_value = val
        result_mocks.append(rm)

    db.execute = AsyncMock(side_effect=result_mocks)
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


class TestForgotPasswordEndpoint:
    """POST /auth/forgot-password endpoint tests."""

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

    def test_forgot_password_generates_token(self):
        """POST /auth/forgot-password with valid email returns 200 + creates a PasswordResetToken."""
        user = _make_user(email="exists@example.com")
        db = _mock_db(user=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "exists@example.com"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        # A token row should have been added to the session
        db.add.assert_called_once()

    def test_forgot_password_unknown_email(self):
        """Unknown email still returns 200 -- don't reveal if email exists."""
        db = _mock_db(user=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "ghost@example.com"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        # No token should be created
        db.add.assert_not_called()

    def test_forgot_password_stores_hashed_token_not_raw(self):
        """create_reset_token must store SHA-256 hash in DB, not the raw token."""
        import asyncio
        import hashlib
        from src.auth import service as auth_service

        user = _make_user(email="hash@example.com")
        db = _mock_db(user=user)

        raw_token = asyncio.run(auth_service.generate_password_reset_token(db, "hash@example.com"))

        assert raw_token is not None
        # The PasswordResetToken added to the session must have the hashed value
        added_obj = db.add.call_args[0][0]
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert added_obj.token == expected_hash, (
            "reset token stored in DB must be SHA-256 hash, not the raw token"
        )
        assert added_obj.token != raw_token, "raw token must never be stored in DB"


class TestResetPasswordEndpoint:
    """POST /auth/reset-password endpoint tests."""

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

    def test_reset_password_valid_token(self):
        """POST /auth/reset-password with valid token + new password returns 200."""
        from src.auth.models import PasswordResetToken

        user = _make_user(email="reset@example.com")
        token_obj = PasswordResetToken(
            user_id=user.id,
            token="valid-reset-token-hex",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=False,
        )
        token_obj.id = uuid.uuid4()
        token_obj.created_at = datetime.now(timezone.utc)
        token_obj.updated_at = datetime.now(timezone.utc)
        token_obj.user = user  # eager-loaded relationship

        # First execute returns the token, second returns the user
        db = _mock_db_multi([token_obj])
        # mock db.get to return user when fetching by id
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": "valid-reset-token-hex",
                    "new_password": VALID_PASSWORD,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        # Token should be marked used
        assert token_obj.used is True

    def test_reset_password_invalid_token(self):
        """Invalid token returns 400."""
        db = _mock_db(user=None)  # scalar_one_or_none returns None
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": "nonexistent-token",
                    "new_password": VALID_PASSWORD,
                },
            )
        assert resp.status_code == 400

    def test_reset_password_expired_token(self):
        """Expired token returns 400."""
        from src.auth.models import PasswordResetToken

        user = _make_user()
        token_obj = PasswordResetToken(
            user_id=user.id,
            token="expired-token-hex",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # expired
            used=False,
        )
        token_obj.id = uuid.uuid4()
        token_obj.created_at = datetime.now(timezone.utc)
        token_obj.updated_at = datetime.now(timezone.utc)

        db = _mock_db_multi([token_obj])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": "expired-token-hex",
                    "new_password": VALID_PASSWORD,
                },
            )
        assert resp.status_code == 400

    def test_reset_password_weak_password(self):
        """Weak new password returns 400."""
        from src.auth.models import PasswordResetToken

        user = _make_user()
        token_obj = PasswordResetToken(
            user_id=user.id,
            token="weak-pw-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=False,
        )
        token_obj.id = uuid.uuid4()
        token_obj.created_at = datetime.now(timezone.utc)
        token_obj.updated_at = datetime.now(timezone.utc)
        token_obj.user = user

        db = _mock_db_multi([token_obj])
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": "weak-pw-token",
                    "new_password": "weak",
                },
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Forgot / Reset password service tests
# ---------------------------------------------------------------------------


class TestGeneratePasswordResetToken:
    @pytest.mark.asyncio
    async def test_generates_token_for_existing_user(self):
        from src.auth.service import generate_password_reset_token

        user = _make_user(email="tokenuser@example.com")
        db = _mock_db(user=user)
        token_str = await generate_password_reset_token(db, "tokenuser@example.com")
        assert token_str is not None
        assert len(token_str) > 32  # secrets.token_urlsafe(32) produces ~43 chars
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_email(self):
        from src.auth.service import generate_password_reset_token

        db = _mock_db(user=None)
        token_str = await generate_password_reset_token(db, "noone@example.com")
        assert token_str is None
        db.add.assert_not_called()


class TestResetPasswordService:
    @pytest.mark.asyncio
    async def test_resets_password_with_valid_token(self):
        from src.auth.models import PasswordResetToken
        from src.auth.service import reset_password

        user = _make_user(email="resetme@example.com")
        old_hash = user.hashed_password

        token_obj = PasswordResetToken(
            user_id=user.id,
            token="service-valid-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=False,
        )
        token_obj.id = uuid.uuid4()
        token_obj.created_at = datetime.now(timezone.utc)
        token_obj.updated_at = datetime.now(timezone.utc)

        db = _mock_db_multi([token_obj])
        db.get = AsyncMock(return_value=user)

        await reset_password(db, "service-valid-token", VALID_PASSWORD)

        assert token_obj.used is True
        assert user.hashed_password != old_hash

    @pytest.mark.asyncio
    async def test_raises_on_invalid_token(self):
        from src.auth.exceptions import InvalidResetTokenError
        from src.auth.service import reset_password

        db = _mock_db(user=None)
        with pytest.raises(InvalidResetTokenError):
            await reset_password(db, "bad-token", VALID_PASSWORD)

    @pytest.mark.asyncio
    async def test_raises_on_expired_token(self):
        from src.auth.models import PasswordResetToken
        from src.auth.exceptions import InvalidResetTokenError
        from src.auth.service import reset_password

        user = _make_user()
        token_obj = PasswordResetToken(
            user_id=user.id,
            token="expired-svc-token",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            used=False,
        )
        token_obj.id = uuid.uuid4()
        token_obj.created_at = datetime.now(timezone.utc)
        token_obj.updated_at = datetime.now(timezone.utc)

        db = _mock_db_multi([token_obj])
        with pytest.raises(InvalidResetTokenError):
            await reset_password(db, "expired-svc-token", VALID_PASSWORD)

    @pytest.mark.asyncio
    async def test_raises_on_weak_password(self):
        from src.auth.models import PasswordResetToken
        from src.auth.service import reset_password

        user = _make_user()
        token_obj = PasswordResetToken(
            user_id=user.id,
            token="weak-pw-svc-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=False,
        )
        token_obj.id = uuid.uuid4()
        token_obj.created_at = datetime.now(timezone.utc)
        token_obj.updated_at = datetime.now(timezone.utc)
        token_obj.user = user

        db = _mock_db_multi([token_obj])
        db.get = AsyncMock(return_value=user)
        with pytest.raises(WeakPasswordError):
            await reset_password(db, "weak-pw-svc-token", "weak")


# ---------------------------------------------------------------------------
# Refresh token service tests
# ---------------------------------------------------------------------------


class TestCreateRefreshToken:
    @pytest.mark.asyncio
    async def test_creates_refresh_token_for_user(self):
        from src.auth.service import create_refresh_token

        user = _make_user()
        db = _mock_db()
        token_str = await create_refresh_token(db, user)
        assert token_str is not None
        assert len(token_str) > 32  # secrets.token_urlsafe(64) produces >= 86 chars
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_unique_tokens_per_call(self):
        from src.auth.service import create_refresh_token

        user = _make_user()
        db1 = _mock_db()
        db2 = _mock_db()
        t1 = await create_refresh_token(db1, user)
        t2 = await create_refresh_token(db2, user)
        assert t1 != t2


class TestRefreshAccessToken:
    @pytest.mark.asyncio
    async def test_valid_refresh_token_returns_new_access_token(self):
        from src.auth.models import RefreshToken
        from src.auth.service import create_refresh_token, refresh_access_token
        import hashlib

        user = _make_user()

        # Simulate a raw token
        raw_token = "a" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=None,
        )
        refresh_token_obj.id = uuid.uuid4()
        refresh_token_obj.created_at = datetime.now(timezone.utc)
        refresh_token_obj.updated_at = datetime.now(timezone.utc)
        refresh_token_obj.user = user

        db = _mock_db_multi([refresh_token_obj])
        db.flush = AsyncMock()

        new_access_token = await refresh_access_token(db, raw_token)
        assert new_access_token is not None
        # Decode it to verify
        from src.core.security import decode_access_token
        payload = decode_access_token(new_access_token)
        assert payload["sub"] == str(user.id)

    @pytest.mark.asyncio
    async def test_expired_refresh_token_raises(self):
        from src.auth.models import RefreshToken
        from src.auth.exceptions import InvalidRefreshTokenError
        from src.auth.service import refresh_access_token
        import hashlib

        user = _make_user()
        raw_token = "b" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # expired
            revoked_at=None,
        )
        refresh_token_obj.id = uuid.uuid4()
        refresh_token_obj.created_at = datetime.now(timezone.utc)
        refresh_token_obj.updated_at = datetime.now(timezone.utc)
        refresh_token_obj.user = user

        db = _mock_db_multi([refresh_token_obj])

        with pytest.raises(InvalidRefreshTokenError):
            await refresh_access_token(db, raw_token)

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_raises(self):
        from src.auth.models import RefreshToken
        from src.auth.exceptions import InvalidRefreshTokenError
        from src.auth.service import refresh_access_token
        import hashlib

        user = _make_user()
        raw_token = "c" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # revoked
        )
        refresh_token_obj.id = uuid.uuid4()
        refresh_token_obj.created_at = datetime.now(timezone.utc)
        refresh_token_obj.updated_at = datetime.now(timezone.utc)
        refresh_token_obj.user = user

        db = _mock_db_multi([refresh_token_obj])

        with pytest.raises(InvalidRefreshTokenError):
            await refresh_access_token(db, raw_token)

    @pytest.mark.asyncio
    async def test_nonexistent_refresh_token_raises(self):
        from src.auth.exceptions import InvalidRefreshTokenError
        from src.auth.service import refresh_access_token

        db = _mock_db(user=None)

        with pytest.raises(InvalidRefreshTokenError):
            await refresh_access_token(db, "nonexistent-token")


class TestRevokeRefreshToken:
    @pytest.mark.asyncio
    async def test_revoke_sets_revoked_at(self):
        from src.auth.models import RefreshToken
        from src.auth.service import revoke_refresh_token
        import hashlib

        user = _make_user()
        raw_token = "d" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=None,
        )
        refresh_token_obj.id = uuid.uuid4()
        refresh_token_obj.created_at = datetime.now(timezone.utc)
        refresh_token_obj.updated_at = datetime.now(timezone.utc)
        refresh_token_obj.user = user

        db = _mock_db_multi([refresh_token_obj])
        db.flush = AsyncMock()

        await revoke_refresh_token(db, raw_token)
        assert refresh_token_obj.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token_is_noop(self):
        """Revoking a token that does not exist should not raise."""
        from src.auth.service import revoke_refresh_token

        db = _mock_db(user=None)
        # Should not raise
        await revoke_refresh_token(db, "nonexistent-refresh-token")


# ---------------------------------------------------------------------------
# Refresh token endpoint tests
# ---------------------------------------------------------------------------


class TestRefreshEndpoint:
    """POST /auth/refresh endpoint tests."""

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

    def test_refresh_with_valid_token_returns_access_token(self):
        from src.auth.models import RefreshToken
        import hashlib

        user = _make_user()
        raw_token = "e" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=None,
        )
        refresh_token_obj.id = uuid.uuid4()
        refresh_token_obj.created_at = datetime.now(timezone.utc)
        refresh_token_obj.updated_at = datetime.now(timezone.utc)
        refresh_token_obj.user = user

        db = _mock_db_multi([refresh_token_obj])
        db.flush = AsyncMock()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": raw_token},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_with_invalid_token_returns_401(self):
        db = _mock_db(user=None)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "bogus-refresh-token"},
            )
        assert resp.status_code == 401

    def test_refresh_with_expired_token_returns_401(self):
        from src.auth.models import RefreshToken
        import hashlib

        user = _make_user()
        raw_token = "f" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        expired_rt = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            revoked_at=None,
        )
        expired_rt.id = uuid.uuid4()
        expired_rt.created_at = datetime.now(timezone.utc)
        expired_rt.updated_at = datetime.now(timezone.utc)
        expired_rt.user = user

        db = _mock_db_multi([expired_rt])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": raw_token},
            )
        assert resp.status_code == 401

    def test_refresh_with_revoked_token_returns_401(self):
        from src.auth.models import RefreshToken
        import hashlib

        user = _make_user()
        raw_token = "g" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        revoked_rt = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        revoked_rt.id = uuid.uuid4()
        revoked_rt.created_at = datetime.now(timezone.utc)
        revoked_rt.updated_at = datetime.now(timezone.utc)
        revoked_rt.user = user

        db = _mock_db_multi([revoked_rt])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": raw_token},
            )
        assert resp.status_code == 401


class TestLogoutEndpoint:
    """POST /auth/logout endpoint tests."""

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

    def test_logout_with_valid_token_returns_200(self):
        from src.auth.models import RefreshToken
        import hashlib

        user = _make_user()
        raw_token = "h" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        rt_obj = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=None,
        )
        rt_obj.id = uuid.uuid4()
        rt_obj.created_at = datetime.now(timezone.utc)
        rt_obj.updated_at = datetime.now(timezone.utc)
        rt_obj.user = user

        db = _mock_db_multi([rt_obj])
        db.flush = AsyncMock()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": raw_token},
            )
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_logout_with_unknown_token_still_returns_200(self):
        """Logout is idempotent -- unknown tokens should not reveal anything."""
        db = _mock_db(user=None)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": "completely-unknown-token"},
            )
        assert resp.status_code == 200


class TestLoginReturnsRefreshToken:
    """POST /auth/login should now include refresh_token in response."""

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

    def test_login_returns_both_tokens(self):
        user = _make_user()
        db = _mock_db(user=user)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"


class TestHttpOnlyCookie:
    """Login must set an HttpOnly cookie containing the access token."""

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

    def test_login_sets_httponly_access_token_cookie(self):
        """POST /auth/login must set Set-Cookie: access_token with HttpOnly flag."""
        user = _make_user()
        db = _mock_db(user=user)
        self._override_db(db)

        with TestClient(self.app, follow_redirects=False) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )

        assert resp.status_code == 200
        # The cookie must be present
        assert "access_token" in resp.cookies
        # The Set-Cookie header must contain HttpOnly
        set_cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower(), f"Expected HttpOnly in Set-Cookie but got: {set_cookie}"

    def test_login_cookie_samesite_and_path(self):
        """Set-Cookie header must include SameSite and Path attributes."""
        user = _make_user()
        db = _mock_db(user=user)
        self._override_db(db)

        with TestClient(self.app, follow_redirects=False) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )

        set_cookie = resp.headers.get("set-cookie", "")
        assert "samesite" in set_cookie.lower(), f"Expected SameSite in Set-Cookie but got: {set_cookie}"
        assert "path=/" in set_cookie.lower(), f"Expected Path=/ in Set-Cookie but got: {set_cookie}"

    def test_protected_endpoint_accepts_cookie_auth(self):
        """GET /auth/me must work when access token is supplied as a cookie."""
        user = _make_user()
        db = _mock_db(user=user)
        self._override_db(db)

        token = build_token(user)
        db.get = AsyncMock(return_value=user)

        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/auth/me",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    def test_logout_clears_access_token_cookie(self):
        """POST /auth/logout must clear the access_token cookie."""
        # Pass no user so scalar_one_or_none() returns None → revoke is a no-op
        db = _mock_db(user=None)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": "some-refresh-token"},
            )

        assert resp.status_code == 200
        # Cookie must be cleared (max-age=0 or expires in the past)
        set_cookie = resp.headers.get("set-cookie", "")
        assert set_cookie, "Expected Set-Cookie header on logout to clear access_token"
        assert "access_token" in set_cookie
        assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()

    def test_logout_without_refresh_token_still_clears_cookie(self):
        """POST /auth/logout with no refresh_token body must still clear the cookie."""
        db = _mock_db(user=None)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post("/api/v1/auth/logout", json={})

        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert set_cookie, "Expected Set-Cookie header on logout to clear access_token"
        assert "access_token" in set_cookie


# ---------------------------------------------------------------------------
# Admin unlock endpoint
# ---------------------------------------------------------------------------


class TestAdminUnlockEndpoint:
    """PATCH /auth/admin/unlock endpoint tests."""

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
            admin_user = _make_user()

        async def _fake_admin():
            return admin_user

        self.app.dependency_overrides[require_admin] = _fake_admin

    def test_admin_unlock_resets_lockout(self):
        """PATCH /admin/unlock must clear failed_login_attempts and locked_until."""
        # Use naive UTC to match the DB column (TIMESTAMP WITHOUT TIME ZONE)
        locked_until = datetime.utcnow() + timedelta(minutes=10)
        locked_user = _make_user(
            email="locked@example.com",
            failed_login_attempts=3,
            locked_until=locked_until,
        )
        db = _mock_db(user=locked_user)
        self._override_db(db)
        self._override_require_admin()

        with TestClient(self.app) as client:
            resp = client.patch(
                "/api/v1/auth/admin/unlock",
                json={"email": "locked@example.com"},
            )
        assert resp.status_code == 200
        assert locked_user.failed_login_attempts == 0
        assert locked_user.locked_until is None
        assert resp.json()["email"] == "locked@example.com"

    def test_unlock_nonexistent_user_returns_404(self):
        """PATCH /admin/unlock with unknown email must return 404."""
        db = _mock_db(user=None)
        self._override_db(db)
        self._override_require_admin()

        with TestClient(self.app) as client:
            resp = client.patch(
                "/api/v1/auth/admin/unlock",
                json={"email": "ghost@example.com"},
            )
        assert resp.status_code == 404

    def test_non_admin_unlock_returns_403(self):
        """PATCH /admin/unlock without admin role must return 403."""
        from src.auth.models import UserRole

        non_admin = _make_user(role=UserRole.SALES_MANAGER)
        token = build_token(non_admin)
        db = AsyncMock()
        db.get = AsyncMock(return_value=non_admin)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.patch(
                "/api/v1/auth/admin/unlock",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": "anyone@example.com"},
            )
        assert resp.status_code == 403


class TestLoginRateLimit:
    """A real E2E suite legitimately logs in far more than 10 times/minute
    across its full run (many specs, each with its own beforeEach login) —
    without this override, the CI E2E gate rate-limits itself into a stall
    (429s triggering widespread test retries/timeouts) rather than any
    genuine backend slowness."""

    def test_relaxed_when_e2e_flag_set(self, monkeypatch):
        from src.auth.router import _login_rate_limit
        from src.core.config import settings

        monkeypatch.setattr(settings, "E2E_RELAXED_LOGIN_RATE_LIMIT", True)
        assert _login_rate_limit() == "1000/minute"

    def test_stays_strict_by_default(self, monkeypatch):
        """Must never blanket-loosen the real brute-force protection —
        gated on the dedicated E2E flag, not ENVIRONMENT=test, since the
        plain backend pytest CI job also sets ENVIRONMENT=test and its own
        security regression tests specifically verify the strict limit."""
        from src.auth.router import _login_rate_limit
        from src.core.config import settings

        monkeypatch.setattr(settings, "E2E_RELAXED_LOGIN_RATE_LIMIT", False)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        assert _login_rate_limit() == "10/minute"

        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        assert _login_rate_limit() == "10/minute"
