"""Tests for reports domain: profit/loss, stock report, purchase & sale."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import src.suppliers.models  # noqa: F401 — registers Supplier mapper for PurchaseOrder.supplier relationship
from src.auth.service import build_token
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_BUSINESS_ID = uuid.uuid4()


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
        business_id=_DEFAULT_BUSINESS_ID,
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
        # Sequence: purchase, sales, opex, stock, purchase_returns, sell_returns, purchase_due, sales_due
        _mock_execute_sequence(
            db,
            [
                None,  # total_purchase (no rows)
                None,  # total_sales (no rows)
                [],  # operating costs (empty)
                None,  # stock value (no batches)
                None,  # purchase_returns (no rows)
                None,  # sell_returns (no rows)
                None,  # purchase_due (no unpaid orders)
                None,  # sales_due (no unpaid sales)
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
        # total_purchase=200000, total_sales=350000, opex=[100000/mo], stock=500000, returns=5000
        opex = [_make_operating_cost(monthly_equivalent=Decimal("100000.00"))]
        _mock_execute_sequence(
            db,
            [
                Decimal("200000.000000"),  # total_purchase
                Decimal("350000.000000"),  # total_sales
                opex,  # operating_costs list
                Decimal("500000.000000"),  # stock_value
                Decimal("5000.000000"),  # purchase_returns
                None,  # sell_returns (none in this test)
                None,  # purchase_due (no unpaid orders)
                None,  # sales_due (no unpaid sales)
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.total_purchase_excl_tax == Decimal("200000.000000")
        assert result.total_sales == Decimal("350000.000000")
        assert result.gross_profit == Decimal("150000.000000")  # 350000 - 200000
        # operating costs = 100000 * 1 month
        assert result.total_operating_costs == Decimal("100000.00")
        assert result.net_profit == Decimal("50000.00")  # 150000 - 100000
        assert result.purchase_returns_total == Decimal("5000.000000")
        # placeholders
        assert result.purchase_due == Decimal("0")
        assert result.sales_due == Decimal("0")

    @pytest.mark.asyncio
    async def test_profit_loss_purchase_query_filters_by_order_date_not_created_at(self):
        """Confirmed live during a real POS migration: filtering by
        PurchaseOrder.created_at (row-insert timestamp) instead of
        order_date (when the purchase actually happened) silently excludes
        every purchase from any date-scoped P&L report whose end_date is
        today — created_at always has a non-midnight time component, so
        `created_at <= end_date` (implicitly midnight) is false for every
        row created today. Must filter on order_date, matching sales_query's
        use of Sale.sale_date and dashboard/service.py's identical query."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),  # total_purchase
                Decimal("200000.000000"),  # total_sales
                [],  # operating_costs
                Decimal("0"),  # stock_value
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
            ],
        )

        await get_profit_loss_report(
            db, start_date=date(2026, 1, 1), end_date=date(2026, 3, 31)
        )

        purchase_query = db.execute.call_args_list[0].args[0]
        compiled = str(purchase_query)
        assert "order_date" in compiled
        assert "created_at" not in compiled

    @pytest.mark.asyncio
    async def test_profit_loss_with_date_range(self):
        """Report accepts start_date and end_date filters."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),  # total_purchase
                Decimal("200000.000000"),  # total_sales
                [],  # operating_costs (empty)
                Decimal("0"),  # stock_value
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
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
                Decimal("300000.000000"),  # purchases
                Decimal("350000.000000"),  # sales
                opex,  # opex (200k/month)
                Decimal("1000000.000000"),  # stock
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
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
                Decimal("500000.000000"),  # total_purchase
                Decimal("10000.000000"),  # total_purchase_returns
                Decimal("750000.000000"),  # total_sales
                None,  # sell_returns (none in this test)
            ],
        )

        result = await get_purchase_sale_report(db)

        assert result.total_purchase == Decimal("500000.000000")
        assert result.total_purchase_returns == Decimal("10000.000000")
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
            [
                None,  # total_purchase
                None,  # purchase_returns
                None,  # total_sales
                None,  # sell_returns
            ],
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
                Decimal("100000.000000"),  # total_purchase
                Decimal("0"),  # purchase_returns
                Decimal("150000.000000"),  # total_sales
                None,  # sell_returns
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
        assert result.total_purchase_returns == Decimal("0")

    @pytest.mark.asyncio
    async def test_purchase_sale_negative_net_position(self):
        """Net position is negative when purchases exceed sales."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("800000.000000"),  # purchases
                Decimal("0"),  # purchase_returns
                Decimal("600000.000000"),  # sales
                None,  # sell_returns
            ],
        )

        result = await get_purchase_sale_report(db)

        assert result.net_position == Decimal("-200000.000000")

    @pytest.mark.asyncio
    async def test_purchase_sale_report_includes_sell_returns(self):
        """total_sales_returns reflects real SellReturn totals, not hardcoded zero."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("500000.000000"),  # total_purchase
                Decimal("0"),  # purchase_returns
                Decimal("700000.000000"),  # total_sales
                Decimal("25000.000000"),  # sell_returns — non-zero
            ],
        )

        result = await get_purchase_sale_report(db)

        assert result.total_sales_returns == Decimal("25000.000000")
        assert result.total_sales == Decimal("700000.000000")


# ---------------------------------------------------------------------------
# Profit & Loss — new field tests (TDD)
# ---------------------------------------------------------------------------


class TestProfitLossNewFields:
    @pytest.mark.asyncio
    async def test_profit_loss_purchase_due_not_zero(self):
        """purchase_due reflects real unpaid/partial order balances."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("300000.000000"),  # total_purchase
                Decimal("400000.000000"),  # total_sales
                [],  # opex
                Decimal("0"),  # stock
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                Decimal("75000.000000"),  # purchase_due — non-zero
                None,  # sales_due
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.purchase_due == Decimal("75000.000000")

    @pytest.mark.asyncio
    async def test_profit_loss_sales_due_not_zero(self):
        """sales_due reflects real unpaid/partial sale balances."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("200000.000000"),  # total_purchase
                Decimal("350000.000000"),  # total_sales
                [],  # opex
                Decimal("0"),  # stock
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                Decimal("40000.000000"),  # sales_due — non-zero
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.sales_due == Decimal("40000.000000")

    @pytest.mark.asyncio
    async def test_profit_loss_includes_sales_returns(self):
        """total_sales_returns in P&L reflects real SellReturn totals."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("200000.000000"),  # total_purchase
                Decimal("350000.000000"),  # total_sales
                [],  # opex
                Decimal("0"),  # stock
                Decimal("0"),  # purchase_returns
                Decimal("15000.000000"),  # sell_returns — non-zero
                None,  # purchase_due
                None,  # sales_due
            ],
        )

        result = await get_profit_loss_report(db)

        assert result.total_sales_returns == Decimal("15000.000000")


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
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        async def _fake_db():
            yield db_mock

        def _fake_user():
            return _make_user()

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        self.app.dependency_overrides[get_db] = _fake_db
        self.app.dependency_overrides[get_current_active_user] = _fake_user
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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
                None,  # UserPreferences lookup (no FY configured)
                Decimal("200000.000000"),  # total_purchase
                Decimal("350000.000000"),  # total_sales
                opex,  # operating_costs
                Decimal("500000.000000"),  # stock_value
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
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
                Decimal("100000.000000"),  # total_purchase
                Decimal("200000.000000"),  # total_sales
                [],  # operating_costs
                Decimal("0"),  # stock_value
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
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
                None,  # UserPreferences lookup (no FY configured)
                Decimal("500000.000000"),  # total_purchase
                Decimal("0"),  # purchase_returns
                Decimal("750000.000000"),  # total_sales
                None,  # sell_returns
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
                Decimal("100000.000000"),  # total_purchase
                Decimal("0"),  # purchase_returns
                Decimal("150000.000000"),  # total_sales
                None,  # sell_returns
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

    def test_profit_loss_no_params_with_fy_configured(self):
        """GET /reports/profit-loss with no params uses FY start as date_from."""
        from src.settings.models import UserPreferences as UserPrefsModel

        db = _mock_db()
        prefs = MagicMock(spec=UserPrefsModel)
        prefs.fiscal_year_start_month = 4
        prefs.fiscal_year_start_day = 1
        opex = [_make_operating_cost(monthly_equivalent=Decimal("50000.00"))]
        _mock_execute_sequence(
            db,
            [
                prefs,  # FY lookup: April 1
                Decimal("100000.000000"),
                Decimal("200000.000000"),
                opex,
                Decimal("300000.000000"),
                Decimal("0"),
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
            ],
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/profit-loss")
        assert resp.status_code == 200

    def test_purchase_sale_no_params_with_fy_configured(self):
        """GET /reports/purchase-sale with no params uses FY start as date_from."""
        from src.settings.models import UserPreferences as UserPrefsModel

        db = _mock_db()
        prefs = MagicMock(spec=UserPrefsModel)
        prefs.fiscal_year_start_month = 4
        prefs.fiscal_year_start_day = 1
        _mock_execute_sequence(
            db,
            [
                prefs,  # FY lookup: April 1
                Decimal("500000.000000"),
                Decimal("0"),
                Decimal("750000.000000"),
                None,  # sell_returns
            ],
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/reports/purchase-sale")
        assert resp.status_code == 200
        body = resp.json()
        assert "net_position" in body


# ---------------------------------------------------------------------------
# resolve_default_date_range unit tests
# ---------------------------------------------------------------------------


class TestResolveDefaultDateRange:
    @pytest.mark.asyncio
    async def test_no_fy_returns_365_day_range(self):
        """No fiscal year configured → date_from = today-365, date_to = today."""
        from unittest.mock import patch

        from src.reports.service import resolve_default_date_range
        from src.settings.schemas import FiscalYearRead

        db = _mock_db()
        user_id = uuid.uuid4()
        fy = FiscalYearRead(fiscal_year_start_month=None, fiscal_year_start_day=None)
        fixed_today = date(2026, 6, 29)

        with patch(
            "src.reports.service.get_fiscal_year_start",
            new=AsyncMock(return_value=fy),
        ):
            date_from, date_to = await resolve_default_date_range(
                db, user_id, today=fixed_today
            )

        assert date_to == fixed_today
        assert date_from == fixed_today - timedelta(days=365)

    @pytest.mark.asyncio
    async def test_fy_after_fys_returns_current_year_date(self):
        """FY April 1, today June 29 2026 (after Apr 1) → date_from = 2026-04-01."""
        from unittest.mock import patch

        from src.reports.service import resolve_default_date_range
        from src.settings.schemas import FiscalYearRead

        db = _mock_db()
        user_id = uuid.uuid4()
        fy = FiscalYearRead(fiscal_year_start_month=4, fiscal_year_start_day=1)

        with patch(
            "src.reports.service.get_fiscal_year_start",
            new=AsyncMock(return_value=fy),
        ):
            date_from, date_to = await resolve_default_date_range(
                db, user_id, today=date(2026, 6, 29)
            )

        assert date_from == date(2026, 4, 1)
        assert date_to == date(2026, 6, 29)

    @pytest.mark.asyncio
    async def test_fy_before_fys_rolls_over_to_prior_year(self):
        """FY April 1, today Feb 15 2026 (before Apr 1) → date_from = 2025-04-01."""
        from unittest.mock import patch

        from src.reports.service import resolve_default_date_range
        from src.settings.schemas import FiscalYearRead

        db = _mock_db()
        user_id = uuid.uuid4()
        fy = FiscalYearRead(fiscal_year_start_month=4, fiscal_year_start_day=1)

        with patch(
            "src.reports.service.get_fiscal_year_start",
            new=AsyncMock(return_value=fy),
        ):
            date_from, date_to = await resolve_default_date_range(
                db, user_id, today=date(2026, 2, 15)
            )

        assert date_from == date(2025, 4, 1)
        assert date_to == date(2026, 2, 15)

    @pytest.mark.asyncio
    async def test_fy_same_day_as_today_includes_today(self):
        """FY = today's date → date_from = today (FY just started today)."""
        from unittest.mock import patch

        from src.reports.service import resolve_default_date_range
        from src.settings.schemas import FiscalYearRead

        db = _mock_db()
        user_id = uuid.uuid4()
        fy = FiscalYearRead(fiscal_year_start_month=6, fiscal_year_start_day=29)

        with patch(
            "src.reports.service.get_fiscal_year_start",
            new=AsyncMock(return_value=fy),
        ):
            date_from, date_to = await resolve_default_date_range(
                db, user_id, today=date(2026, 6, 29)
            )

        assert date_from == date(2026, 6, 29)
        assert date_to == date(2026, 6, 29)


# ---------------------------------------------------------------------------
# Location filter tests
# ---------------------------------------------------------------------------


class TestLocationFilter:
    @pytest.mark.asyncio
    async def test_profit_loss_location_filter_passes_to_service(self):
        """GET /reports/profit-loss?location_id=... forwards location_id to service."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),  # total_purchase
                Decimal("150000.000000"),  # total_sales
                [],  # operating_costs
                Decimal("0"),  # stock_value
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
            ],
        )

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        location_id = str(uuid.uuid4())
        try:
            with TestClient(app) as client:
                resp = client.get(
                    "/api/v1/reports/profit-loss",
                    params={
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                        "location_id": location_id,
                    },
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)

    @pytest.mark.asyncio
    async def test_purchase_sale_location_filter_accepted(self):
        """GET /reports/purchase-sale?location_id=... returns 200."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("200000.000000"),  # total_purchase
                Decimal("0"),  # purchase_returns
                Decimal("300000.000000"),  # total_sales
                None,  # sell_returns
            ],
        )

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        location_id = str(uuid.uuid4())
        try:
            with TestClient(app) as client:
                resp = client.get(
                    "/api/v1/reports/purchase-sale",
                    params={
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                        "location_id": location_id,
                    },
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)

    @pytest.mark.asyncio
    async def test_stock_location_filter_accepted(self):
        """GET /reports/stock?location_id=... returns 200."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        location_id = str(uuid.uuid4())
        try:
            with TestClient(app) as client:
                resp = client.get(
                    "/api/v1/reports/stock",
                    params={"location_id": location_id},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)

    @pytest.mark.asyncio
    async def test_profit_loss_location_filter_service(self):
        """Service get_profit_loss_report accepts location_id without error."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),  # total_purchase
                Decimal("200000.000000"),  # total_sales
                [],  # operating_costs
                Decimal("0"),  # stock_value
                Decimal("0"),  # purchase_returns
                None,  # sell_returns
                None,  # purchase_due
                None,  # sales_due
            ],
        )
        location_id = uuid.uuid4()
        result = await get_profit_loss_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            location_id=location_id,
        )
        assert result.total_sales == Decimal("200000.000000")

    @pytest.mark.asyncio
    async def test_purchase_sale_location_filter_service(self):
        """Service get_purchase_sale_report accepts location_id without error."""
        from src.reports.service import get_purchase_sale_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("100000.000000"),  # total_purchase
                Decimal("0"),  # purchase_returns
                Decimal("150000.000000"),  # total_sales
                None,  # sell_returns
            ],
        )
        location_id = uuid.uuid4()
        result = await get_purchase_sale_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            location_id=location_id,
        )
        assert result.total_purchase == Decimal("100000.000000")

    @pytest.mark.asyncio
    async def test_profit_loss_location_filter_scopes_sell_returns(self):
        """sell_returns in P&L are scoped to location_id (joined via Sale)."""
        from src.reports.service import get_profit_loss_report

        db = _mock_db()
        _mock_execute_sequence(
            db,
            [
                Decimal("0"),   # total_purchase (location-scoped)
                Decimal("50000.000000"),  # total_sales (location-scoped)
                [],             # operating_costs
                Decimal("0"),   # stock_value
                Decimal("0"),   # purchase_returns
                Decimal("5000.000000"),  # sell_returns (location-scoped)
                None,           # purchase_due
                None,           # sales_due
            ],
        )
        location_id = uuid.uuid4()
        result = await get_profit_loss_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            location_id=location_id,
        )
        assert result.total_sales_returns == Decimal("5000.000000")


