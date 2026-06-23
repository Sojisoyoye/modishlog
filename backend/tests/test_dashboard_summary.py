"""Tests for GET /api/v1/dashboard/summary — KPI aggregation endpoint."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash

import src.suppliers.models  # noqa: F401 — register Supplier mapper

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="dash@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Dash User",
        is_active=True,
        role=UserRole.ADMIN,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_summary(**overrides):
    from src.dashboard.schemas import DashboardSummaryResponse

    defaults = dict(
        total_sales=Decimal("1000.00"),
        net=Decimal("400.00"),
        invoice_due=Decimal("200.00"),
        total_sell_return=Decimal("50.00"),
        total_sell_return_paid=Decimal("30.00"),
        total_purchase=Decimal("500.00"),
        purchase_due=Decimal("150.00"),
        total_purchase_return=Decimal("25.00"),
        total_purchase_return_paid=Decimal("25.00"),
        expense=Decimal("100.00"),
    )
    defaults.update(overrides)
    return DashboardSummaryResponse(**defaults)


_saved_overrides: dict = {}


def _setup_app(user, summary_override=None, svc_mock=None):
    """Return a TestClient with db and auth dependencies overridden."""
    from src.main import app
    from src.core.database import get_db
    from src.auth.dependencies import get_current_user, get_current_active_user

    db_mock = AsyncMock()

    async def _fake_db():
        yield db_mock

    async def _fake_auth():
        return user

    _saved_overrides[id(app)] = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_auth
    app.dependency_overrides[get_current_active_user] = _fake_auth
    return app, db_mock


def _teardown_app(app):
    app.dependency_overrides = _saved_overrides.pop(id(app), {})


def _auth_headers(user):
    token = build_token(user)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test 1 — Happy path: all 10 KPI fields returned correctly
# ---------------------------------------------------------------------------

def test_summary_happy_path():
    """GET /dashboard/summary returns all 10 KPI fields for authenticated user."""
    from src.main import app
    from src.dashboard.service import get_dashboard_summary as real_svc

    user = _make_user()
    summary = _make_summary()
    app_inst, _ = _setup_app(user)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = AsyncMock(return_value=summary)

        with TestClient(app_inst) as client:
            resp = client.get(
                "/api/v1/dashboard/summary",
                headers=_auth_headers(user),
            )
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sales"] == "1000.00"
    assert data["net"] == "400.00"
    assert data["invoice_due"] == "200.00"
    assert data["total_sell_return"] == "50.00"
    assert data["total_sell_return_paid"] == "30.00"
    assert data["total_purchase"] == "500.00"
    assert data["purchase_due"] == "150.00"
    assert data["total_purchase_return"] == "25.00"
    assert data["total_purchase_return_paid"] == "25.00"
    assert data["expense"] == "100.00"


# ---------------------------------------------------------------------------
# Test 2 — Location filter forwarded to service
# ---------------------------------------------------------------------------

def test_summary_location_filter():
    """location_id query param is forwarded to get_dashboard_summary."""
    from src.main import app

    user = _make_user()
    loc_id = uuid.uuid4()
    summary = _make_summary(total_sales=Decimal("300.00"))
    app_inst, _ = _setup_app(user)
    mock_svc = AsyncMock(return_value=summary)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = mock_svc

        with TestClient(app_inst) as client:
            resp = client.get(
                f"/api/v1/dashboard/summary?location_id={loc_id}",
                headers=_auth_headers(user),
            )
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst)

    assert resp.status_code == 200
    call_kwargs = mock_svc.call_args.kwargs
    assert str(call_kwargs["location_id"]) == str(loc_id)


# ---------------------------------------------------------------------------
# Test 3 — Date filter forwarded to service
# ---------------------------------------------------------------------------

def test_summary_date_filter():
    """date_from and date_to query params are forwarded to get_dashboard_summary."""
    from src.main import app

    user = _make_user()
    summary = _make_summary()
    app_inst, _ = _setup_app(user)
    mock_svc = AsyncMock(return_value=summary)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = mock_svc

        with TestClient(app_inst) as client:
            resp = client.get(
                "/api/v1/dashboard/summary?date_from=2026-01-01&date_to=2026-01-31",
                headers=_auth_headers(user),
            )
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst)

    assert resp.status_code == 200
    call_kwargs = mock_svc.call_args.kwargs
    assert call_kwargs["date_from"] == date(2026, 1, 1)
    assert call_kwargs["date_to"] == date(2026, 1, 31)


# ---------------------------------------------------------------------------
# Test 4 — Empty state: all 10 fields are "0.00"
# ---------------------------------------------------------------------------

def test_summary_empty_state():
    """All fields return 0.00 when no transactions exist."""
    from src.main import app

    user = _make_user()
    empty = _make_summary(**{
        k: Decimal("0.00") for k in [
            "total_sales", "net", "invoice_due", "total_sell_return",
            "total_sell_return_paid", "total_purchase", "purchase_due",
            "total_purchase_return", "total_purchase_return_paid", "expense",
        ]
    })
    app_inst, _ = _setup_app(user)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = AsyncMock(return_value=empty)

        with TestClient(app_inst) as client:
            resp = client.get(
                "/api/v1/dashboard/summary",
                headers=_auth_headers(user),
            )
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst)

    assert resp.status_code == 200
    data = resp.json()
    for field in [
        "total_sales", "net", "invoice_due", "total_sell_return",
        "total_sell_return_paid", "total_purchase", "purchase_due",
        "total_purchase_return", "total_purchase_return_paid", "expense",
    ]:
        assert data[field] == "0.00", f"Expected 0.00 for {field}, got {data[field]}"


# ---------------------------------------------------------------------------
# Test 5 — Auth guard: no token → 401
# ---------------------------------------------------------------------------

def test_summary_auth_guard():
    """Unauthenticated request returns 401."""
    from src.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 6 — Service receives correct user_id (isolation)
# ---------------------------------------------------------------------------

def test_summary_scoped_to_user():
    """get_dashboard_summary is called with the authenticated user's id."""
    from src.main import app

    user = _make_user()
    summary = _make_summary()
    app_inst, _ = _setup_app(user)
    mock_svc = AsyncMock(return_value=summary)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = mock_svc

        with TestClient(app_inst) as client:
            client.get(
                "/api/v1/dashboard/summary",
                headers=_auth_headers(user),
            )
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst)

    call_kwargs = mock_svc.call_args.kwargs
    assert call_kwargs["user_id"] == user.id
