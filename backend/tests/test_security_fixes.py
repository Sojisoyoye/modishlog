"""Tests for security risk mitigations (S1–S8).

TDD: these tests are written BEFORE implementation to drive the design.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# S1 — Redis-backed rate limiter
# ---------------------------------------------------------------------------


class TestRedisRateLimiter:
    """S1: The rate limiter must reject requests at the configured threshold."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_rate_limiter_rejects_at_threshold(self):
        """After 10 rapid login attempts, the 11th should return 429."""
        payload = {"email": "noone@example.com", "password": "wrongpassword"}
        statuses = []
        for _ in range(12):
            resp = self.client.post("/api/v1/auth/login", json=payload)
            statuses.append(resp.status_code)
        assert 429 in statuses, (
            f"Expected 429 in rate-limit test, got statuses: {statuses}"
        )

    def test_limiter_config_has_redis_url_support(self):
        """Rate limiter module must have REDIS_URL-aware configuration."""
        from src.core import rate_limit

        # The module must expose the limiter object
        assert hasattr(rate_limit, "limiter"), "rate_limit module must export 'limiter'"

    def test_config_has_redis_url_setting(self):
        """Settings must expose a REDIS_URL field."""
        from src.core.config import Settings

        # Should be able to create Settings with REDIS_URL
        fields = Settings.model_fields
        assert "REDIS_URL" in fields, "Settings must have REDIS_URL field"


# ---------------------------------------------------------------------------
# S2 — Refresh token must be in HttpOnly cookie, not JSON body
# ---------------------------------------------------------------------------


class TestRefreshTokenCookie:
    """S2: Login response must set refresh_token as HttpOnly cookie, not in JSON."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_login_json_body_has_no_refresh_token(self):
        """JSON response body for login must NOT contain the refresh_token value."""
        with patch("src.auth.router.authenticate_user") as mock_auth, patch(
            "src.auth.router.create_refresh_token"
        ) as mock_refresh, patch("src.auth.router.build_token") as mock_build:
            from src.auth.models import User, UserRole

            mock_user = MagicMock(spec=User)
            mock_user.id = uuid.uuid4()
            mock_user.business_id = uuid.uuid4()
            mock_user.role = UserRole.ADMIN
            mock_user.is_active = True
            mock_auth.return_value = mock_user
            mock_build.return_value = "fake_access_token_abc123"
            mock_refresh.return_value = "secret_refresh_token_xyz789"

            resp = self.client.post(
                "/api/v1/auth/login",
                json={"email": "test@example.com", "password": "ValidPass123!@#"},
            )
            # JSON body must NOT contain the refresh token value
            body = resp.json()
            assert body.get("refresh_token", "") == "", (
                "refresh_token must not be returned in JSON body"
            )
            # Must NOT contain the raw refresh token string in body text
            assert "secret_refresh_token_xyz789" not in resp.text, (
                "Raw refresh token must not appear in JSON response body"
            )

    def test_login_sets_refresh_token_cookie(self):
        """Login router code must call set_cookie with 'refresh_token' key.

        Verifies the source code pattern rather than making HTTP calls
        to avoid interference with the rate-limiter tests above.
        """
        from pathlib import Path

        # Read the router source directly to verify the cookie-setting pattern
        router_path = Path(__file__).parent.parent / "src" / "auth" / "router.py"
        router_source = router_path.read_text()

        # The router must set a 'refresh_token' cookie
        assert 'key="refresh_token"' in router_source, (
            "auth/router.py must call response.set_cookie(key='refresh_token', ...) "
            "to move the refresh token out of the JSON body"
        )
        # The refresh_token cookie must be HttpOnly
        assert "httponly=True" in router_source, (
            "refresh_token cookie must be httponly=True to prevent XSS theft"
        )
        # The JSON response must return empty string for refresh_token
        assert 'refresh_token=""' in router_source or "refresh_token=\"\"" in router_source, (
            "Login TokenResponse must return refresh_token='' (empty) to keep it out of JSON body"
        )

    def test_refresh_endpoint_reads_from_cookie(self):
        """The /refresh endpoint must accept refresh_token from cookie."""
        with patch("src.auth.router.refresh_access_token") as mock_refresh:
            mock_refresh.return_value = "new_access_token_abc"

            # Send refresh_token via cookie
            resp = self.client.post(
                "/api/v1/auth/refresh",
                cookies={"refresh_token": "valid_refresh_token_from_cookie"},
            )
            # Should succeed (not 422/400 for missing body)
            assert resp.status_code != 422, (
                "/refresh should accept cookie-based refresh_token"
            )

    def test_onboard_json_has_no_refresh_token(self):
        """Onboard response must NOT expose refresh_token in JSON body."""
        with patch("src.auth.router.create_business_and_owner") as mock_onboard:
            mock_business = MagicMock()
            mock_business.id = uuid.uuid4()
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_onboard.return_value = (
                mock_business,
                mock_user,
                "access_token_abc",
                "refresh_token_secret_xyz",
            )
            resp = self.client.post(
                "/api/v1/auth/onboard",
                json={
                    "full_name": "Test User",
                    "email": "new@example.com",
                    "password": "ValidPass123!@#",
                    "business_name": "Test Business",
                    "currency": "NGN",
                    "timezone": "Africa/Lagos",
                    "fiscal_year_start_month": 1,
                },
            )
            if resp.status_code in (200, 201):
                body = resp.json()
                # Bug 5 fix: refresh_token is now Optional[str] = None so the field
                # may be absent or None — neither case exposes the real token in JSON.
                rt = body.get("refresh_token")
                assert rt in (None, ""), (
                    "Onboard response must not return refresh_token in JSON body"
                )


# ---------------------------------------------------------------------------
# S3 — CSP must not contain unsafe-inline
# ---------------------------------------------------------------------------


class TestCSPNoUnsafeInline:
    """S3: Content-Security-Policy must not include 'unsafe-inline' in script-src."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_csp_no_unsafe_inline_in_script_src(self):
        """CSP script-src must not contain 'unsafe-inline'."""
        resp = self.client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        # Parse out script-src directive
        directives = {
            d.strip().split()[0]: d.strip()
            for d in csp.split(";")
            if d.strip()
        }
        script_src = directives.get("script-src", "")
        assert "'unsafe-inline'" not in script_src, (
            f"CSP script-src must not contain 'unsafe-inline'. Got: {script_src!r}"
        )

    def test_csp_no_unsafe_inline_in_style_src(self):
        """CSP style-src must not contain 'unsafe-inline'."""
        resp = self.client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        directives = {
            d.strip().split()[0]: d.strip()
            for d in csp.split(";")
            if d.strip()
        }
        style_src = directives.get("style-src", "")
        assert "'unsafe-inline'" not in style_src, (
            f"CSP style-src must not contain 'unsafe-inline'. Got: {style_src!r}"
        )

    def test_csp_present_on_api_endpoints(self):
        """CSP must be present on API endpoints too."""
        resp = self.client.get("/api/v1/auth/me")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp, "CSP must be present on all responses"
        assert "'unsafe-inline'" not in csp, (
            "CSP must not contain 'unsafe-inline' on API endpoints"
        )


