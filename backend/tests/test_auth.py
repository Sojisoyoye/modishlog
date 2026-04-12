"""Tests for the authentication system."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

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
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(db, user.email, "WrongPassword!1")
        assert user.failed_login_attempts == 1

    @pytest.mark.asyncio
    async def test_lockout_after_threshold(self):
        user = _make_user(failed_login_attempts=LOCKOUT_THRESHOLD - 1)
        db = _mock_db(user=user)
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(db, user.email, "WrongPassword!1")
        assert user.locked_until is not None

    @pytest.mark.asyncio
    async def test_locked_account_raises(self):
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        user = _make_user(locked_until=locked_until)
        db = _mock_db(user=user)
        with pytest.raises(AccountLockedError) as exc_info:
            await authenticate_user(db, user.email, VALID_PASSWORD)
        assert exc_info.value.locked_until == locked_until

    @pytest.mark.asyncio
    async def test_expired_lockout_allows_login(self):
        expired = datetime.now(timezone.utc) - timedelta(minutes=1)
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

    def test_login_locked_account_403(self):
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        user = _make_user(locked_until=locked_until)
        db = _mock_db(user=user)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": VALID_PASSWORD},
            )
        assert resp.status_code == 403
        assert "locked" in resp.json()["detail"].lower()

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
        assert len(token_str) == 32  # uuid4 hex
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
