"""Tests for reports domain: profit/loss, stock report, purchase & sale."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
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
    db.delete = AsyncMock()
    return db


def _mock_execute_scalar(db, value):
    """Configure db.execute to return a scalar value."""
    result_mock = MagicMock()
    result_mock.scalar.return_value = value
    result_mock.scalar_one_or_none.return_value = value
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _mock_execute_sequence(db, side_effects):
    """Configure db.execute to return a sequence of results (for multiple calls)."""
    mocks = []
    for value in side_effects:
        result_mock = MagicMock()
        if isinstance(value, list):
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = value
            result_mock.scalars.return_value = scalars_mock
            result_mock.scalar.return_value = None
        else:
            result_mock.scalar.return_value = value
            result_mock.scalar_one_or_none.return_value = value
        mocks.append(result_mock)
    db.execute = AsyncMock(side_effect=mocks)
    return db


def _make_inventory_batch(product_id=None, **overrides):
    from src.inventory.models import InventoryBatch

    defaults = dict(
        product_id=product_id or uuid.uuid4(),
        order_id=uuid.uuid4(),
        quantity_received=100,
        quantity_remaining=50,
        unit_cost_usd=Decimal("10.000000"),
        fx_rate_at_arrival=Decimal("1500.000000"),
        logistics_allocation_per_unit=Decimal("50.000000"),
        landed_cost_per_unit=Decimal("15050.000000"),
        received_at=date(2026, 1, 1),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    batch = InventoryBatch(**defaults)
    batch.id = overrides.get("id", uuid.uuid4())
    return batch


def _make_product(**overrides):
    from src.products.models import Product

    defaults = dict(
        name="Test Product",
        sku="PRD-001",
        description="A test product",
        category_id=uuid.uuid4(),
        unit_cost=Decimal("15050.000000"),
        selling_price=Decimal("20000.000000"),
        currency="NGN",
        is_active=True,
    )
    defaults.update(overrides)
    product = Product(**defaults)
    product.id = overrides.get("id", uuid.uuid4())
    product.created_at = datetime.now(timezone.utc)
    product.updated_at = datetime.now(timezone.utc)
    return product


def _make_operating_cost(**overrides):
    from src.cashflow.models import CostCategory, CostFrequency, OperatingCost

    defaults = dict(
        cost_name="Office Rent",
        cost_amount=Decimal("100000.000000"),
        frequency=CostFrequency.MONTHLY,
        monthly_equivalent=Decimal("100000.00"),
        category=CostCategory.RENT,
        is_active=True,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    cost = OperatingCost(**defaults)
    cost.id = overrides.get("id", uuid.uuid4())
    cost.created_at = datetime.now(timezone.utc)
    cost.updated_at = datetime.now(timezone.utc)
    return cost


# ---------------------------------------------------------------------------
# Profit / Loss Report Tests
# ---------------------------------------------------------------------------


class TestProfitLossReport:
    @pytest.mark.asyncio
    async def test_profit_loss_empty_period_returns_zeros(self):
        """When no sales or purchases exist, all values should be zero."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        # Sequence: total_purchase, total_sales, operating_costs, stock_value, purchase_returns
        _mock_execute_sequence(
            db,
            [
                None,   # total_purchase (no rows)
                None,   # total_sales (no rows)
                [],     # operating costs (empty)
                None,   # stock value (no batches)
                None,   # purchase_returns (no rows)
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.total_purchase_excl_tax == Decimal("0")
        assert result.total_sales == Decimal("0")
        assert result.gross_profit == Decimal("0")
        assert result.net_profit == Decimal("0")
        assert result.total_operating_costs == Decimal("0")
        assert result.opening_stock_value == Decimal("0")
        assert result.closing_stock_value == Decimal("0")
        assert result.purchase_due == Decimal("0")
        assert result.sales_due == Decimal("0")

    @pytest.mark.asyncio
    async def test_profit_loss_with_sales_and_purchases(self):
        """Report correctly calculates gross and net profit."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        # total_purchase=200000, total_sales=350000, opex=[100000/mo], stock=500000, returns=10000
        opex = [_make_operating_cost(monthly_equivalent=Decimal("100000.00"))]
        _mock_execute_sequence(
            db,
            [
                Decimal("200000.000000"),   # total_purchase
                Decimal("350000.000000"),   # total_sales
                opex,                       # operating_costs list
                Decimal("500000.000000"),   # stock_value
                Decimal("10000.000000"),    # purchase_returns
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.total_purchase_excl_tax == Decimal("200000.000000")
        assert result.total_sales == Decimal("350000.000000")
        assert result.gross_profit == Decimal("150000.000000")  # 350000 - 200000
        # operating costs = 100000 * 1 month
        assert result.total_operating_costs == Decimal("100000.00")
        assert result.net_profit == Decimal("50000.00")  # 150000 - 100000
        assert result.purchase_returns_total == Decimal("10000.000000")
        # placeholders
        assert result.purchase_due == Decimal("0")
        assert result.sales_due == Decimal("0")

    @pytest.mark.asyncio
    async def test_profit_loss_with_date_range(self):
        """Report accepts start_date and end_date filters."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),
                Decimal("200000.000000"),
                [],
                Decimal("0"),
                Decimal("0"),
            ],
        )

        result = await get_profit_loss_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        assert result.total_purchase_excl_tax == Decimal("100000.000000")
        assert result.total_sales == Decimal("200000.000000")
        assert result.gross_profit == Decimal("100000.000000")

    @pytest.mark.asyncio
    async def test_profit_loss_negative_net_profit(self):
        """Net profit can be negative when operating costs exceed gross profit."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        opex = [
            _make_operating_cost(monthly_equivalent=Decimal("200000.00")),
        ]
        _mock_execute_sequence(
            db,
            [
                Decimal("300000.000000"),   # purchases
                Decimal("350000.000000"),   # sales
                opex,                       # opex (200k/month)
                Decimal("1000000.000000"),  # stock
                Decimal("0"),              # returns
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.gross_profit == Decimal("50000.000000")
        assert result.net_profit == Decimal("-150000.00")  # 50000 - 200000


# ---------------------------------------------------------------------------
# Stock Report Tests
# ---------------------------------------------------------------------------


class TestStockReport:
    @pytest.mark.asyncio
    async def test_stock_report_returns_items(self):
        """Stock report returns items for each product with inventory."""
        from src.reports.service import get_stock_report

        db = _mock_db()
        product_id = uuid.uuid4()
        # Each row: (product_id, sku, name, category_name, unit_cost, selling_price, qty_on_hand, total_sold)
        row = MagicMock()
        row.product_id = product_id
        row.sku = "PRD-001"
        row.product_name = "Test Product"
        row.category = "Electronics"
        row.unit_cost = Decimal("15050.000000")
        row.selling_price = Decimal("20000.000000")
        row.quantity_on_hand = 50
        row.total_sold = 30

        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        db.execute = AsyncMock(return_value=result_mock)

        report = await get_stock_report(db)

        assert len(report.items) == 1
        item = report.items[0]
        assert item.product_id == product_id
        assert item.sku == "PRD-001"
        assert item.product_name == "Test Product"
        assert item.quantity_on_hand == 50
        assert item.total_sold == 30

    @pytest.mark.asyncio
    async def test_stock_report_totals_calculated(self):
        """Stock report calculates stock_value, potential_profit and totals correctly."""
        from src.reports.service import get_stock_report

        db = _mock_db()
        row = MagicMock()
        row.product_id = uuid.uuid4()
        row.sku = "PRD-001"
        row.product_name = "Test Product"
        row.category = "Electronics"
        row.unit_cost = Decimal("10000.000000")
        row.selling_price = Decimal("15000.000000")
        row.quantity_on_hand = 20
        row.total_sold = 10

        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        db.execute = AsyncMock(return_value=result_mock)

        report = await get_stock_report(db)

        item = report.items[0]
        # stock_value = qty * unit_cost = 20 * 10000 = 200000
        assert item.stock_value == Decimal("200000.000000")
        # potential_profit = (selling - cost) * qty = 5000 * 20 = 100000
        assert item.potential_profit == Decimal("100000.000000")
        # Totals
        assert report.total_stock_value == Decimal("200000.000000")
        assert report.total_potential_profit == Decimal("100000.000000")
        assert report.total_sold == 10

    @pytest.mark.asyncio
    async def test_stock_report_empty(self):
        """Stock report with no products returns empty list and zero totals."""
        from src.reports.service import get_stock_report

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        report = await get_stock_report(db)

        assert report.items == []
        assert report.total_stock_value == Decimal("0")
        assert report.total_potential_profit == Decimal("0")
        assert report.total_sold == 0

    @pytest.mark.asyncio
    async def test_stock_report_multiple_products(self):
        """Stock report aggregates totals across multiple products."""
        from src.reports.service import get_stock_report

        db = _mock_db()

        row1 = MagicMock()
        row1.product_id = uuid.uuid4()
        row1.sku = "PRD-001"
        row1.product_name = "Product A"
        row1.category = "Cat A"
        row1.unit_cost = Decimal("1000.000000")
        row1.selling_price = Decimal("1500.000000")
        row1.quantity_on_hand = 10
        row1.total_sold = 5

        row2 = MagicMock()
        row2.product_id = uuid.uuid4()
        row2.sku = "PRD-002"
        row2.product_name = "Product B"
        row2.category = "Cat B"
        row2.unit_cost = Decimal("2000.000000")
        row2.selling_price = Decimal("3000.000000")
        row2.quantity_on_hand = 5
        row2.total_sold = 3

        result_mock = MagicMock()
        result_mock.all.return_value = [row1, row2]
        db.execute = AsyncMock(return_value=result_mock)

        report = await get_stock_report(db)

        # row1: stock_value = 10 * 1000 = 10000; potential = 5000 * 10 = 5000 (wait: 500*10=5000)
        # row2: stock_value = 5 * 2000 = 10000; potential = 1000 * 5 = 5000
        # total_stock = 20000, total_potential = 10000, total_sold = 8
        assert len(report.items) == 2
        assert report.total_stock_value == Decimal("20000.000000")
        assert report.total_potential_profit == Decimal("10000.000000")
        assert report.total_sold == 8


# ---------------------------------------------------------------------------
# Purchase & Sale Report Tests
# ---------------------------------------------------------------------------


class TestPurchaseSaleReport:
    @pytest.mark.asyncio
    async def test_purchase_sale_report_totals(self):
        """Report sums purchases, purchase returns, and sales."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("500000.000000"),   # total_purchase
                Decimal("20000.000000"),    # total_purchase_returns
                Decimal("750000.000000"),   # total_sales
            ],
        )

        result = await get_purchase_sale_report(db)

        assert result.total_purchase == Decimal("500000.000000")
        assert result.total_purchase_returns == Decimal("20000.000000")
        assert result.total_sales == Decimal("750000.000000")
        assert result.total_sales_returns == Decimal("0")
        # net_position = total_sales - total_purchase = 750000 - 500000
        assert result.net_position == Decimal("250000.000000")

    @pytest.mark.asyncio
    async def test_purchase_sale_report_empty_period(self):
        """Report returns zeros when no transactions exist in period."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [None, None, None],  # all sums return None
        )

        result = await get_purchase_sale_report(db)

        assert result.total_purchase == Decimal("0")
        assert result.total_purchase_returns == Decimal("0")
        assert result.total_sales == Decimal("0")
        assert result.total_sales_returns == Decimal("0")
        assert result.net_position == Decimal("0")

    @pytest.mark.asyncio
    async def test_purchase_sale_report_with_date_range(self):
        """Report filters by date range."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),
                Decimal("5000.000000"),
                Decimal("150000.000000"),
            ],
        )

        result = await get_purchase_sale_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        assert result.total_purchase == Decimal("100000.000000")
        assert result.total_sales == Decimal("150000.000000")
        assert result.net_position == Decimal("50000.000000")

    @pytest.mark.asyncio
    async def test_purchase_sale_negative_net_position(self):
        """Net position is negative when purchases exceed sales."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("800000.000000"),   # purchases
                Decimal("0"),              # returns
                Decimal("600000.000000"),   # sales
            ],
        )

        result = await get_purchase_sale_report(db)

        assert result.net_position == Decimal("-200000.000000")


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------


class TestReportsEndpoints:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
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

    def _auth_headers(self):
        user = _make_user()
        token = build_token(user)
        return {"Authorization": f"Bearer {token}"}, user

    def _make_stock_row(self):
        row = MagicMock()
        row.product_id = uuid.uuid4()
        row.sku = "PRD-001"
        row.product_name = "Test Product"
        row.category = "Electronics"
        row.unit_cost = Decimal("10000.000000")
        row.selling_price = Decimal("15000.000000")
        row.quantity_on_hand = 20
        row.total_sold = 10
        return row

    def test_profit_loss_endpoint_ok(self):
        """GET /reports/profit-loss returns 200 with correct structure."""
        db = _mock_db()
        opex = [_make_operating_cost(monthly_equivalent=Decimal("100000.00"))]
        _mock_execute_sequence(
            db,
            [
                Decimal("200000.000000"),
                Decimal("350000.000000"),
                opex,
                Decimal("500000.000000"),
                Decimal("10000.000000"),
            ],
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/profit-loss")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_sales" in body
        assert "gross_profit" in body
        assert "net_profit" in body

    def test_profit_loss_with_date_params(self):
        """GET /reports/profit-loss?start_date=...&end_date=... filters correctly."""
        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),
                Decimal("200000.000000"),
                [],
                Decimal("0"),
                Decimal("0"),
            ],
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/reports/profit-loss",
                params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            )
        assert resp.status_code == 200

    def test_stock_report_endpoint_ok(self):
        """GET /reports/stock returns 200 with stock items."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = [self._make_stock_row()]
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/stock")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total_stock_value" in body
        assert len(body["items"]) == 1

    def test_stock_export_csv_endpoint_ok(self):
        """GET /reports/stock/export-csv returns CSV content."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = [self._make_stock_row()]
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/stock/export-csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        # CSV has header row
        content = resp.content.decode("utf-8")
        assert "sku" in content or "SKU" in content or "product_id" in content

    def test_purchase_sale_report_endpoint_ok(self):
        """GET /reports/purchase-sale returns 200 with totals."""
        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("500000.000000"),
                Decimal("20000.000000"),
                Decimal("750000.000000"),
            ],
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/purchase-sale")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_purchase" in body
        assert "total_sales" in body
        assert "net_position" in body

    def test_purchase_sale_with_date_params(self):
        """GET /reports/purchase-sale?start_date=...&end_date=... filters correctly."""
        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),
                Decimal("5000.000000"),
                Decimal("150000.000000"),
            ],
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/reports/purchase-sale",
                params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            )
        assert resp.status_code == 200

    def test_stock_export_before_stock_detail(self):
        """Ensure /stock/export-csv route resolves before /stock/{id} pattern."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/stock/export-csv")
        # Should be 200 (CSV endpoint), not 422 (treated as UUID path param)
        assert resp.status_code == 200