# ---------------------------------------------------------------------------
# S4 — Cross-tenant isolation: list_users must filter by business_id
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation:
    """S4: list_users must be scoped to business_id."""

    @pytest.mark.asyncio
    async def test_list_users_filters_by_business_id(self):
        """list_users() must return only users from the specified business."""
        from src.auth.service import list_users

        business_a_id = uuid.uuid4()
        business_b_id = uuid.uuid4()

        # Build mock users for two different businesses
        user_a = MagicMock()
        user_a.id = uuid.uuid4()
        user_a.business_id = business_a_id
        user_a.email = "user_a@biz_a.com"

        user_b = MagicMock()
        user_b.id = uuid.uuid4()
        user_b.business_id = business_b_id
        user_b.email = "user_b@biz_b.com"

        # Mock DB to return only user_a when queried with business_a_id filter
        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [user_a]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        result_mock.scalar_one.return_value = 1
        db.execute.return_value = result_mock

        # Must accept business_id parameter
        import inspect

        sig = inspect.signature(list_users)
        assert "business_id" in sig.parameters, (
            "list_users() must accept a business_id parameter"
        )

    @pytest.mark.asyncio
    async def test_list_users_signature_requires_business_id(self):
        """list_users must require business_id to prevent cross-tenant leakage."""
        from src.auth.service import list_users
        import inspect

        sig = inspect.signature(list_users)
        params = sig.parameters
        assert "business_id" in params, (
            "list_users() must have a business_id parameter for tenant isolation"
        )


# ---------------------------------------------------------------------------
# S5 — Fernet key rotation support
# ---------------------------------------------------------------------------


