"""TDD tests for purchase returns list/read endpoints (task #162)."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import src.suppliers.models  # noqa: F401 — registers Supplier mapper for PurchaseOrder relationship
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test User",
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


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _make_purchase_return(**overrides):
    from src.orders.models import PurchaseReturn

    defaults = dict(
        original_order_id=uuid.uuid4(),
        ref_no=f"RET-2026-{uuid.uuid4().hex[:8].upper()}",
        return_date=date(2026, 6, 1),
        notes="Damaged goods",
        total_amount=Decimal("50000.000000"),
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    pr = PurchaseReturn(**defaults)
    pr.id = overrides.get("id", uuid.uuid4())
    pr.created_at = datetime.now(timezone.utc)
    pr.updated_at = datetime.now(timezone.utc)
    return pr


# ---------------------------------------------------------------------------
# Service-layer unit tests
# ---------------------------------------------------------------------------


class TestListPurchaseReturnsService:
    @pytest.mark.asyncio
    async def test_list_purchase_returns_returns_all(self):
        """list_purchase_returns returns (items, total) for all returns."""
        from src.orders.service import list_purchase_returns

        pr1 = _make_purchase_return()
        pr2 = _make_purchase_return()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 2

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [pr1, pr2]

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        items, total = await list_purchase_returns(db)

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_purchase_returns_filtered_by_order(self):
        """list_purchase_returns with order_id filters to that order's returns."""
        from src.orders.service import list_purchase_returns

        order_id = uuid.uuid4()
        pr = _make_purchase_return(original_order_id=order_id)

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [pr]

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        items, total = await list_purchase_returns(db, order_id=order_id)

        assert total == 1
        assert items[0].original_order_id == order_id

    @pytest.mark.asyncio
    async def test_list_purchase_returns_empty(self):
        """list_purchase_returns returns empty list when no returns exist."""
        from src.orders.service import list_purchase_returns

        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = []

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        items, total = await list_purchase_returns(db)

        assert total == 0
        assert items == []


class TestGetPurchaseReturnService:
    @pytest.mark.asyncio
    async def test_get_purchase_return_found(self):
        """get_purchase_return returns the return when it exists."""
        from src.orders.service import get_purchase_return

        pr = _make_purchase_return()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = pr

        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        found = await get_purchase_return(db, pr.id)

        assert found.id == pr.id
        assert found.ref_no == pr.ref_no

    @pytest.mark.asyncio
    async def test_get_purchase_return_not_found(self):
        """get_purchase_return raises PurchaseReturnNotFoundError for unknown id."""
        from src.orders.exceptions import PurchaseReturnNotFoundError
        from src.orders.service import get_purchase_return

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None

        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(PurchaseReturnNotFoundError):
            await get_purchase_return(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


class TestPurchaseReturnEndpoints:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.main import app

        self.app = app
        self._orig = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._orig

    def _override_db(self, db):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        async def _fake_db():
            yield db

        u = _make_user()
        business_id = u.business_id

        self.app.dependency_overrides[get_db] = _fake_db
        self.app.dependency_overrides[get_current_active_user] = lambda: u
        self.app.dependency_overrides[get_current_business_id] = lambda: business_id

    def test_list_all_purchase_returns_endpoint_ok(self):
        """GET /orders/returns/purchases returns 200 with items + total."""
        db = _mock_db()
        pr = _make_purchase_return()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [pr]

        db.execute = AsyncMock(side_effect=[count_mock, items_mock])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/returns/purchases")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_list_all_purchase_returns_empty(self):
        """GET /orders/returns/purchases returns empty list when no returns."""
        db = _mock_db()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_mock, items_mock])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/returns/purchases")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_get_purchase_return_endpoint_ok(self):
        """GET /orders/returns/purchases/{id} returns 200 with correct fields."""
        db = _mock_db()
        pr = _make_purchase_return()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = pr
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/orders/returns/purchases/{pr.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(pr.id)
        assert body["ref_no"] == pr.ref_no
        assert "total_amount" in body

    def test_get_purchase_return_not_found(self):
        """GET /orders/returns/purchases/{bad_id} returns 404."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        bad_id = uuid.uuid4()
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/orders/returns/purchases/{bad_id}")

        assert resp.status_code == 404

    def test_list_returns_by_order_endpoint_ok(self):
        """GET /orders/{order_id}/returns returns 200 with filtered items."""
        db = _mock_db()
        order_id = uuid.uuid4()
        pr = _make_purchase_return(original_order_id=order_id)

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [pr]

        db.execute = AsyncMock(side_effect=[count_mock, items_mock])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/orders/{order_id}/returns")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["original_order_id"] == str(order_id)

    def test_list_returns_by_order_empty(self):
        """GET /orders/{order_id}/returns returns empty list for order with no returns."""
        db = _mock_db()
        order_id = uuid.uuid4()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_mock, items_mock])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/orders/{order_id}/returns")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_static_returns_route_before_parameterized(self):
        """GET /orders/returns/purchases resolves as static, not /{order_id}/returns."""
        db = _mock_db()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_mock, items_mock])
        self._override_db(db)

        with TestClient(self.app) as client:
            # "returns" would match /{order_id} if static route not first
            resp = client.get("/api/v1/orders/returns/purchases")

        assert resp.status_code == 200  # 422 = treated as UUID param
