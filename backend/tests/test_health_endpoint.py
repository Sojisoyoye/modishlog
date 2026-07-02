"""Tests for the enhanced /health and /api/health endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


class TestHealthEndpoint:
    @pytest.fixture(autouse=True)
    def _client(self):
        from src.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health_returns_200(self):
        with patch("src.health.router.check_db", new=AsyncMock(return_value="ok")):
            resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_json(self):
        with patch("src.health.router.check_db", new=AsyncMock(return_value="ok")):
            resp = self.client.get("/health")
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["db"] == "ok"
        assert "version" in body

    def test_health_includes_db_status(self):
        with patch("src.health.router.check_db", new=AsyncMock(return_value="ok")):
            resp = self.client.get("/health")
        assert "db" in resp.json()

    def test_health_includes_version(self):
        with patch("src.health.router.check_db", new=AsyncMock(return_value="ok")):
            resp = self.client.get("/health")
        assert "version" in resp.json()

    def test_api_health_alias_returns_200(self):
        """/api/health must also be accessible (for monitoring tools that expect this path)."""
        with patch("src.health.router.check_db", new=AsyncMock(return_value="ok")):
            resp = self.client.get("/api/health")
        assert resp.status_code == 200

    def test_health_db_ok_when_db_reachable(self):
        """When DB ping succeeds, db field reports 'ok'."""
        with patch("src.health.router.check_db", new=AsyncMock(return_value="ok")):
            resp = self.client.get("/health")
        assert resp.json().get("db") == "ok"

    def test_health_returns_503_when_db_fails(self):
        """When the DB ping raises, health returns 503 with status=degraded."""
        from src.main import app
        from sqlalchemy.exc import OperationalError

        with patch(
            "src.health.router.check_db",
            new=AsyncMock(side_effect=OperationalError("conn", None, None)),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"

    def test_health_no_auth_required(self):
        """Health endpoint must be publicly accessible — no auth header needed."""
        resp = self.client.get("/health")
        assert resp.status_code != 401
        assert resp.status_code != 403