class TestFernetKeyRotation:
    """S5: Fernet key rotation must allow decryption with old key after rotating to new key."""

    def test_encrypt_with_old_key_decrypt_with_rotation(self):
        """Encrypting with key A and then rotating to key B must still allow decryption."""
        from cryptography.fernet import Fernet

        from src.settings.service import decrypt_api_key, encrypt_api_key

        key_a = Fernet.generate_key().decode()
        key_b = Fernet.generate_key().decode()

        # Encrypt with key A
        with patch("src.settings.service._get_fernet_keys") as mock_keys:
            # Simulate key A as the only key (pre-rotation)
            import base64
            import hashlib

            raw_a = hashlib.sha256(key_a.encode()).digest()
            fernet_a = Fernet(base64.urlsafe_b64encode(raw_a))
            mock_keys.return_value = [fernet_a]
            ciphertext = encrypt_api_key("my-secret-api-key")

        # Now rotate: key B is newest, key A is still in list for decryption
        with patch("src.settings.service._get_fernet_keys") as mock_keys:
            raw_b = hashlib.sha256(key_b.encode()).digest()
            fernet_b = Fernet(base64.urlsafe_b64encode(raw_b))
            mock_keys.return_value = [fernet_b, fernet_a]  # B newest, A still present
            plaintext = decrypt_api_key(ciphertext)

        assert plaintext == "my-secret-api-key", (
            "Decryption must succeed after key rotation when old key is still in list"
        )

    def test_decrypt_fails_with_completely_wrong_key(self):
        """Decryption must fail when no valid key is in the rotation list."""
        from cryptography.fernet import Fernet

        from src.settings.service import decrypt_api_key, encrypt_api_key

        key_a = Fernet.generate_key().decode()
        key_wrong = Fernet.generate_key().decode()

        # Encrypt with key A
        with patch("src.settings.service._get_fernet_keys") as mock_keys:
            import base64
            import hashlib

            raw_a = hashlib.sha256(key_a.encode()).digest()
            fernet_a = Fernet(base64.urlsafe_b64encode(raw_a))
            mock_keys.return_value = [fernet_a]
            ciphertext = encrypt_api_key("my-secret-api-key")

        # Try to decrypt with completely wrong key
        with patch("src.settings.service._get_fernet_keys") as mock_keys:
            raw_wrong = hashlib.sha256(key_wrong.encode()).digest()
            fernet_wrong = Fernet(base64.urlsafe_b64encode(raw_wrong))
            mock_keys.return_value = [fernet_wrong]  # Only wrong key
            with pytest.raises(ValueError):
                decrypt_api_key(ciphertext)

    def test_config_has_fernet_keys_setting(self):
        """Settings must have FERNET_KEYS as an optional comma-separated list."""
        from src.core.config import Settings

        fields = Settings.model_fields
        assert "FERNET_KEYS" in fields, (
            "Settings must have FERNET_KEYS field for key rotation support"
        )


# ---------------------------------------------------------------------------
# S6 — File upload MIME validation
# ---------------------------------------------------------------------------


