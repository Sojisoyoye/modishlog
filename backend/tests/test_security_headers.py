"""Tests for security headers middleware and auth rate limiting."""

import pytest
from fastapi.testclient import TestClient


class TestSecurityHeaders:
    """Every response must include production-grade security headers."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_x_frame_options_deny(self):
        resp = self.client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options_nosniff(self):
        resp = self.client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy(self):
        resp = self.client.get("/health")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_content_security_policy_present(self):
        resp = self.client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp

    def test_x_xss_protection(self):
        resp = self.client.get("/health")
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_permissions_policy_present(self):
        resp = self.client.get("/health")
        assert "Permissions-Policy" in resp.headers

    def test_hsts_on_secure_responses(self):
        """HSTS header should be present (Nginx enforces it in prod; middleware adds it always for defence-in-depth)."""
        resp = self.client.get("/health")
        hsts = resp.headers.get("Strict-Transport-Security", "")
        assert "max-age" in hsts

    def test_server_header_removed(self):
        """Server header must not reveal uvicorn/FastAPI version."""
        resp = self.client.get("/health")
        server = resp.headers.get("Server", "")
        assert "uvicorn" not in server.lower()
        assert "fastapi" not in server.lower()

    def test_security_headers_on_api_endpoint(self):
        """Security headers must apply to API routes, not just /health."""
        resp = self.client.get("/api/v1/auth/me")
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"


class TestAuthRateLimiting:
    """Login and password-reset endpoints must enforce per-IP rate limits."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_login_rate_limit_after_many_requests(self):
        """After 10 rapid login attempts, the 11th should return 429."""
        payload = {"email": "noone@example.com", "password": "wrongpassword"}
        # Clear any state — send enough requests to exceed the 10/minute limit
        last_status = None
        for _ in range(12):
            resp = self.client.post("/api/v1/auth/login", json=payload)
            last_status = resp.status_code
        assert last_status == 429, (
            f"Expected 429 after 12 rapid login attempts, got {last_status}"
        )

    def test_forgot_password_rate_limit(self):
        """Forgot-password endpoint must also be rate-limited."""
        payload = {"email": "noone@example.com"}
        last_status = None
        for _ in range(12):
            resp = self.client.post("/api/v1/auth/forgot-password", json=payload)
            last_status = resp.status_code
        assert last_status == 429


class TestSensitiveDataLeakage:
    """Verify password hashes and internal tokens never appear in API responses."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_login_response_has_no_password_hash(self):
        """Token response must never contain hashed_password or password field."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "noone@example.com", "password": "wrongpassword"},
        )
        body_text = resp.text
        assert "hashed_password" not in body_text
        assert "$2b$" not in body_text  # bcrypt prefix

    def test_500_response_has_no_traceback(self):
        """500 error response must not leak internal traceback or module paths."""
        from src.main import app

        @app.get("/test-leak-route-sec")
        async def _leak():
            raise RuntimeError("internal leak test")

        try:
            resp = self.client.get("/test-leak-route-sec")
            assert resp.status_code == 500
            assert "RuntimeError" not in resp.text
            assert "Traceback" not in resp.text
            assert "/app/" not in resp.text
        finally:
            app.routes[:] = [
                r for r in app.routes
                if getattr(r, "path", "") != "/test-leak-route-sec"
            ]
