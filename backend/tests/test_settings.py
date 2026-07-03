"""Tests for the settings domain — API key storage."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.models import User, UserRole
from src.auth.service import get_password_hash

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

    def test_save_api_key_updates_existing_key(self):
        """POST /settings/api-key with an existing key updates it (upsert path)."""
        from src.settings.models import UserApiKey

        user = _make_user()
        existing = UserApiKey()
        existing.id = uuid.uuid4()
        existing.user_id = user.id
        existing.key_name = "anthropic"
        existing.encrypted_value = "gAAAAA_old_encrypted_value"

        db = _mock_db(existing_key=existing)
        self._override_db(db)
        self._override_auth(user)

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/settings/api-key",
                json={"key_name": "anthropic", "key_value": "sk-ant-new-value"},
            )

        assert resp.status_code == 200
        # UPDATE path: db.add() must NOT be called (no new row inserted)
        assert not db.add.called
        # The existing object's encrypted_value must have been replaced
        assert existing.encrypted_value != "gAAAAA_old_encrypted_value"
        assert existing.encrypted_value.startswith("gAAAAA")
        # db.flush() must have been called to persist the change
        db.flush.assert_called_once()


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

    def test_decrypt_invalid_token_raises_value_error(self):
        """decrypt_api_key raises ValueError (not cryptography.InvalidToken) on bad ciphertext."""
        from src.settings.service import decrypt_api_key

        with pytest.raises(ValueError, match="SECRET_KEY may have been rotated"):
            decrypt_api_key("not-a-valid-fernet-token")


# ---------------------------------------------------------------------------
# BusinessProfile service tests
# ---------------------------------------------------------------------------


def _mock_db_simple():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


class TestBusinessProfile:
    @pytest.mark.asyncio
    async def test_get_business_profile_returns_none_when_absent(self):
        """get_business_profile() returns None when no profile exists for this business."""
        from src.settings.service import get_business_profile

        business_id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        profile = await get_business_profile(db, business_id=business_id)
        assert profile is None
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_get_business_profile_returns_existing(self):
        """get_business_profile() returns the stored BusinessProfile when one exists."""
        from src.settings.models import BusinessProfile
        from src.settings.service import get_business_profile

        business_id = uuid.uuid4()
        existing = BusinessProfile(business_name="Ade Traders", currency="NGN", business_id=business_id)
        existing.id = uuid.uuid4()
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        profile = await get_business_profile(db, business_id=business_id)
        assert profile.business_name == "Ade Traders"

    @pytest.mark.asyncio
    async def test_update_business_profile_persists_all_fields(self):
        """update_business_profile() upserts and returns the updated profile."""
        from src.settings.models import BusinessProfile
        from src.settings.schemas import BusinessProfileUpdate
        from src.settings.service import update_business_profile

        business_id = uuid.uuid4()
        # Returned by the re-fetch SELECT after pg_insert upsert
        updated_profile = BusinessProfile(
            business_name="New Name", currency="USD", business_id=business_id
        )
        updated_profile.id = uuid.uuid4()
        updated_profile.tax_number = "TIN-12345"
        updated_profile.created_at = datetime.now(timezone.utc)
        updated_profile.updated_at = datetime.now(timezone.utc)

        # execute call 1: pg_insert (result is ignored)
        insert_result = MagicMock()
        # execute call 2: re-fetch SELECT returns updated_profile
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = updated_profile

        db = _mock_db_simple()
        db.execute = AsyncMock(side_effect=[insert_result, fetch_result])

        data = BusinessProfileUpdate(
            business_name="New Name",
            currency="USD",
            tax_number="TIN-12345",
        )
        result = await update_business_profile(db, data, user_id=uuid.uuid4(), business_id=business_id)
        assert result.business_name == "New Name"
        assert result.currency == "USD"
        assert result.tax_number == "TIN-12345"
        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# AppSetting service tests
# ---------------------------------------------------------------------------


class TestAppSettings:
    @pytest.mark.asyncio
    async def test_get_app_settings_returns_defaults_when_absent(self):
        """get_app_settings() returns all default key/value pairs when table is empty."""
        from src.settings.service import get_app_settings

        business_id = uuid.uuid4()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        settings_dict = await get_app_settings(db, business_id=business_id)
        assert "global_low_stock_threshold" in settings_dict
        assert "default_currency_pair" in settings_dict
        assert settings_dict["global_low_stock_threshold"] == "10"
        assert settings_dict["default_currency_pair"] == "USDNGN"

    @pytest.mark.asyncio
    async def test_update_app_setting_persists_value(self):
        """update_app_setting() upserts via pg_insert and flushes."""
        from src.settings.service import update_app_setting

        business_id = uuid.uuid4()
        result_mock = MagicMock()
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        await update_app_setting(
            db, "global_low_stock_threshold", "25", user_id=uuid.uuid4(), business_id=business_id
        )
        # pg_insert path: db.execute is called once (pg_insert), db.add is NOT called
        db.execute.assert_called_once()
        db.add.assert_not_called()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_app_setting_updates_existing(self):
        """update_app_setting() uses pg_insert on_conflict_do_update (single execute)."""
        from src.settings.service import update_app_setting

        business_id = uuid.uuid4()
        result_mock = MagicMock()
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        await update_app_setting(
            db, "global_low_stock_threshold", "50", user_id=uuid.uuid4(), business_id=business_id
        )
        # pg_insert path: single execute, no separate SELECT
        db.execute.assert_called_once()
        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Business isolation tests
# ---------------------------------------------------------------------------


class TestBusinessProfileIsolation:
    @pytest.mark.asyncio
    async def test_business_profile_isolates_by_business(self):
        """Each business gets its own profile, not the global one."""
        from src.settings.service import get_business_profile

        business_a_id = uuid.uuid4()
        business_b_id = uuid.uuid4()

        profile_a = MagicMock()
        profile_a.id = uuid.uuid4()

        async def fake_execute_a(query):
            r = MagicMock()
            r.scalar_one_or_none.return_value = profile_a
            return r

        async def fake_execute_b(query):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        db_a, db_b = AsyncMock(), AsyncMock()
        db_a.execute = fake_execute_a
        db_b.execute = fake_execute_b
        db_a.flush = AsyncMock()
        db_b.flush = AsyncMock()
        db_a.add = MagicMock()
        db_b.add = MagicMock()

        result_a = await get_business_profile(db_a, business_id=business_a_id)
        result_b = await get_business_profile(db_b, business_id=business_b_id)
        assert result_a is profile_a
        assert result_b is None  # business_b has no profile yet

    @pytest.mark.asyncio
    async def test_update_business_profile_scoped_to_business(self):
        """update_business_profile() upserts a new row scoped to the given business_id."""
        from src.settings.models import BusinessProfile
        from src.settings.schemas import BusinessProfileUpdate
        from src.settings.service import update_business_profile

        business_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Re-fetch after upsert returns this profile
        fetched = BusinessProfile(business_name="My Shop", currency="NGN", business_id=business_id)
        fetched.id = uuid.uuid4()
        fetched.created_at = datetime.now(timezone.utc)
        fetched.updated_at = datetime.now(timezone.utc)

        insert_result = MagicMock()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = fetched

        db = _mock_db_simple()
        db.execute = AsyncMock(side_effect=[insert_result, fetch_result])

        data = BusinessProfileUpdate(business_name="My Shop", currency="NGN")
        profile = await update_business_profile(db, data, user_id=user_id, business_id=business_id)
        assert profile.business_name == "My Shop"
        assert profile.business_id == business_id
        # pg_insert path: db.add is NOT called, execute called twice (INSERT + SELECT)
        db.add.assert_not_called()
        assert db.execute.call_count == 2
        db.flush.assert_called_once()


class TestAppSettingIsolation:
    @pytest.mark.asyncio
    async def test_app_settings_isolates_by_business(self):
        """Each business gets its own app settings."""
        from src.settings.service import get_app_setting

        business_a_id = uuid.uuid4()
        business_b_id = uuid.uuid4()
        key = "theme"

        async def fake_execute_a(query):
            r = MagicMock()
            r.scalar_one_or_none.return_value = MagicMock(value="dark")
            return r

        async def fake_execute_b(query):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        db_a, db_b = AsyncMock(), AsyncMock()
        db_a.execute = fake_execute_a
        db_b.execute = fake_execute_b

        result_a = await get_app_setting(db_a, key=key, business_id=business_a_id)
        result_b = await get_app_setting(db_b, key=key, business_id=business_b_id)
        assert result_a is not None
        assert result_b is None

    @pytest.mark.asyncio
    async def test_get_app_settings_scoped_to_business(self):
        """get_app_settings() returns only rows for the given business_id."""
        from src.settings.models import AppSetting
        from src.settings.service import get_app_settings

        business_id = uuid.uuid4()
        row = AppSetting(key="global_low_stock_threshold", value="5")
        row.updated_at = datetime.now(timezone.utc)

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [row]
        result_mock.scalars.return_value = scalars_mock
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        settings_dict = await get_app_settings(db, business_id=business_id)
        assert settings_dict["global_low_stock_threshold"] == "5"

    @pytest.mark.asyncio
    async def test_update_app_setting_scoped_to_business(self):
        """update_app_setting() upserts via pg_insert scoped to business_id."""
        from src.settings.service import update_app_setting

        business_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result_mock = MagicMock()
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        await update_app_setting(
            db, "global_low_stock_threshold", "25", user_id=user_id, business_id=business_id
        )
        # pg_insert path: single execute (INSERT ON CONFLICT), no db.add
        db.add.assert_not_called()
        db.execute.assert_called_once()
        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Test API key endpoint
# ---------------------------------------------------------------------------


class TestApiKeyTest:
    @pytest.mark.asyncio
    async def test_test_api_key_returns_success_true_on_valid_key(self):
        """test_anthropic_api_key() returns success=True when key decrypts and works."""
        from unittest.mock import patch

        from src.settings.models import UserApiKey
        from src.settings.service import test_anthropic_api_key

        existing = UserApiKey()
        existing.id = uuid.uuid4()
        existing.key_name = "anthropic"
        existing.encrypted_value = "gAAAAAsomefakeencryptedvalue"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db = _mock_db_simple()
        db.execute.return_value = result_mock

        with patch(
            "src.settings.service.decrypt_api_key", return_value="sk-test-valid"
        ), patch(
            "src.settings.service._call_anthropic_api", return_value=True
        ):
            result = await test_anthropic_api_key(db=db, user_id=uuid.uuid4())
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_test_api_key_returns_failure_when_not_configured(self):
        """test_anthropic_api_key() returns success=False if no key is stored."""
        from src.settings.service import test_anthropic_api_key

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None  # no key stored
        db = _mock_db_simple()
        db.execute = AsyncMock(return_value=result_mock)

        result = await test_anthropic_api_key(db=db, user_id=uuid.uuid4())
        assert result["success"] is False
        assert "not configured" in result["message"].lower()