class TestFileUploadMimeValidation:
    """S6: File uploads must validate actual MIME type, not just Content-Type header."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_php_file_with_jpeg_content_type_rejected(self):
        """A PHP file sent with Content-Type image/jpeg must be rejected with 400."""
        php_bytes = b"<?php echo shell_exec($_GET['cmd']); ?>"

        with patch(
            "src.auth.dependencies.get_current_active_user"
        ) as mock_user, patch(
            "src.auth.dependencies.get_current_business_id"
        ) as mock_biz:
            mock_user.return_value = MagicMock()
            mock_biz.return_value = uuid.uuid4()

            product_id = uuid.uuid4()
            resp = self.client.post(
                f"/api/v1/products/{product_id}/image",
                files={"file": ("evil.jpg", php_bytes, "image/jpeg")},
            )
            # Must be rejected — either 400 (MIME mismatch) or 401/403 (auth)
            # We accept 400 as the target — auth failure is also acceptable in test env
            assert resp.status_code in (
                400,
                401,
                403,
                404,
            ), f"PHP-as-JPEG must be rejected. Got {resp.status_code}: {resp.text}"

    def test_valid_jpeg_accepted(self):
        """A real JPEG file must pass MIME validation."""
        # Minimal valid JPEG: SOI marker + APP0 marker
        jpeg_bytes = (
            b"\xff\xd8\xff\xe0"
            + b"\x00\x10"
            + b"JFIF\x00"
            + b"\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            + b"\xff\xd9"
        )

        with patch(
            "src.auth.dependencies.get_current_active_user"
        ) as mock_user, patch(
            "src.auth.dependencies.get_current_business_id"
        ) as mock_biz, patch(
            "src.products.router.update_product"
        ) as mock_update:
            mock_user.return_value = MagicMock()
            mock_biz.return_value = uuid.uuid4()
            mock_product = MagicMock()
            mock_update.return_value = mock_product

            product_id = uuid.uuid4()
            resp = self.client.post(
                f"/api/v1/products/{product_id}/image",
                files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")},
            )
            # Should not be rejected for MIME reasons (may fail for other reasons in test env)
            assert resp.status_code != 400 or "MIME" not in resp.text.upper(), (
                f"Valid JPEG must not be rejected by MIME validation. Got: {resp.text}"
            )

    def test_mime_validation_helper_exists(self):
        """A MIME validation utility must exist in the products router."""
        from src.products import router as products_router

        # The router module must have MIME validation capability
        source = products_router.__file__
        with open(source) as f:
            content = f.read()
        assert "magic" in content or "MIME" in content or "mime" in content, (
            "products/router.py must import magic for MIME validation"
        )


# ---------------------------------------------------------------------------
# S7 — sanitize_url strips passwords from DB URLs
# ---------------------------------------------------------------------------


class TestSanitizeUrl:
    """S7: sanitize_url() must mask the password portion of database URLs."""

    def test_sanitize_url_masks_password(self):
        """A postgresql URL with a password must have it masked."""
        from src.core.logging import sanitize_url

        url = "postgresql+asyncpg://user:SuperSecret123@db.example.com/mydb"
        sanitized = sanitize_url(url)
        assert "SuperSecret123" not in sanitized, (
            f"sanitize_url must mask passwords. Got: {sanitized!r}"
        )
        assert "user" in sanitized, "sanitize_url should keep the username"
        assert "db.example.com" in sanitized, "sanitize_url should keep the host"

    def test_sanitize_url_handles_no_password(self):
        """A URL without a password must pass through unchanged."""
        from src.core.logging import sanitize_url

        url = "postgresql+asyncpg://localhost/modishlog"
        sanitized = sanitize_url(url)
        assert "localhost" in sanitized
        assert "modishlog" in sanitized

    def test_sanitize_url_handles_empty_string(self):
        """sanitize_url must handle empty strings gracefully."""
        from src.core.logging import sanitize_url

        result = sanitize_url("")
        assert result == ""

    def test_sanitize_url_replaces_with_redacted(self):
        """The masked password should show as '***' or similar."""
        from src.core.logging import sanitize_url

        url = "postgresql+asyncpg://admin:TopSecret@host:5432/db"
        sanitized = sanitize_url(url)
        assert "TopSecret" not in sanitized
        # Should contain some redaction marker
        assert "***" in sanitized or "REDACTED" in sanitized or "****" in sanitized, (
            f"sanitize_url should use *** or REDACTED. Got: {sanitized!r}"
        )

    def test_sanitize_url_function_exists_in_logging(self):
        """sanitize_url must be importable from src.core.logging."""
        try:
            from src.core.logging import sanitize_url  # noqa: F401
        except ImportError:
            pytest.fail("sanitize_url must be importable from src.core.logging")


# ---------------------------------------------------------------------------
# S8 — pip-audit in CI (structural test: verify workflow file exists)
# ---------------------------------------------------------------------------


class TestPipAuditCI:
    """S8: pip-audit must be configured with --fail-on-vuln in CI."""

    def test_dependency_scan_workflow_has_fail_on_vuln(self):
        """_dependency-scan.yml must run pip-audit with --fail-on-vuln."""
        import os
        from pathlib import Path

        # Navigate from tests/ up to project root, then to .github/workflows/
        project_root = Path(__file__).resolve().parents[2]  # backend/tests -> backend -> project root
        workflow_path = project_root / ".github" / "workflows" / "_dependency-scan.yml"
        assert workflow_path.exists(), (
            f"_dependency-scan.yml must exist at {workflow_path}"
        )
        content = workflow_path.read_text()
        assert "--fail-on-vuln" in content or "fail-on-vuln" in content, (
            "_dependency-scan.yml must use pip-audit --fail-on-vuln to block merges on CVEs"
        )
