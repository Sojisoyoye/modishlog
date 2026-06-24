"""Tests for sales CRUD, inventory integration, and audit trail."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
from src.inventory.exceptions import InvalidStockAdjustmentError
from src.inventory.models import InventoryLevel
from src.sales.exceptions import (
    SaleAlreadyVoidedError,
    SaleNotFoundError,
    SaleValidationError,
)
from src.sales.models import Sale, SaleChannel, SaleStatus
from src.sales.schemas import SaleCreate, SaleUpdate
from src.sales.service import (
    create_sale,
    get_sale,
    get_sale_audit_trail,
    get_sales_summary,
    list_sales,
    process_bulk_upload,
    update_sale,
    void_sale,
)
import src.suppliers.models  # noqa: F401 — register Supplier mapper for PurchaseOrder.supplier

VALID_PASSWORD = "Str0ng!Pass#99"


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


def _make_product(**overrides):
    from src.products.models import Product

    defaults = dict(
        name="Test Product",
        sku="PRD-00001",
        description="A test product",
        category_id=uuid.uuid4(),
        unit_cost=Decimal("100.000000"),
        selling_price=Decimal("150.000000"),
        currency="NGN",
        is_active=True,
    )
    defaults.update(overrides)
    product = Product(**defaults)
    product.id = overrides.get("id", uuid.uuid4())
    product.created_at = datetime.now(timezone.utc)
    product.updated_at = datetime.now(timezone.utc)
    return product


def _make_sale(product_id=None, **overrides):
    defaults = dict(
        product_id=product_id or uuid.uuid4(),
        quantity=5,
        unit_price=Decimal("150.000000"),
        total_amount=Decimal("750.000000"),
        currency="NGN",
        sale_date=date(2026, 3, 15),
        channel=SaleChannel.RETAIL,
        status=SaleStatus.COMPLETED,
        notes=None,
        recorded_by=uuid.uuid4(),
        transaction_id=None,
    )
    defaults.update(overrides)
    sale = Sale(**defaults)
    sale.id = overrides.get("id", uuid.uuid4())
    sale.created_at = datetime.now(timezone.utc)
    sale.updated_at = datetime.now(timezone.utc)
    return sale


def _make_inventory(product_id=None, **overrides):
    defaults = dict(
        product_id=product_id or uuid.uuid4(),
        quantity_on_hand=100,
        quantity_reserved=0,
        low_stock_threshold=10,
        last_replenished_at=None,
    )
    defaults.update(overrides)
    inv = InventoryLevel(**defaults)
    inv.id = overrides.get("id", uuid.uuid4())
    inv.created_at = datetime.now(timezone.utc)
    inv.updated_at = datetime.now(timezone.utc)
    return inv


def _mock_db():
    """Return a flexible AsyncMock db."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.delete = AsyncMock()
    return db


def _mock_db_with_execute(scalar_result=None, scalars_result=None):
    db = _mock_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    result_mock.scalar.return_value = scalar_result
    if scalars_result is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_result
        result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Service tests - create_sale
# ---------------------------------------------------------------------------


