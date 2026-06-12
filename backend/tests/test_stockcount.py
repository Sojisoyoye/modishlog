"""Tests for stock count service and endpoints."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.suppliers.models  # noqa: F401 — register Supplier mapper for PurchaseOrder
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="sc_test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="SC Test User",
        is_active=True,
        role=UserRole.ADMIN,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    u = User(**defaults)
    u.id = overrides.get("id", uuid.uuid4())
    u.created_at = datetime.now(timezone.utc)
    u.updated_at = datetime.now(timezone.utc)
    return u


def _make_stock_count(count_type="PRODUCT", status="DRAFT", **overrides):
    from src.stockcount.models import StockCount, StockCountStatus, StockCountType

    sc = StockCount(
        count_date=date.today(),
        count_type=StockCountType(count_type),
        status=StockCountStatus(status),
        notes=None,
        created_by=uuid.uuid4(),
        finalized_at=None,
    )
    sc.id = overrides.get("id", uuid.uuid4())
    sc.items = overrides.get("items", [])
    sc.created_at = datetime.now(timezone.utc)
    sc.updated_at = datetime.now(timezone.utc)
    return sc


def _make_item(stock_count_id=None, product_id=None, **overrides):
    from src.stockcount.models import StockCountItem

    item = StockCountItem(
        stock_count_id=stock_count_id or uuid.uuid4(),
        product_id=product_id or uuid.uuid4(),
        order_line_item_id=overrides.get("order_line_item_id"),
        system_quantity_at_count=overrides.get("system_quantity_at_count"),
        counted_quantity=overrides.get("counted_quantity"),
        notes=overrides.get("notes"),
    )
    item.id = overrides.get("id", uuid.uuid4())
    return item


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    return db


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


class TestCreateProductStockCount:
    @pytest.mark.asyncio
    async def test_creates_one_item_per_product(self):
        """PRODUCT-type session creates one StockCountItem per product, system_quantity_at_count=None."""
        from src.stockcount.service import create_stock_count

        pid1, pid2 = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # InventoryLevel query
                il1 = MagicMock(product_id=pid1, quantity_on_hand=100)
                il2 = MagicMock(product_id=pid2, quantity_on_hand=50)
                result.scalars.return_value.all.return_value = [il1, il2]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute
        user_id = uuid.uuid4()

        sc = await create_stock_count(db, date.today(), "PRODUCT", None, user_id)

        assert sc.count_type.value == "PRODUCT"
        assert sc.status.value == "DRAFT"
        assert db.add.call_count >= 3  # 1 StockCount + 2 items
        added_items = [
            call.args[0]
            for call in db.add.call_args_list
            if hasattr(call.args[0], "system_quantity_at_count")
        ]
        assert len(added_items) == 2
        for item in added_items:
            assert item.system_quantity_at_count is None


class TestCreateLotStockCount:
    @pytest.mark.asyncio
    async def test_creates_one_item_per_active_lot(self):
        """LOT-type session creates one item per active lot (units_remaining > 0)."""
        from src.stockcount.service import create_stock_count

        db = _mock_db()
        lot = MagicMock()
        lot.id = uuid.uuid4()
        lot.product_id = uuid.uuid4()
        lot.units_remaining = Decimal("20")

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = [lot]
            return result

        db.execute = mock_execute
        sc = await create_stock_count(db, date.today(), "LOT", None, uuid.uuid4())

        assert sc.count_type.value == "LOT"
        added_items = [
            call.args[0]
            for call in db.add.call_args_list
            if hasattr(call.args[0], "order_line_item_id")
        ]
        assert len(added_items) == 1
        assert added_items[0].order_line_item_id == lot.id
        assert added_items[0].system_quantity_at_count is None


class TestUpdateCountedQuantity:
    @pytest.mark.asyncio
    async def test_update_in_draft_succeeds(self):
        """PATCH counted_quantity on a DRAFT item returns updated item."""
        from src.stockcount.service import update_count_item

        sc_id = uuid.uuid4()
        item_id = uuid.uuid4()
        item = _make_item(stock_count_id=sc_id, id=item_id)
        sc = _make_stock_count(id=sc_id)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = sc
            else:
                result.scalar_one_or_none.return_value = item
            return result

        db.execute = mock_execute

        updated = await update_count_item(db, sc_id, item_id, Decimal("80"))
        assert updated.counted_quantity == Decimal("80")

    @pytest.mark.asyncio
    async def test_update_rejected_when_finalized(self):
        """PATCH counted_quantity on a FINALIZED session raises StockCountFinalizedError."""
        from src.stockcount.exceptions import StockCountFinalizedError
        from src.stockcount.service import update_count_item

        sc_id = uuid.uuid4()
        sc = _make_stock_count(id=sc_id, status="FINALIZED")

        db = _mock_db()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = sc
            return result

        db.execute = mock_execute

        with pytest.raises(StockCountFinalizedError):
            await update_count_item(db, sc_id, uuid.uuid4(), Decimal("80"))


class TestFinalizeStockCount:
    @pytest.mark.asyncio
    async def test_finalize_product_count_snapshots_system_qty(self):
        """Finalization snapshots InventoryLevel.quantity_on_hand into system_quantity_at_count."""
        from src.stockcount.service import finalize_stock_count

        sc_id = uuid.uuid4()
        product_id = uuid.uuid4()
        item = _make_item(stock_count_id=sc_id, product_id=product_id, counted_quantity=Decimal("90"))
        sc = _make_stock_count(id=sc_id, status="DRAFT", items=[item])

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = sc
            else:
                inv = MagicMock(quantity_on_hand=100)
                result.scalar_one_or_none.return_value = inv
            return result

        db.execute = mock_execute

        finalized = await finalize_stock_count(db, sc_id)

        assert finalized.status.value == "FINALIZED"
        assert finalized.finalized_at is not None
        assert item.system_quantity_at_count == Decimal("100")

    @pytest.mark.asyncio
    async def test_finalize_already_finalized_raises(self):
        """Finalizing an already-FINALIZED session raises StockCountFinalizedError."""
        from src.stockcount.exceptions import StockCountFinalizedError
        from src.stockcount.service import finalize_stock_count

        sc = _make_stock_count(status="FINALIZED")
        db = _mock_db()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = sc
            return result

        db.execute = mock_execute

        with pytest.raises(StockCountFinalizedError):
            await finalize_stock_count(db, sc.id)


class TestVarianceCalculation:
    def test_variance_positive(self):
        """counted > system → positive variance (surplus)."""
        from src.stockcount.schemas import StockCountItemRead

        item = _make_item(
            system_quantity_at_count=Decimal("100"),
            counted_quantity=Decimal("110"),
        )
        read = StockCountItemRead.model_validate(item)
        assert read.variance == Decimal("10")

    def test_variance_negative(self):
        """counted < system → negative variance (shrinkage)."""
        from src.stockcount.schemas import StockCountItemRead

        item = _make_item(
            system_quantity_at_count=Decimal("100"),
            counted_quantity=Decimal("80"),
        )
        read = StockCountItemRead.model_validate(item)
        assert read.variance == Decimal("-20")

    def test_variance_null_when_not_finalized(self):
        """system_quantity_at_count=None → variance is None."""
        from src.stockcount.schemas import StockCountItemRead

        item = _make_item(counted_quantity=Decimal("80"))
        read = StockCountItemRead.model_validate(item)
        assert read.variance is None


class TestSystemQuantitySnapshotTiming:
    @pytest.mark.asyncio
    async def test_snapshot_reflects_stock_at_finalization_not_creation(self):
        """system_quantity_at_count captures the value at finalize time, not create time."""
        from src.stockcount.service import finalize_stock_count

        sc_id = uuid.uuid4()
        product_id = uuid.uuid4()
        # Item has no system_quantity_at_count yet (created pre-finalization)
        item = _make_item(stock_count_id=sc_id, product_id=product_id)
        assert item.system_quantity_at_count is None

        sc = _make_stock_count(id=sc_id, status="DRAFT", items=[item])
        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = sc
            else:
                # Stock changed between creation and finalization: was 100, now 75
                inv = MagicMock(quantity_on_hand=75)
                result.scalar_one_or_none.return_value = inv
            return result

        db.execute = mock_execute
        await finalize_stock_count(db, sc_id)

        # Must reflect the finalization-time value (75), not any prior value
        assert item.system_quantity_at_count == Decimal("75")


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class _StockCountEndpointBase:
    @pytest.fixture(autouse=True)
    def setup(self):
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

    def _auth_headers(self, user=None):
        from src.auth.service import build_token

        u = user or _make_user()
        return {"Authorization": f"Bearer {build_token(u)}"}, u


class TestStockCountCreateEndpoint(_StockCountEndpointBase):
    def test_create_requires_auth(self):
        """POST /stockcount without auth returns 401."""
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/stockcount/",
                json={"count_date": str(date.today()), "count_type": "PRODUCT"},
            )
        assert resp.status_code == 401

    def test_create_product_count_returns_201(self):
        """Authenticated POST /stockcount returns 201 with the new session."""
        user = _make_user()
        sc = _make_stock_count()
        sc.items = []

        db = _mock_db()
        db.get = AsyncMock(return_value=user)

        # Patch the router's local reference (direct import), not the service module
        with patch("src.stockcount.router.create_stock_count", new_callable=AsyncMock, return_value=sc), \
             patch("src.stockcount.router.get_stock_count", new_callable=AsyncMock, return_value=sc):
            self._override_db(db)
            headers, _ = self._auth_headers(user)
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/stockcount/",
                    json={"count_date": str(date.today()), "count_type": "PRODUCT"},
                    headers=headers,
                )
        assert resp.status_code == 201


class TestStockCountFinalizeEndpoint(_StockCountEndpointBase):
    def test_finalize_returns_200(self):
        """POST /stockcount/{id}/finalize returns 200 with finalized session."""
        user = _make_user()
        sc = _make_stock_count(status="FINALIZED")
        sc.items = []
        sc.finalized_at = datetime.now(timezone.utc)

        db = _mock_db()
        db.get = AsyncMock(return_value=user)

        with patch("src.stockcount.router.finalize_stock_count", new_callable=AsyncMock, return_value=sc):
            self._override_db(db)
            headers, _ = self._auth_headers(user)
            with TestClient(self.app) as client:
                resp = client.post(
                    f"/api/v1/stockcount/{sc.id}/finalize",
                    headers=headers,
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "FINALIZED"
