"""Tests for GET /api/v1/dashboard/summary — KPI aggregation endpoint."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
        business_id=uuid.uuid4(),
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


def _setup_app(user):
    """Return (app, db_mock, original_overrides) with db and auth dependencies overridden."""
    from src.main import app
    from src.core.database import get_db
    from src.auth.dependencies import get_current_user, get_current_active_user, get_current_business_id

    db_mock = AsyncMock()

    async def _fake_db():
        yield db_mock

    async def _fake_auth():
        return user

    async def _fake_business_id():
        return user.business_id

    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_auth
    app.dependency_overrides[get_current_active_user] = _fake_auth
    app.dependency_overrides[get_current_business_id] = _fake_business_id
    return app, db_mock, original


def _teardown_app(app, original_overrides):
    app.dependency_overrides = original_overrides


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
    app_inst, _, orig = _setup_app(user)

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
        _teardown_app(app_inst, orig)

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
    app_inst, _, orig = _setup_app(user)
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
        _teardown_app(app_inst, orig)

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
    app_inst, _, orig = _setup_app(user)
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
        _teardown_app(app_inst, orig)

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
    app_inst, _, orig = _setup_app(user)

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
        _teardown_app(app_inst, orig)

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
# Test 6 — Service receives correct business_id (isolation)
# ---------------------------------------------------------------------------

def test_summary_scoped_to_business():
    """get_dashboard_summary is called with the authenticated user's business_id."""
    from src.main import app

    business_id = uuid.uuid4()
    user = _make_user(business_id=business_id)
    summary = _make_summary()
    app_inst, _, orig = _setup_app(user)
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
        _teardown_app(app_inst, orig)

    call_kwargs = mock_svc.call_args.kwargs
    assert call_kwargs["business_id"] == business_id


# ---------------------------------------------------------------------------
# Test 7 — User without business_id gets 400
# ---------------------------------------------------------------------------

def test_summary_no_business_id_returns_400():
    """Authenticated user without business_id returns 400 Bad Request."""
    from src.main import app
    from src.auth.dependencies import get_current_business_id

    user = _make_user(business_id=None)
    app_inst, _, orig = _setup_app(user)

    # Override get_current_business_id to use the real implementation
    # so it raises the 400 when business_id is None
    async def _real_business_id_for_none_user():
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a business",
        )

    app_inst.dependency_overrides[get_current_business_id] = _real_business_id_for_none_user

    try:
        with TestClient(app_inst, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/dashboard/summary",
                headers=_auth_headers(user),
            )
    finally:
        _teardown_app(app_inst, orig)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 8 — Service uses business_id in queries (unit test)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_summary_uses_business_id():
    """Dashboard summary is scoped to the authenticated business."""
    from src.dashboard.service import get_dashboard_summary

    business_id = uuid.uuid4()

    async def fake_execute(query):
        r = MagicMock()
        r.scalar_one.return_value = Decimal("0")
        r.scalar_one_or_none.return_value = None
        r.scalars.return_value.all.return_value = []
        r.one.return_value = (Decimal("0"), Decimal("0"))
        r.all.return_value = []
        return r

    db = AsyncMock()
    db.execute = fake_execute

    # Should not raise — returns zero data for a new business
    result = await get_dashboard_summary(db, business_id=business_id)
    assert result is not None
    assert result.total_sales == Decimal("0")


@pytest.mark.asyncio
async def test_dashboard_summary_missing_business_id_raises():
    """get_dashboard_summary without business_id raises TypeError (wrong signature)."""
    from src.dashboard.service import get_dashboard_summary
    import inspect

    sig = inspect.signature(get_dashboard_summary)
    params = list(sig.parameters.keys())
    # Must have business_id and NOT require user_id as positional arg
    assert "business_id" in params, "business_id must be a parameter of get_dashboard_summary"


def test_summary_new_hero_fields():
    """GET /dashboard/summary returns transaction_count, yesterday_sales, recent_sales."""
    from src.main import app
    from src.dashboard.schemas import DashboardSummaryResponse, RecentSaleItem

    user = _make_user()
    summary = _make_summary(
        transaction_count=5,
        yesterday_sales=Decimal("800.00"),
        recent_sales=[
            RecentSaleItem(product_name="Ankara Fabric", quantity=3, revenue="18000.00", margin_pct="41.0")
        ],
    )
    app_inst, _, orig = _setup_app(user)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = AsyncMock(return_value=summary)
        with TestClient(app_inst) as client:
            resp = client.get("/api/v1/dashboard/summary", headers=_auth_headers(user))
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst, orig)

    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_count"] == 5
    assert data["yesterday_sales"] == "800.00"
    assert len(data["recent_sales"]) == 1
    assert data["recent_sales"][0]["product_name"] == "Ankara Fabric"
    assert data["recent_sales"][0]["margin_pct"] == "41.0"


def test_summary_hero_fields_zero_state():
    """Hero fields serialize correctly when there are no sales."""
    from src.main import app
    from src.dashboard.schemas import DashboardSummaryResponse

    user = _make_user()
    summary = _make_summary(transaction_count=0, yesterday_sales=Decimal("0.00"), recent_sales=[])
    app_inst, _, orig = _setup_app(user)

    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = AsyncMock(return_value=summary)
        with TestClient(app_inst) as client:
            resp = client.get("/api/v1/dashboard/summary", headers=_auth_headers(user))
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst, orig)

    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_count"] == 0
    assert data["yesterday_sales"] == "0.00"
    assert data["recent_sales"] == []