class TestCreateSale:
    @pytest.mark.asyncio
    async def test_create_sale_success(self):
        product = _make_product(id=uuid.uuid4())
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=100)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Product lookup
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                # get_inventory_level (inside adjust_stock)
                result.scalar_one_or_none.return_value = inventory
            elif call_count == 3:
                # fifo_deduct batch query (no batches)
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product.id,
            quantity=5,
            unit_price=Decimal("150"),
            sale_date=date(2026, 3, 15),
            channel="retail",
        )
        sale = await create_sale(db, data, uuid.uuid4())
        assert sale.quantity == 5
        assert sale.total_amount == Decimal("750")
        assert sale.status == SaleStatus.COMPLETED
        # Inventory should be depleted
        assert inventory.quantity_on_hand == 95
        # FIFO fields set (no batches => cogs=0)
        assert sale.fifo_cogs == Decimal("0")
        assert sale.fifo_gross_profit == Decimal("750")

    @pytest.mark.asyncio
    async def test_create_sale_product_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        data = SaleCreate(
            product_id=uuid.uuid4(),
            quantity=1,
            unit_price=Decimal("10"),
            sale_date=date(2026, 3, 15),
            channel="retail",
        )
        from src.products.exceptions import ProductNotFoundError

        with pytest.raises(ProductNotFoundError):
            await create_sale(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_sale_inactive_product(self):
        product = _make_product(is_active=False)
        db = _mock_db_with_execute(scalar_result=product)
        data = SaleCreate(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10"),
            sale_date=date(2026, 3, 15),
            channel="retail",
        )
        with pytest.raises(SaleValidationError):
            await create_sale(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_sale_insufficient_stock(self):
        product = _make_product(id=uuid.uuid4())
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=3)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product.id,
            quantity=10,  # more than available
            unit_price=Decimal("150"),
            sale_date=date(2026, 3, 15),
            channel="retail",
        )
        with pytest.raises(InvalidStockAdjustmentError):
            await create_sale(db, data, uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - get/list sales
# ---------------------------------------------------------------------------


class TestGetListSales:
    @pytest.mark.asyncio
    async def test_get_sale_success(self):
        sale = _make_sale()
        db = _mock_db_with_execute(scalar_result=sale)
        result = await get_sale(db, sale.id)
        assert result.id == sale.id

    @pytest.mark.asyncio
    async def test_get_sale_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(SaleNotFoundError):
            await get_sale(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_sales_empty(self):
        db = _mock_db()
        # Two calls: count + query
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        list_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await list_sales(db)
        assert total == 0
        assert items == []


# ---------------------------------------------------------------------------
# Service tests - update_sale
# ---------------------------------------------------------------------------


class TestUpdateSale:
    @pytest.mark.asyncio
    async def test_update_sale_notes(self):
        sale = _make_sale()
        db = _mock_db_with_execute(scalar_result=sale)

        data = SaleUpdate(notes="Updated note")
        result = await update_sale(db, sale.id, data, uuid.uuid4())
        assert result.notes == "Updated note"
        # Audit entry should be added
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_sale_quantity_adjusts_inventory(self):
        product_id = uuid.uuid4()
        sale = _make_sale(product_id=product_id, quantity=5)
        inventory = _make_inventory(product_id=product_id, quantity_on_hand=95)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # get_sale
                result.scalar_one_or_none.return_value = sale
            elif call_count == 2:
                # get_inventory_level (inside adjust_stock)
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleUpdate(quantity=3)
        result = await update_sale(db, sale.id, data, uuid.uuid4())
        assert result.quantity == 3
        # Stock should be restored: 95 + (5-3) = 97
        assert inventory.quantity_on_hand == 97

    @pytest.mark.asyncio
    async def test_update_voided_sale_raises(self):
        sale = _make_sale(status=SaleStatus.VOIDED)
        db = _mock_db_with_execute(scalar_result=sale)

        data = SaleUpdate(notes="Try to update")
        with pytest.raises(SaleAlreadyVoidedError):
            await update_sale(db, sale.id, data, uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - void_sale
# ---------------------------------------------------------------------------


class TestVoidSale:
    @pytest.mark.asyncio
    async def test_void_sale_success(self):
        product_id = uuid.uuid4()
        sale = _make_sale(product_id=product_id, quantity=5)
        inventory = _make_inventory(product_id=product_id, quantity_on_hand=95)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # get_sale
                result.scalar_one_or_none.return_value = sale
            elif call_count == 2:
                # get_inventory_level (inside adjust_stock)
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        result = await void_sale(db, sale.id, "Customer return", uuid.uuid4())
        assert result.status == SaleStatus.VOIDED
        # Stock should be restored: 95 + 5 = 100
        assert inventory.quantity_on_hand == 100

    @pytest.mark.asyncio
    async def test_void_already_voided_raises(self):
        sale = _make_sale(status=SaleStatus.VOIDED)
        db = _mock_db_with_execute(scalar_result=sale)
        with pytest.raises(SaleAlreadyVoidedError):
            await void_sale(db, sale.id, "reason", uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - bulk upload
# ---------------------------------------------------------------------------


class TestBulkUpload:
    @pytest.mark.asyncio
    async def test_bulk_upload_valid_csv(self):
        product = _make_product(id=uuid.uuid4())
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=100)

        db = _mock_db()

        # Track how many create_sale calls happen via execute calls
        async def mock_execute(stmt):
            result = MagicMock()
            # Product lookup or inventory lookup both return correct objects
            result.scalar_one_or_none.return_value = product
            result.scalar.return_value = None
            # For inventory lookups, we need to return inventory too
            # Use a simple approach: return product for product queries, inventory for inventory queries
            return result

        db.execute = mock_execute

        # But we need inventory to work - patch adjust_stock behavior
        # Since this is complex with multiple calls, let's use a simpler approach
        call_count = 0

        async def mock_execute_multi(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # Each create_sale: 1=product, 2=inventory, 3=fifo batches, 4=lot FIFO
            phase = (call_count - 1) % 4
            if phase == 0:
                result.scalar_one_or_none.return_value = product
            elif phase == 1:
                result.scalar_one_or_none.return_value = inventory
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            return result

        db.execute = mock_execute_multi

        csv_content = (
            "product_id,quantity,unit_price,sale_date,channel\n"
            f"{product.id},2,150.00,2026-03-15,retail\n"
            f"{product.id},3,150.00,2026-03-16,online\n"
        ).encode("utf-8")

        job = await process_bulk_upload(db, csv_content, "test.csv", uuid.uuid4())
        assert job.total_rows == 2
        assert job.successful_rows == 2
        assert job.failed_rows == 0

    @pytest.mark.asyncio
    async def test_bulk_upload_missing_headers(self):
        from src.sales.exceptions import InvalidCSVFormatError

        db = _mock_db()

        csv_content = b"product_id,quantity\n123,5\n"
        with pytest.raises(InvalidCSVFormatError):
            await process_bulk_upload(db, csv_content, "bad.csv", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_bulk_upload_invalid_utf8(self):
        from src.sales.exceptions import InvalidCSVFormatError

        db = _mock_db()
        with pytest.raises(InvalidCSVFormatError):
            await process_bulk_upload(db, b"\xff\xfe", "bad.csv", uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    @pytest.mark.asyncio
    async def test_get_audit_trail(self):
        sale = _make_sale()
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # get_sale
                result.scalar_one_or_none.return_value = sale
            else:
                # audit entries
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            return result

        db.execute = mock_execute

        entries = await get_sale_audit_trail(db, sale.id)
        assert entries == []


# ---------------------------------------------------------------------------
# Service tests - sales summary
# ---------------------------------------------------------------------------


class TestSalesSummary:
    @pytest.mark.asyncio
    async def test_get_sales_summary(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.one.return_value = (Decimal("1500"), 10, 3)
        db.execute = AsyncMock(return_value=result_mock)

        summary = await get_sales_summary(db, date(2026, 3, 1), date(2026, 3, 31))
        assert summary.total_revenue == Decimal("1500")
        assert summary.total_units_sold == 10
        assert summary.transaction_count == 3


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestSalesEndpoints:
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

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user
        u = _make_user()
        async def _fake_auth():
            return u
        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def test_create_sale_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/sales",
                json={
                    "product_id": str(uuid.uuid4()),
                    "quantity": 5,
                    "unit_price": "150.00",
                    "sale_date": "2026-03-15",
                    "channel": "retail",
                },
            )
        assert resp.status_code == 401

    def test_get_sale_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/{fake_id}")
        assert resp.status_code == 404

    def test_list_sales_empty(self):
        self._override_auth()
        db = _mock_db()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        list_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_result, list_result])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_void_sale_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.delete(f"/api/v1/sales/{fake_id}")
        assert resp.status_code == 401

    def test_upload_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/sales/upload",
                files={"file": ("test.csv", b"data", "text/csv")},
            )
        assert resp.status_code == 401

    def test_sales_summary(self):
        self._override_auth()
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.one.return_value = (Decimal("0"), 0, 0)
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/summary?date_from=2026-03-01&date_to=2026-03-31")
        assert resp.status_code == 200
        data = resp.json()
        assert data["transaction_count"] == 0


# ---------------------------------------------------------------------------
# CSV Export endpoint tests
# ---------------------------------------------------------------------------


class TestSalesExportEndpoint:
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

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user
        u = _make_user()
        async def _fake_auth():
            return u
        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def _make_execute_side_effects(self, sales: list):
        """Return two execute side effects: count then list."""
        count_result = MagicMock()
        count_result.scalar.return_value = len(sales)
        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = sales
        list_result.scalars.return_value = scalars_mock
        return [count_result, list_result]

    def test_export_sales_csv_returns_csv_content_type(self):
        self._override_auth()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/export.csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_sales_csv_has_correct_headers(self):
        self._override_auth()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/export.csv")

        assert resp.status_code == 200
        first_line = resp.text.splitlines()[0]
        assert "sale_date" in first_line
        assert "quantity" in first_line
        assert "total_amount" in first_line
        assert "status" in first_line

    def test_export_sales_csv_content_disposition(self):
        self._override_auth()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/export.csv")

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert ".csv" in resp.headers.get("content-disposition", "")

    def test_export_sales_csv_with_data_row(self):
        self._override_auth()
        product_id = uuid.uuid4()
        sale = _make_sale(product_id=product_id)
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([sale]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/export.csv")

        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        # Header + 1 data row
        assert len(lines) == 2
        # Data row should contain the sale date
        assert "2026-03-15" in lines[1]


# ---------------------------------------------------------------------------
# Quick Quote tests
# ---------------------------------------------------------------------------


class TestQuickQuote:
    @pytest.mark.asyncio
    async def test_quick_quote_two_batches_different_costs(self):
        """Weighted average landed cost across two FIFO batches."""
        from src.inventory.models import InventoryBatch
        from src.inventory.service import compute_landed_cost
        from src.sales.service import quick_quote

        product_id = uuid.uuid4()
        batch1 = InventoryBatch(
            product_id=product_id,
            order_id=uuid.uuid4(),
            quantity_received=10,
            quantity_remaining=10,
            unit_cost_usd=Decimal("10"),
            fx_rate_at_arrival=Decimal("1500"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=compute_landed_cost(
                Decimal("10"), Decimal("1500"), Decimal("0")
            ),
            received_at=date(2026, 1, 1),
            created_at=datetime.now(timezone.utc),
        )
        batch1.id = uuid.uuid4()

        batch2 = InventoryBatch(
            product_id=product_id,
            order_id=uuid.uuid4(),
            quantity_received=20,
            quantity_remaining=20,
            unit_cost_usd=Decimal("12"),
            fx_rate_at_arrival=Decimal("1600"),
            logistics_allocation_per_unit=Decimal("100"),
            landed_cost_per_unit=compute_landed_cost(
                Decimal("12"), Decimal("1600"), Decimal("100")
            ),
            received_at=date(2026, 2, 1),
            created_at=datetime.now(timezone.utc),
        )
        batch2.id = uuid.uuid4()

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [batch1, batch2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        quote = await quick_quote(db, product_id, 15)

        # batch1: 10 units @ 15000, batch2: 5 units @ 19300
        # total cost = 150000 + 96500 = 246500
        # avg = 246500 / 15 = 16433.333333
        assert quote.product_id == product_id
        assert quote.quantity == 15
        assert quote.fifo_landed_cost_per_unit == Decimal("16433.333333")
        assert quote.floor_margin_pct == Decimal("15")
        # min_sell = 16433.333333 * 1.15 = 18898.333333 (rounded)
        expected_min = (Decimal("16433.333333") * Decimal("1.15")).quantize(
            Decimal("0.000001")
        )
        assert quote.min_sell_price_per_unit == expected_min
        assert quote.total_min_price == (expected_min * Decimal("15")).quantize(
            Decimal("0.000001")
        )

    @pytest.mark.asyncio
    async def test_quick_quote_no_batches_returns_zero(self):
        """No batches available returns all-zero response."""
        from src.sales.service import quick_quote

        product_id = uuid.uuid4()
        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        quote = await quick_quote(db, product_id, 10)

        assert quote.product_id == product_id
        assert quote.quantity == 10
        assert quote.fifo_landed_cost_per_unit == Decimal("0")
        assert quote.min_sell_price_per_unit == Decimal("0")
        assert quote.total_min_price == Decimal("0")


# ---------------------------------------------------------------------------
# Service tests - discount_amount support
# ---------------------------------------------------------------------------


class TestCreateSaleWithDiscount:
    @pytest.mark.asyncio
    async def test_create_sale_with_discount_adjusts_total(self):
        """discount_amount reduces total_amount and is stored on the sale."""
        product = _make_product(id=uuid.uuid4())
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=100)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            elif call_count == 3:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product.id,
            quantity=5,
            unit_price=Decimal("150"),
            sale_date=date(2026, 3, 15),
            channel="retail",
            discount_amount=Decimal("50"),
        )
        sale = await create_sale(db, data, uuid.uuid4())
        # total = unit_price * qty - discount = 150 * 5 - 50 = 700
        assert sale.total_amount == Decimal("700")
        assert sale.discount_amount == Decimal("50")

    @pytest.mark.asyncio
    async def test_create_sale_discount_exceeds_gross_raises(self):
        """Discount larger than gross amount raises SaleValidationError."""
        product = _make_product(id=uuid.uuid4())
        db = _mock_db_with_execute(scalar_result=product)

        data = SaleCreate(
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("100"),
            sale_date=date(2026, 3, 15),
            channel="retail",
            discount_amount=Decimal("300"),  # 300 > 100*2 = 200
        )
        with pytest.raises(SaleValidationError):
            await create_sale(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_sale_without_discount_uses_full_price(self):
        """Without discount_amount, total_amount = unit_price * quantity."""
        product = _make_product(id=uuid.uuid4())
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=100)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            elif call_count == 3:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product.id,
            quantity=5,
            unit_price=Decimal("150"),
            sale_date=date(2026, 3, 15),
            channel="retail",
        )
        sale = await create_sale(db, data, uuid.uuid4())
        # total = 150 * 5 = 750
        assert sale.total_amount == Decimal("750")
        assert sale.discount_amount is None


# ---------------------------------------------------------------------------
# Role-based access tests
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_require_admin_rejects_sales_manager(self):
        """SALES_MANAGER role must be rejected by require_admin dependency."""
        from src.auth.dependencies import require_admin
        from src.auth.models import UserRole

        user = _make_user(role=UserRole.SALES_MANAGER)
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(current_user=user)
        assert exc_info.value.status_code == 403
        assert "Admin role required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self):
        """ADMIN role should pass require_admin dependency."""
        from src.auth.dependencies import require_admin
        from src.auth.models import UserRole

        user = _make_user(role=UserRole.ADMIN)
        result = await require_admin(current_user=user)
        assert result.role == UserRole.ADMIN


# ---------------------------------------------------------------------------
# Service tests - transaction grouping (task #64)
# ---------------------------------------------------------------------------


class TestSaleTransactions:
    @pytest.mark.asyncio
    async def test_list_transactions_groups_sales_by_transaction_id(self):
        """Sales sharing a transaction_id are returned as one grouped transaction."""
        from src.sales.service import list_transactions

        txn_id = uuid.uuid4()
        sale1 = _make_sale(transaction_id=txn_id, total_amount=Decimal("300"))
        sale2 = _make_sale(transaction_id=txn_id, total_amount=Decimal("200"))

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # COUNT distinct transaction_ids
                result.scalar.return_value = 1
            elif call_count == 2:
                # Distinct transaction_id rows
                result.all.return_value = [(txn_id,)]
            elif call_count == 3:
                # Sales for the transaction
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [sale1, sale2]
                result.scalars.return_value = scalars_mock
            return result

        db.execute = mock_execute

        transactions, total = await list_transactions(db)
        assert total == 1
        assert len(transactions) == 1
        txn = transactions[0]
        assert txn.transaction_id == txn_id
        assert txn.item_count == 2
        assert txn.total_amount == Decimal("500")
        assert txn.status == "completed"

    @pytest.mark.asyncio
    async def test_get_transaction_returns_items(self):
        """get_transaction returns a SaleTransactionRead with all items."""
        from src.sales.service import get_transaction

        txn_id = uuid.uuid4()
        sale1 = _make_sale(transaction_id=txn_id, total_amount=Decimal("150"))
        sale2 = _make_sale(transaction_id=txn_id, total_amount=Decimal("300"))

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale1, sale2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        txn = await get_transaction(db, txn_id)
        assert txn.transaction_id == txn_id
        assert txn.item_count == 2
        assert txn.total_amount == Decimal("450")
        assert len(txn.items) == 2

    @pytest.mark.asyncio
    async def test_get_transaction_not_found_raises(self):
        """get_transaction raises SaleNotFoundError when no sales match."""
        from src.sales.service import get_transaction

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(SaleNotFoundError):
            await get_transaction(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_sale_stores_transaction_id(self):
        """create_sale stores transaction_id on the Sale when provided."""
        product = _make_product(id=uuid.uuid4())
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=100)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            elif call_count == 3:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        txn_id = uuid.uuid4()
        data = SaleCreate(
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("100"),
            sale_date=date(2026, 3, 15),
            channel="retail",
            transaction_id=txn_id,
        )
        sale = await create_sale(db, data, uuid.uuid4())
        assert sale.transaction_id == txn_id


# ---------------------------------------------------------------------------
# Tests for lot FIFO deduction (Task #75)
# ---------------------------------------------------------------------------


class TestLotFifoDeduction:
    """Recording a sale deducts units_remaining from oldest active lot (FIFO)."""

    @pytest.mark.asyncio
    async def test_sale_deducts_fifo_from_oldest_lot(self):
        """Selling units deducts from the lot with the oldest order_date first."""
        from src.orders.models import OrderLineItem, PurchaseOrder, OrderStatus
        from src.sales.service import create_sale

        product_id = uuid.uuid4()
        product = _make_product(id=product_id)

        # Older lot — should be deducted first
        old_order = MagicMock()
        old_order.order_date = date(2026, 1, 1)
        old_order.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        old_lot = MagicMock(spec=OrderLineItem)
        old_lot.product_id = product_id
        old_lot.units_remaining = Decimal("30")
        old_lot.order = old_order

        # Newer lot — only deducted if old is exhausted
        new_order = MagicMock()
        new_order.order_date = date(2026, 3, 1)
        new_order.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        new_lot = MagicMock(spec=OrderLineItem)
        new_lot.product_id = product_id
        new_lot.units_remaining = Decimal("50")
        new_lot.order = new_order

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # product lookup
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:  # lot FIFO query (adjust_stock + fifo_deduct are patched)
                result.scalars.return_value.all.return_value = [old_lot, new_lot]
            else:
                result.scalar_one_or_none.return_value = None
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        with patch("src.sales.service.adjust_stock", new_callable=AsyncMock), \
             patch("src.sales.service.fifo_deduct", new_callable=AsyncMock, return_value=Decimal("0")):
            data = SaleCreate(
                product_id=product_id,
                quantity=10,
                unit_price=Decimal("20000"),
                sale_date=date.today(),
                channel="retail",
            )
            await create_sale(db, data, uuid.uuid4())

        # Oldest lot should be deducted
        assert old_lot.units_remaining == Decimal("20")
        assert new_lot.units_remaining == Decimal("50")  # untouched

    @pytest.mark.asyncio
    async def test_sale_spills_to_next_lot(self):
        """When a sale quantity exceeds the oldest lot, remainder spills to next lot."""
        from src.orders.models import OrderLineItem
        from src.sales.service import create_sale

        product_id = uuid.uuid4()
        product = _make_product(id=product_id)

        old_order = MagicMock()
        old_order.order_date = date(2026, 1, 1)
        old_order.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        old_lot = MagicMock(spec=OrderLineItem)
        old_lot.product_id = product_id
        old_lot.units_remaining = Decimal("5")  # only 5 left
        old_lot.order = old_order

        new_order = MagicMock()
        new_order.order_date = date(2026, 3, 1)
        new_order.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        new_lot = MagicMock(spec=OrderLineItem)
        new_lot.product_id = product_id
        new_lot.units_remaining = Decimal("50")
        new_lot.order = new_order

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # product lookup
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:  # lot FIFO query
                result.scalars.return_value.all.return_value = [old_lot, new_lot]
            else:
                result.scalar_one_or_none.return_value = None
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        with patch("src.sales.service.adjust_stock", new_callable=AsyncMock), \
             patch("src.sales.service.fifo_deduct", new_callable=AsyncMock, return_value=Decimal("0")):
            data = SaleCreate(
                product_id=product_id,
                quantity=12,  # more than old_lot has
                unit_price=Decimal("20000"),
                sale_date=date.today(),
                channel="retail",
            )
            await create_sale(db, data, uuid.uuid4())

        assert old_lot.units_remaining == Decimal("0")   # fully consumed


# ---------------------------------------------------------------------------
# IDOR ownership checks
# ---------------------------------------------------------------------------


class TestSalesOwnershipChecks:
    """Non-admin users can only access sales they recorded."""

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

    def _override_auth_as(self, user):
        from src.auth.dependencies import get_current_active_user
        async def _fake_auth():
            return user
        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def test_user_cannot_read_other_users_sale(self):
        """Non-admin cannot GET a sale recorded by someone else."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        requester = _make_user(role=UserRole.SALES_MANAGER)
        sale = _make_sale(recorded_by=owner.id)
        db = _mock_db_with_execute(scalar_result=sale)
        self._override_db(db)
        self._override_auth_as(requester)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/{sale.id}")
        assert resp.status_code == 403

    def test_user_can_read_own_sale(self):
        """User can GET a sale they recorded."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        sale = _make_sale(recorded_by=owner.id)
        db = _mock_db_with_execute(scalar_result=sale)
        self._override_db(db)
        self._override_auth_as(owner)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/{sale.id}")
        assert resp.status_code == 200

    def test_admin_can_read_any_sale(self):
        """Admin bypasses ownership check and can GET any sale."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        admin = _make_user(role=UserRole.ADMIN)
        sale = _make_sale(recorded_by=owner.id)
        db = _mock_db_with_execute(scalar_result=sale)
        self._override_db(db)
        self._override_auth_as(admin)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/{sale.id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Service tests - update_transaction
# ---------------------------------------------------------------------------


class TestUpdateTransaction:
    @pytest.mark.asyncio
    async def test_happy_path_updates_all_items_in_group(self):
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        user_id = uuid.uuid4()
        sale1 = _make_sale(transaction_id=txn_id, payment_method="cash", notes=None, recorded_by=user_id)
        sale2 = _make_sale(transaction_id=txn_id, payment_method="cash", notes=None, recorded_by=user_id)

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale1, sale2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        data = SaleTransactionUpdate(payment_method="transfer", notes="Group note")
        updated = await update_transaction(db, txn_id, data, user_id)

        assert sale1.payment_method == "transfer"
        assert sale2.payment_method == "transfer"
        assert sale1.notes == "Group note"
        assert sale2.notes == "Group note"
        assert len(updated) == 2

    @pytest.mark.asyncio
    async def test_not_found_raises_error(self):
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(SaleNotFoundError):
            await update_transaction(
                db, uuid.uuid4(), SaleTransactionUpdate(payment_method="cash"), uuid.uuid4()
            )

    @pytest.mark.asyncio
    async def test_skips_voided_items_in_mixed_transaction(self):
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        user_id = uuid.uuid4()
        active = _make_sale(transaction_id=txn_id, payment_method="cash", notes=None, recorded_by=user_id)
        voided = _make_sale(
            transaction_id=txn_id, payment_method="cash", notes=None, status=SaleStatus.VOIDED, recorded_by=user_id
        )

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [active, voided]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        await update_transaction(db, txn_id, SaleTransactionUpdate(payment_method="transfer"), user_id)

        assert active.payment_method == "transfer"
        assert voided.payment_method == "cash"  # unchanged

    @pytest.mark.asyncio
    async def test_all_voided_raises_error(self):
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        user_id = uuid.uuid4()
        voided1 = _make_sale(
            transaction_id=txn_id, payment_method="cash", notes=None, status=SaleStatus.VOIDED, recorded_by=user_id
        )
        voided2 = _make_sale(
            transaction_id=txn_id, payment_method="cash", notes=None, status=SaleStatus.VOIDED, recorded_by=user_id
        )

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [voided1, voided2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(SaleAlreadyVoidedError):
            await update_transaction(
                db, txn_id, SaleTransactionUpdate(payment_method="transfer"), user_id
            )

    @pytest.mark.asyncio
    async def test_payment_amount_propagated_to_all_items(self):
        from decimal import Decimal as D
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        user_id = uuid.uuid4()
        sale1 = _make_sale(transaction_id=txn_id, payment_method="cash", notes=None, recorded_by=user_id)
        sale2 = _make_sale(transaction_id=txn_id, payment_method="cash", notes=None, recorded_by=user_id)

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale1, sale2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        await update_transaction(db, txn_id, SaleTransactionUpdate(payment_amount=D("5000.00")), user_id)

        assert sale1.payment_amount == D("5000.00")
        assert sale2.payment_amount == D("5000.00")

    @pytest.mark.asyncio
    async def test_permission_denied_for_non_owner(self):
        from src.sales.exceptions import SalePermissionError
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        requester_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, recorded_by=owner_id)

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(SalePermissionError):
            await update_transaction(
                db, txn_id, SaleTransactionUpdate(payment_method="cash"), requester_id
            )

    @pytest.mark.asyncio
    async def test_admin_bypasses_ownership_check(self):
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, recorded_by=owner_id, payment_method="cash")

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        await update_transaction(db, txn_id, SaleTransactionUpdate(payment_method="transfer"), admin_id, is_admin=True)
        assert sale.payment_method == "transfer"


# ---------------------------------------------------------------------------
# HTTP endpoint tests - update_transaction_endpoint
# ---------------------------------------------------------------------------


class TestUpdateTransactionEndpoint:
    """HTTP-level tests for PUT /api/v1/sales/transactions/{transaction_id}."""

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

    def _override_auth_as(self, user):
        from src.auth.dependencies import get_current_active_user

        async def _fake_auth():
            return user

        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def _make_scalars_execute(self, sales):
        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = sales
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)
        return db

    def test_returns_404_when_transaction_not_found(self):
        from src.auth.models import UserRole

        owner = _make_user(role=UserRole.ADMIN)
        db = self._make_scalars_execute([])
        self._override_db(db)
        self._override_auth_as(owner)

        with TestClient(self.app) as client:
            resp = client.put(
                f"/api/v1/sales/transactions/{uuid.uuid4()}",
                json={"payment_method": "cash"},
            )
        assert resp.status_code == 404

    def test_returns_403_when_user_does_not_own_transaction(self):
        from src.auth.models import UserRole

        owner = _make_user(role=UserRole.SALES_MANAGER)
        requester = _make_user(role=UserRole.SALES_MANAGER)
        txn_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, recorded_by=owner.id)

        db = self._make_scalars_execute([sale])
        self._override_db(db)
        self._override_auth_as(requester)

        with TestClient(self.app) as client:
            resp = client.put(
                f"/api/v1/sales/transactions/{txn_id}",
                json={"payment_method": "cash"},
            )
        assert resp.status_code == 403

    def test_admin_can_update_any_transaction(self):
        """Admin bypasses ownership check."""
        from src.auth.models import UserRole

        owner = _make_user(role=UserRole.SALES_MANAGER)
        admin = _make_user(role=UserRole.ADMIN)
        txn_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, recorded_by=owner.id)

        # First execute call: update_transaction query
        # Second execute call: get_transaction query
        db = _mock_db()
        result_with_sale = MagicMock()
        scalars_with_sale = MagicMock()
        scalars_with_sale.all.return_value = [sale]
        result_with_sale.scalars.return_value = scalars_with_sale
        db.execute = AsyncMock(return_value=result_with_sale)
        self._override_db(db)
        self._override_auth_as(admin)

        with TestClient(self.app) as client:
            resp = client.put(
                f"/api/v1/sales/transactions/{txn_id}",
                json={"payment_method": "transfer"},
            )
        # 200 (not 403) — admin bypasses ownership
        assert resp.status_code == 200

    def test_invalid_payment_method_returns_422(self):
        from src.auth.models import UserRole

        admin = _make_user(role=UserRole.ADMIN)
        db = _mock_db()
        self._override_db(db)
        self._override_auth_as(admin)

        with TestClient(self.app) as client:
            resp = client.put(
                f"/api/v1/sales/transactions/{uuid.uuid4()}",
                json={"payment_method": "bitcoin"},
            )
        assert resp.status_code == 422

    def test_returns_409_when_all_items_voided(self):
        from src.auth.models import UserRole

        user = _make_user(role=UserRole.SALES_MANAGER)
        txn_id = uuid.uuid4()
        voided = _make_sale(
            transaction_id=txn_id, recorded_by=user.id, status=SaleStatus.VOIDED
        )

        db = self._make_scalars_execute([voided])
        self._override_db(db)
        self._override_auth_as(user)

        with TestClient(self.app) as client:
            resp = client.put(
                f"/api/v1/sales/transactions/{txn_id}",
                json={"payment_method": "cash"},
            )
        assert resp.status_code == 409
