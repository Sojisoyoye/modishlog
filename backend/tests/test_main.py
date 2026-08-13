"""Tests for application-level behaviour in src/main.py."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestStaticFileMount:
    """The uploads-directory static mount is wrapped in a try/except that
    tolerates a Docker named volume being root-owned on first run (CI
    without volume init) — but a real misconfigured production uploads
    volume must not fail silently with zero diagnostic trail (task 174)."""

    def test_mount_failure_is_logged_not_swallowed(self):
        from src.main import _mount_static_files

        fake_app = MagicMock()

        with patch("src.main.os.makedirs", side_effect=PermissionError("denied")), \
             patch("src.main.logger") as mock_logger:
            _mount_static_files(fake_app)

        mock_logger.error.assert_called_once()
        fake_app.mount.assert_not_called()

    def test_runtime_error_is_also_logged(self):
        from src.main import _mount_static_files

        fake_app = MagicMock()

        with patch("src.main.os.makedirs", side_effect=RuntimeError("boom")), \
             patch("src.main.logger") as mock_logger:
            _mount_static_files(fake_app)

        mock_logger.error.assert_called_once()

    def test_mount_succeeds_when_directory_is_writable(self):
        from src.main import _mount_static_files

        fake_app = MagicMock()

        with patch("src.main.os.makedirs"), \
             patch("src.main.logger") as mock_logger:
            _mount_static_files(fake_app)

        fake_app.mount.assert_called_once()
        mock_logger.error.assert_not_called()


class TestUnhandledExceptionHandler:
    def test_unhandled_exception_returns_generic_500(self):
        """A route that raises an unexpected RuntimeError must return 500 with
        a generic JSON body — no stack trace, no internal paths leaked."""
        from src.main import app

        # Temporarily add a route that always raises
        @app.get("/test-crash-route")
        async def _crash():
            raise RuntimeError("intentional crash for test")

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/test-crash-route")

            assert resp.status_code == 500
            body = resp.json()
            assert body == {"detail": "Internal server error"}
            assert "RuntimeError" not in resp.text
            assert "Traceback" not in resp.text
        finally:
            # Remove the temporary route so it doesn't leak into other tests
            app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != "/test-crash-route"]

    def test_http_exception_still_returns_correct_status(self):
        """HTTPException (e.g. 404) must NOT be swallowed by the catch-all handler."""
        from fastapi import HTTPException
        from src.main import app

        @app.get("/test-404-route")
        async def _not_found():
            raise HTTPException(status_code=404, detail="not found")

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/test-404-route")

            assert resp.status_code == 404
            assert resp.json()["detail"] == "not found"
        finally:
            app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != "/test-404-route"]


class TestCorsMiddlewareHeaders:
    def test_preflight_does_not_expose_wildcard_allow_headers(self):
        """CORS preflight must never advertise Access-Control-Allow-Headers: * —
        that combination with credentials is undefined per spec."""
        from src.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:4200",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
        assert resp.headers.get("Access-Control-Allow-Headers") != "*"

    def test_preflight_allows_authorization_header(self):
        """Preflight must explicitly list Authorization so Bearer token requests pass."""
        from src.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:4200",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
        allowed = resp.headers.get("Access-Control-Allow-Headers", "")
        assert "authorization" in allowed.lower()


class TestDataRouterAuthGates:
    """Verify every financial data router requires authentication.

    Each test confirms that a representative GET endpoint returns 401
    when called without a Bearer token.
    """

    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app
        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def test_sales_list_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/sales")
        assert resp.status_code == 401

    def test_orders_list_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/orders")
        assert resp.status_code == 401

    def test_cashflow_loans_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/cashflow/loans")
        assert resp.status_code == 401

    def test_inventory_list_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/inventory")
        assert resp.status_code == 401

    def test_pricing_recommendations_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/pricing/recommendations")
        assert resp.status_code == 401

    def test_fx_rates_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/fx/rates/current")
        assert resp.status_code == 401

    def test_ai_recommendations_unauthenticated_returns_401(self):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/ai/recommendations")
        assert resp.status_code == 401
