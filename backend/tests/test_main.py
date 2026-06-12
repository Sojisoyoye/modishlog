"""Tests for application-level behaviour in src/main.py."""

import pytest
from fastapi.testclient import TestClient


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