# ---------------------------------------------------------------------------
# Per-product sales report tests
# ---------------------------------------------------------------------------


class TestProductSalesReport:
    @pytest.mark.asyncio
    async def test_product_sales_report_groups_by_product(self):
        """get_product_sales_report returns a row per product."""
        from src.reports.service import get_product_sales_report

        db = _mock_db()
        pid = uuid.uuid4()
        row = MagicMock()
        row.product_id = pid
        row.sku = "PRD-001"
        row.product_name = "Widget"
        row.category = "Electronics"
        row.quantity_sold = 10
        row.total_revenue = Decimal("150000.000000")
        row.avg_unit_price = Decimal("15000.000000")
        row.return_quantity = 1

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        revenue_mock = MagicMock()
        revenue_mock.scalar.return_value = Decimal("150000.000000")

        rows_mock = MagicMock()
        rows_mock.all.return_value = [row]

        db.execute = AsyncMock(side_effect=[count_mock, revenue_mock, rows_mock])

        result = await get_product_sales_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
        )

        assert result.total == 1
        assert len(result.rows) == 1
        assert result.rows[0].product_name == "Widget"
        assert result.rows[0].quantity_sold == 10
        assert result.rows[0].net_quantity == 9  # 10 - 1
        assert result.total_revenue == Decimal("150000.000000")

    @pytest.mark.asyncio
    async def test_product_sales_report_margin_calculation(self):
        """Rows have correct net_quantity = quantity_sold - return_quantity."""
        from src.reports.service import get_product_sales_report

        db = _mock_db()
        row = MagicMock()
        row.product_id = uuid.uuid4()
        row.sku = "PRD-002"
        row.product_name = "Gadget"
        row.category = "Tech"
        row.quantity_sold = 5
        row.total_revenue = Decimal("75000.000000")
        row.avg_unit_price = Decimal("15000.000000")
        row.return_quantity = 2

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1
        revenue_mock = MagicMock()
        revenue_mock.scalar.return_value = Decimal("75000.000000")
        rows_mock = MagicMock()
        rows_mock.all.return_value = [row]
        db.execute = AsyncMock(side_effect=[count_mock, revenue_mock, rows_mock])

        result = await get_product_sales_report(db)

        assert result.rows[0].net_quantity == 3  # 5 - 2
        assert result.total_revenue == Decimal("75000.000000")

    @pytest.mark.asyncio
    async def test_product_sales_report_empty(self):
        """get_product_sales_report returns empty rows for no sales."""
        from src.reports.service import get_product_sales_report

        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 0
        revenue_mock = MagicMock()
        revenue_mock.scalar.return_value = None  # no revenue when empty
        rows_mock = MagicMock()
        rows_mock.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_mock, revenue_mock, rows_mock])

        result = await get_product_sales_report(db)

        assert result.total == 0
        assert result.rows == []
        assert result.total_revenue == Decimal("0")

    def test_product_sales_endpoint_ok(self):
        """GET /reports/product-sales returns 200."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 0
        revenue_mock = MagicMock()
        revenue_mock.scalar.return_value = None
        rows_mock = MagicMock()
        rows_mock.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_mock, revenue_mock, rows_mock])

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        try:
            with TestClient(app) as client:
                resp = client.get("/api/v1/reports/product-sales")
            assert resp.status_code == 200
            body = resp.json()
            assert "rows" in body
            assert "total" in body
            assert "total_revenue" in body
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)

    def test_product_sales_endpoint_with_filters(self):
        """GET /reports/product-sales?start_date=...&category_id=... returns 200."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 0
        revenue_mock = MagicMock()
        revenue_mock.scalar.return_value = None
        rows_mock = MagicMock()
        rows_mock.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_mock, revenue_mock, rows_mock])

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        try:
            with TestClient(app) as client:
                resp = client.get(
                    "/api/v1/reports/product-sales",
                    params={
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                        "page": 1,
                        "page_size": 10,
                    },
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)


