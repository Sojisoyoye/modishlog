"""Tests for the settings domain — API key storage."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.models import User, UserRole
from src.auth.service import build_token, get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides) -> User:
    defaults = dict(
        email="settings-test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Settings Tester",
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


def _mock_db(existing_key=None) -> AsyncMock:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_key
    db.execute.return_value = result_mock
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


class TestApiKeyEndpoints:
    """POST /settings/api-key and GET /settings/api-key/{key_name}."""

    @pytest.fixture(autouse=True)
    def _setup(self):
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

    def _override_auth(self, user):
        from src.auth.dependencies import get_current_active_user

        async def _fake_user():
            return user

        self.app.dependency_overrides[get_current_active_user] = _fake_user

    # ------------------------------------------------------------------
    # POST /settings/api-key
    # ------------------------------------------------------------------

    def test_save_api_key_returns_is_configured_true(self):
        """POST /settings/api-key stores the key and returns is_configured=true."""
        user = _make_user()
        db = _mock_db(existing_key=None)
        self._override_db(db)
        self._override_auth(user)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/settings/api-key",
                json={"key_name": "anthropic", "key_value": "sk-ant-secret123"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["key_name"] == "anthropic"
        assert data["is_configured"] is True

    def test_save_api_key_does_not_echo_plaintext(self):
        """The response must never contain the raw key value."""
        user = _make_user()
        db = _mock_db(existing_key=None)
        self._override_db(db)
        self._override_auth(user)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/settings/api-key",
                json={"key_name": "anthropic", "key_value": "sk-ant-topsecret"},
            )

        body = resp.text
        assert "sk-ant-topsecret" not in body

    def test_save_api_key_stores_encrypted_not_plaintext(self):
        """The value stored in the DB must not be the plaintext key."""
        user = _make_user()
        db = _mock_db(existing_key=None)
        self._override_db(db)
        self._override_auth(user)

        with TestClient(self.app) as client:
            client.post(
                "/api/v1/settings/api-key",
                json={"key_name": "anthropic", "key_value": "sk-ant-plaintext"},
            )

        # db.add() should have been called with a UserApiKey whose encrypted_value is NOT the plaintext
        assert db.add.called
        stored_obj = db.add.call_args[0][0]
        assert stored_obj.encrypted_value != "sk-ant-plaintext"
        # Fernet ciphertext starts with 'gAAAAA'
        assert stored_obj.encrypted_value.startswith("gAAAAA")

    def test_save_api_key_requires_authentication(self):
        """POST /settings/api-key without auth returns 401."""
        db = _mock_db()
        self._override_db(db)
        # do NOT override auth — use real dependency which requires a valid token

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/settings/api-key",
                json={"key_name": "anthropic", "key_value": "sk-ant-test"},
            )

        assert resp.status_code == 401

    # ------------------------------------------------------------------
    # GET /settings/api-key/{key_name}
    # ------------------------------------------------------------------

    def test_get_api_key_status_configured(self):
        """GET /settings/api-key/anthropic returns is_configured=true when a key exists."""
        from src.settings.models import UserApiKey

        user = _make_user()
        existing = UserApiKey()
        existing.id = uuid.uuid4()
        existing.user_id = user.id
        existing.key_name = "anthropic"
        existing.encrypted_value = "gAAAAAsomefakeencryptedvalue"

        db = _mock_db(existing_key=existing)
        self._override_db(db)
        self._override_auth(user)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/settings/api-key/anthropic")

        assert resp.status_code == 200
        data = resp.json()
        assert data["key_name"] == "anthropic"
        assert data["is_configured"] is True
        assert "encrypted_value" not in data

    def test_get_api_key_status_not_configured(self):
        """GET /settings/api-key/anthropic returns is_configured=false when no key exists."""
        user = _make_user()
        db = _mock_db(existing_key=None)
        self._override_db(db)
        self._override_auth(user)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/settings/api-key/anthropic")

        assert resp.status_code == 200
        data = resp.json()
        assert data["key_name"] == "anthropic"
        assert data["is_configured"] is False

    def test_get_api_key_requires_authentication(self):
        """GET /settings/api-key/{key_name} without auth returns 401."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/settings/api-key/anthropic")

        assert resp.status_code == 401


class TestFernetEncryption:
    """Unit tests for the encryption helper in settings service."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted value decrypts back to the original plaintext."""
        from src.settings.service import decrypt_api_key, encrypt_api_key

        plaintext = "sk-ant-secret-key-12345"
        encrypted = encrypt_api_key(plaintext)
        assert encrypted != plaintext
        assert decrypt_api_key(encrypted) == plaintext

    def test_encrypt_produces_different_output_each_time(self):
        """Fernet uses a random IV so two encryptions of the same value differ."""
        from src.settings.service import encrypt_api_key

        e1 = encrypt_api_key("same-key")
        e2 = encrypt_api_key("same-key")
        assert e1 != e2