# ---------------------------------------------------------------------------
# Trending products tests
# ---------------------------------------------------------------------------


class TestTrendingProducts:
    @pytest.mark.asyncio
    async def test_trending_products_sorted_by_revenue(self):
        """get_trending_products returns rows sorted by revenue descending."""
        from src.reports.service import get_trending_products

        db = _mock_db()
        row1 = MagicMock()
        row1.product_id = uuid.uuid4()
        row1.sku = "PRD-A"
        row1.product_name = "TopSeller"
        row1.category = "Category A"
        row1.quantity_sold = 50
        row1.total_revenue = Decimal("1000000.000000")

        row2 = MagicMock()
        row2.product_id = uuid.uuid4()
        row2.sku = "PRD-B"
        row2.product_name = "SecondSeller"
        row2.category = "Category B"
        row2.quantity_sold = 30
        row2.total_revenue = Decimal("500000.000000")

        result_mock = MagicMock()
        result_mock.all.return_value = [row1, row2]
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_trending_products(db, limit=10, sort_by="revenue")

        assert len(result.rows) == 2
        assert result.rows[0].rank == 1
        assert result.rows[0].product_name == "TopSeller"
        assert result.rows[1].rank == 2

    @pytest.mark.asyncio
    async def test_trending_products_sorted_by_quantity(self):
        """get_trending_products with sort_by=quantity returns correct rows."""
        from src.reports.service import get_trending_products

        db = _mock_db()
        row = MagicMock()
        row.product_id = uuid.uuid4()
        row.sku = "PRD-Q"
        row.product_name = "HighVolume"
        row.category = "Cat"
        row.quantity_sold = 200
        row.total_revenue = Decimal("200000.000000")

        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_trending_products(db, sort_by="quantity")

        assert len(result.rows) == 1
        assert result.rows[0].quantity_sold == 200

    @pytest.mark.asyncio
    async def test_trending_products_empty(self):
        """get_trending_products returns empty list for no sales."""
        from src.reports.service import get_trending_products

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_trending_products(db)

        assert result.rows == []

    def test_trending_products_endpoint_ok(self):
        """GET /reports/trending-products returns 200."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        try:
            with TestClient(app) as client:
                resp = client.get("/api/v1/reports/trending-products")
            assert resp.status_code == 200
            body = resp.json()
            assert "rows" in body
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)

    def test_trending_products_endpoint_with_params(self):
        """GET /reports/trending-products?limit=5&sort_by=quantity returns 200."""
        from src.main import app
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.core.database import get_db

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        async def _fake_db():
            yield db

        async def _fake_business_id():
            return _DEFAULT_BUSINESS_ID

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_active_user] = lambda: _make_user()
        app.dependency_overrides[get_current_business_id] = _fake_business_id
        try:
            with TestClient(app) as client:
                resp = client.get(
                    "/api/v1/reports/trending-products",
                    params={
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                        "limit": 5,
                        "sort_by": "quantity",
                    },
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_active_user, None)
            app.dependency_overrides.pop(get_current_business_id, None)
