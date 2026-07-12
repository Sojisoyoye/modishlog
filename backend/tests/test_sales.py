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
        sale = await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())
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
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

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
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

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
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())


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
    async def test_void_sale_reverses_fifo_consumption(self):
        """Voiding a sale must credit back the exact InventoryBatch rows
        fifo_deduct() consumed for it — restoring InventoryLevel alone
        (via adjust_stock()) leaves InventoryBatch.quantity_remaining
        permanently short, understating COGS on future sales."""
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
                result.scalar_one_or_none.return_value = sale
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        with patch(
            "src.sales.service.reverse_fifo_consumption", new_callable=AsyncMock
        ) as mock_reverse:
            await void_sale(db, sale.id, "Customer return", uuid.uuid4())

        mock_reverse.assert_awaited_once_with(db, [sale.id])

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

        job = await process_bulk_upload(db, csv_content, "test.csv", uuid.uuid4(), business_id=uuid.uuid4())
        assert job.total_rows == 2
        assert job.successful_rows == 2
        assert job.failed_rows == 0

    @pytest.mark.asyncio
    async def test_bulk_upload_missing_headers(self):
        from src.sales.exceptions import InvalidCSVFormatError

        db = _mock_db()

        csv_content = b"product_id,quantity\n123,5\n"
        with pytest.raises(InvalidCSVFormatError):
            await process_bulk_upload(db, csv_content, "bad.csv", uuid.uuid4(), business_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_bulk_upload_invalid_utf8(self):
        from src.sales.exceptions import InvalidCSVFormatError

        db = _mock_db()
        with pytest.raises(InvalidCSVFormatError):
            await process_bulk_upload(db, b"\xff\xfe", "bad.csv", uuid.uuid4(), business_id=uuid.uuid4())


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
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user()
        _business_id = uuid.uuid4()
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return _business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user()
        _business_id = uuid.uuid4()
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return _business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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
        sale = await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())
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
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

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
        sale = await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())
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
    async def test_list_transactions_filter_by_payment_status(self):
        """list_transactions passes payment_status filter and returns matching results."""
        from src.sales.service import list_transactions

        txn_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, payment_status="credit", total_amount=Decimal("500"))

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 1
            elif call_count == 2:
                result.all.return_value = [(txn_id,)]
            elif call_count == 3:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [sale]
                result.scalars.return_value = scalars_mock
            return result

        db.execute = mock_execute
        transactions, total = await list_transactions(db, payment_status="credit")
        assert total == 1
        assert transactions[0].payment_status == "credit"

    @pytest.mark.asyncio
    async def test_list_transactions_filter_no_results(self):
        """list_transactions returns empty list when COUNT is 0 for a filter."""
        from src.sales.service import list_transactions

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 0
            elif call_count == 2:
                result.all.return_value = []
            return result

        db.execute = mock_execute
        transactions, total = await list_transactions(db, payment_status="nonexistent")
        assert total == 0
        assert transactions == []

    @pytest.mark.asyncio
    async def test_list_transactions_filter_by_date_range(self):
        """list_transactions accepts date_from / date_to without raising."""
        from src.sales.service import list_transactions
        from datetime import date as dt_date

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 0
            elif call_count == 2:
                result.all.return_value = []
            return result

        db.execute = mock_execute
        transactions, total = await list_transactions(
            db, date_from=dt_date(2026, 1, 1), date_to=dt_date(2026, 12, 31)
        )
        assert total == 0
        assert transactions == []

    @pytest.mark.asyncio
    async def test_list_transactions_filter_by_customer_name(self):
        """list_transactions filters by customer_name substring (case-insensitive)."""
        from src.sales.service import list_transactions

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 1
            elif call_count == 2:
                result.all.return_value = []
            return result

        db.execute = mock_execute
        transactions, total = await list_transactions(db, customer_name="alice")
        assert total == 1
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_list_transactions_customer_name_empty_returns_all(self):
        """list_transactions with customer_name=None applies no name filter."""
        from src.sales.service import list_transactions

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 5
            elif call_count == 2:
                result.all.return_value = []
            return result

        db.execute = mock_execute
        transactions, total = await list_transactions(db, customer_name=None)
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_transactions_issues_exactly_three_queries_for_full_page(self):
        """list_transactions must run exactly 3 DB queries regardless of page size:
        1. COUNT(DISTINCT transaction_id)
        2. Paginated GROUP BY to get the ordered transaction_id page
        3. Single bulk IN query to fetch all Sale rows for those transaction_ids

        A page of 25 transactions must NOT result in 1+25 individual queries.
        """
        from src.sales.service import list_transactions

        PAGE = 25
        txn_ids = [uuid.uuid4() for _ in range(PAGE)]

        # Build 2 Sale rows per transaction (50 rows total) to confirm grouping works
        all_sales = []
        for tid in txn_ids:
            all_sales.append(_make_sale(transaction_id=tid, total_amount=Decimal("100")))
            all_sales.append(_make_sale(transaction_id=tid, total_amount=Decimal("200")))

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Query 1: COUNT(DISTINCT transaction_id)
                result.scalar.return_value = PAGE
            elif call_count == 2:
                # Query 2: paginated GROUP BY returning txn_id page.
                # The mock returns all PAGE ids unconditionally; in production
                # page_size drives the LIMIT clause — that's SQL correctness, not
                # what this test is measuring.
                result.all.return_value = [(tid,) for tid in txn_ids]
            elif call_count == 3:
                # Query 3: single IN bulk fetch — all rows for the page
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = all_sales
                result.scalars.return_value = scalars_mock
            else:
                # Any 4th+ query means the N+1 bug has regressed
                raise AssertionError(
                    f"list_transactions issued query #{call_count} — expected exactly 3"
                )
            return result

        db.execute = mock_execute

        transactions, total = await list_transactions(db, page_size=PAGE)

        # call_count guard: the else-branch above raises on query 4+, so reaching
        # here already proves ≤ 3 queries. The explicit check documents the contract.
        assert call_count == 3
        assert total == PAGE
        assert len(transactions) == PAGE
        # Each transaction groups 2 items → combined total 300
        assert transactions[0].total_amount == Decimal("300")

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
        sale = await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())
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
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

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
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

        assert old_lot.units_remaining == Decimal("0")   # fully consumed

    @pytest.mark.asyncio
    async def test_without_variant_id_only_matches_untagged_lots(self):
        """A non-variant sale must only draw from variant_id=NULL lots —
        mirrors fifo_deduct()'s inventory_batch_variant_filter() (task 165)
        applied to the parallel OrderLineItem.units_remaining ledger."""
        from src.sales.service import _deduct_lot_units

        db = AsyncMock()
        db.flush = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        await _deduct_lot_units(db, uuid.uuid4(), Decimal("10"))

        executed_stmt = db.execute.call_args[0][0]
        compiled = str(
            executed_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "order_line_items.variant_id is null" in compiled
        assert "order_line_items.variant_id =" not in compiled

    @pytest.mark.asyncio
    async def test_with_variant_id_matches_that_variant_or_untagged_lots(self):
        """A variant-specific sale may draw from its own tagged lots AND
        untagged lots, but never from a sibling variant's tagged lots."""
        from src.sales.service import _deduct_lot_units

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        db = AsyncMock()
        db.flush = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        await _deduct_lot_units(db, product_id, Decimal("10"), variant_id=variant_id)

        executed_stmt = db.execute.call_args[0][0]
        compiled = str(
            executed_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "order_line_items.variant_id is null" in compiled
        assert variant_id.hex in compiled.replace("-", "")
        assert (
            "order_line_items.variant_id = " in compiled
            or "order_line_items.variant_id=" in compiled
        )

    @pytest.mark.asyncio
    async def test_variant_scoped_deduction_never_touches_sibling_variant_lot(self):
        """Deduction-math check: given only the lots a correctly-scoped
        query would return (sibling_lot excluded, matching how the mock
        stands in for the real WHERE clause — see
        test_with_variant_id_matches_that_variant_or_untagged_lots above
        for the actual SQL-shape assertion), consuming from that set must
        leave sibling_lot's own quantity field untouched."""
        from src.orders.models import OrderLineItem
        from src.sales.service import _deduct_lot_units

        product_id = uuid.uuid4()
        variant_a = uuid.uuid4()
        variant_b = uuid.uuid4()

        order = MagicMock()
        order.order_date = date(2026, 1, 1)
        order.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        own_lot = MagicMock(spec=OrderLineItem)
        own_lot.product_id = product_id
        own_lot.variant_id = variant_a
        own_lot.units_remaining = Decimal("50")
        own_lot.order = order

        sibling_lot = MagicMock(spec=OrderLineItem)
        sibling_lot.product_id = product_id
        sibling_lot.variant_id = variant_b
        sibling_lot.units_remaining = Decimal("20")
        sibling_lot.order = order

        db = AsyncMock()
        db.flush = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        # The real query would exclude sibling_lot entirely — simulating
        # that here since the mock doesn't evaluate the WHERE clause itself.
        scalars_mock.all.return_value = [own_lot]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        await _deduct_lot_units(db, product_id, Decimal("10"), variant_id=variant_a)

        assert own_lot.units_remaining == Decimal("40")
        assert sibling_lot.units_remaining == Decimal("20")

    @pytest.mark.asyncio
    async def test_create_sale_passes_variant_id_to_deduct_lot_units(self):
        """A sale of a specific variant must scope its lot-level deduction
        to that variant — otherwise create_sale() would silently pool
        units_remaining across sibling variants of the same product, the
        same bug already fixed for fifo_deduct()/InventoryBatch."""
        from src.sales.service import create_sale

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        product = _make_product(id=product_id, has_variants=True)

        variant = MagicMock()
        variant.id = variant_id
        variant.product_id = product_id
        variant.price_override = None

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # product lookup
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:  # variant lookup
                result.scalar_one_or_none.return_value = variant
            else:
                result.scalar_one_or_none.return_value = None
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        with patch("src.sales.service.adjust_stock", new_callable=AsyncMock), \
             patch("src.sales.service.fifo_deduct", new_callable=AsyncMock, return_value=Decimal("0")), \
             patch("src.sales.service._deduct_lot_units", new_callable=AsyncMock) as mock_deduct_lots:
            data = SaleCreate(
                product_id=product_id,
                variant_id=variant_id,
                quantity=10,
                unit_price=Decimal("20000"),
                sale_date=date.today(),
                channel="retail",
            )
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

        mock_deduct_lots.assert_awaited_once()
        args, kwargs = mock_deduct_lots.call_args
        assert args == (db, product_id, Decimal("10"))
        assert kwargs["variant_id"] == variant_id


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
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        _business_id = uuid.uuid4()
        async def _fake_auth():
            return user
        async def _fake_business_id():
            return _business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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
    async def test_payment_date_propagated_to_all_items(self):
        from datetime import date as date_type
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

        payment_date = date_type(2026, 6, 1)
        await update_transaction(db, txn_id, SaleTransactionUpdate(payment_date=payment_date), user_id)

        assert sale1.payment_date == payment_date
        assert sale2.payment_date == payment_date

    @pytest.mark.asyncio
    def test_payment_date_defaults_to_none_on_sale_create(self):
        """SaleCreate without payment_date should leave the field as None."""
        from datetime import date as date2
        from src.sales.schemas import SaleCreate
        import uuid as _uuid

        data = SaleCreate(
            product_id=_uuid.uuid4(),
            quantity=1,
            unit_price=Decimal("100.00"),
            sale_date=date2.today(),
            channel="retail",
        )
        assert data.payment_date is None
        assert data.payment_amount is None

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

    @pytest.mark.asyncio
    async def test_business_id_scoping_returns_not_found_for_wrong_business(self):
        """Bug 2 — update_transaction with business_id must scope the Sale lookup."""
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        # Empty result simulates no sales matching (transaction_id + wrong business_id)
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(SaleNotFoundError):
            await update_transaction(
                db,
                uuid.uuid4(),
                SaleTransactionUpdate(payment_method="cash"),
                uuid.uuid4(),
                business_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_business_id_scoping_succeeds_for_correct_business(self):
        """Bug 2 — update_transaction with matching business_id should update sales."""
        from src.sales.schemas import SaleTransactionUpdate
        from src.sales.service import update_transaction

        txn_id = uuid.uuid4()
        user_id = uuid.uuid4()
        business_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, payment_method="cash", recorded_by=user_id, business_id=business_id)

        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        updated = await update_transaction(
            db,
            txn_id,
            SaleTransactionUpdate(payment_method="transfer"),
            user_id,
            business_id=business_id,
        )
        assert sale.payment_method == "transfer"
        assert len(updated) == 1


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
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        _business_id = uuid.uuid4()

        async def _fake_auth():
            return user

        async def _fake_business_id():
            return _business_id

        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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


class TestListTransactionsEndpointFilters:
    """HTTP-level tests for GET /api/v1/sales/transactions filter params."""

    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app
        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_db_with_txn(self, txn_id, sales):
        from src.core.database import get_db
        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = len(sales)
            elif call_count == 2:
                result.all.return_value = [(txn_id,)] if sales else []
            elif call_count == 3:
                sm = MagicMock()
                sm.all.return_value = sales
                result.scalars.return_value = sm
            return result

        db.execute = mock_execute

        async def _fake_db():
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user()
        _business_id = uuid.uuid4()
        async def _fake():
            return u
        async def _fake_business_id():
            return _business_id
        self.app.dependency_overrides[get_current_active_user] = _fake
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_filter_by_payment_status_accepted(self):
        """GET /transactions?payment_status=credit returns 200 with matching items."""
        txn_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, payment_status="credit", total_amount=Decimal("1000"))
        self._override_db_with_txn(txn_id, [sale])
        self._override_auth()
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/transactions?payment_status=credit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_filter_by_date_range_accepted(self):
        """GET /transactions?date_from=...&date_to=... returns 200."""
        txn_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, total_amount=Decimal("500"))
        self._override_db_with_txn(txn_id, [sale])
        self._override_auth()
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/transactions?date_from=2026-01-01&date_to=2026-12-31")
        assert resp.status_code == 200

    def test_filter_by_customer_id_accepted(self):
        """GET /transactions?customer_id=<uuid> returns 200."""
        txn_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        sale = _make_sale(transaction_id=txn_id, customer_id=customer_id, total_amount=Decimal("500"))
        self._override_db_with_txn(txn_id, [sale])
        self._override_auth()
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/transactions?customer_id={customer_id}")
        assert resp.status_code == 200


class TestBuildTransactionReadTotalPaid:
    """Unit tests for _build_transaction_read total_paid / sale_due logic."""

    def _run(self, items):
        from src.sales.service import _build_transaction_read
        import uuid as _uuid
        return _build_transaction_read(_uuid.uuid4(), items)

    def test_explicit_payment_amount_used_as_total_paid(self):
        """When payment_amount is set, total_paid equals it regardless of total_amount."""
        txn_id = uuid.uuid4()
        sale = _make_sale(
            transaction_id=txn_id,
            total_amount=Decimal("10000"),
            payment_status="partial",
            payment_amount=Decimal("4000"),
        )
        result = self._run([sale])
        assert result.total_paid == Decimal("4000")
        assert result.sale_due == Decimal("6000")

    def test_paid_status_no_payment_amount_infers_full_total(self):
        """payment_status='paid' with no payment_amount → total_paid = total_amount."""
        txn_id = uuid.uuid4()
        sale = _make_sale(
            transaction_id=txn_id,
            total_amount=Decimal("5000"),
            payment_status="paid",
            payment_amount=None,
        )
        result = self._run([sale])
        assert result.total_paid == Decimal("5000")
        assert result.sale_due == Decimal("0")

    def test_credit_status_no_payment_amount_gives_zero_paid(self):
        """payment_status='credit' with no payment_amount → total_paid = 0."""
        txn_id = uuid.uuid4()
        sale = _make_sale(
            transaction_id=txn_id,
            total_amount=Decimal("8000"),
            payment_status="credit",
            payment_amount=None,
        )
        result = self._run([sale])
        assert result.total_paid == Decimal("0")
        assert result.sale_due == Decimal("8000")

    def test_voided_items_excluded_from_total_amount(self):
        """Voided items are not counted in total_amount or total_paid."""
        txn_id = uuid.uuid4()
        active = _make_sale(
            transaction_id=txn_id,
            total_amount=Decimal("3000"),
            payment_status="paid",
            payment_amount=None,
        )
        voided = _make_sale(
            transaction_id=txn_id,
            total_amount=Decimal("2000"),
            status=SaleStatus.VOIDED,
            payment_status="paid",
            payment_amount=None,
        )
        result = self._run([active, voided])
        assert result.total_amount == Decimal("3000")
        assert result.total_paid == Decimal("3000")
        assert result.sale_due == Decimal("0")


# ---------------------------------------------------------------------------
# Business isolation tests (Task #159)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sales_isolates_by_business():
    """Business B cannot see Business A's sales."""
    business_a_id = uuid.uuid4()
    business_b_id = uuid.uuid4()

    async def fake_execute_a(query):
        r = MagicMock()
        r.scalars.return_value.all.return_value = [MagicMock()]
        r.scalar.return_value = 1
        return r

    async def fake_execute_b(query):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.scalar.return_value = 0
        return r

    db_a, db_b = AsyncMock(), AsyncMock()
    db_a.execute = fake_execute_a
    db_b.execute = fake_execute_b

    result_a = await list_sales(db_a, business_id=business_a_id)
    result_b = await list_sales(db_b, business_id=business_b_id)
    items_a = result_a[0] if isinstance(result_a, tuple) else result_a
    items_b = result_b[0] if isinstance(result_b, tuple) else result_b
    assert len(items_a) > 0
    assert len(items_b) == 0


@pytest.mark.asyncio
async def test_sales_owner_sees_own_data():
    """Business owner can see their own sales."""
    business_id = uuid.uuid4()
    mock_sale = MagicMock()

    async def fake_execute(query):
        r = MagicMock()
        r.scalars.return_value.all.return_value = [mock_sale]
        r.scalar.return_value = 1
        return r

    db = AsyncMock()
    db.execute = fake_execute
    result = await list_sales(db, business_id=business_id)
    items = result[0] if isinstance(result, tuple) else result
    assert len(items) == 1


# ---------------------------------------------------------------------------
# Task #167 — MAX_CSV_ROWS cap on sales bulk upload
# ---------------------------------------------------------------------------


class TestSalesBulkUploadRowCap:
    """Sales bulk upload must reject CSVs exceeding MAX_CSV_ROWS."""

    def _make_csv(self, n_rows: int) -> bytes:
        header = "product_id,quantity,unit_price,sale_date,channel\n"
        rows = "".join(f"{uuid.uuid4()},1,100.00,2024-01-01,POS\n" for _ in range(n_rows))
        return (header + rows).encode("utf-8")

    @pytest.mark.asyncio
    async def test_csv_within_limit_is_accepted(self):
        """A CSV within the row cap must be processed without error."""
        from unittest.mock import patch
        from src.sales.exceptions import InvalidCSVFormatError

        db = _mock_db()
        content = self._make_csv(1)
        with patch("src.sales.service.settings") as mock_settings:
            mock_settings.MAX_CSV_ROWS = 5
            # Should not raise — 1 row < 5 cap
            try:
                await process_bulk_upload(db, content, "ok.csv", uuid.uuid4(), business_id=uuid.uuid4())
            except InvalidCSVFormatError:
                pytest.fail("Should not raise InvalidCSVFormatError within limit")

    @pytest.mark.asyncio
    async def test_csv_exceeding_limit_raises_error(self):
        """A CSV over MAX_CSV_ROWS must raise InvalidCSVFormatError immediately."""
        from unittest.mock import patch
        from src.sales.exceptions import InvalidCSVFormatError

        db = _mock_db()
        content = self._make_csv(6)  # 6 rows > cap of 5
        with patch("src.sales.service.settings") as mock_settings:
            mock_settings.MAX_CSV_ROWS = 5
            with pytest.raises(InvalidCSVFormatError, match="maximum"):
                await process_bulk_upload(db, content, "big.csv", uuid.uuid4(), business_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# Task #160 — Variant-aware sale creation tests
# ---------------------------------------------------------------------------


def _make_variant(product_id=None, price_override=None, cost_price_override=None, **overrides):
    """Build a minimal ProductVariant-like object without requiring the ORM table."""
    from unittest.mock import MagicMock

    variant = MagicMock()
    variant.id = overrides.get("id", uuid.uuid4())
    variant.product_id = product_id or uuid.uuid4()
    variant.price_override = price_override
    variant.cost_price_override = cost_price_override
    variant.is_active = overrides.get("is_active", True)
    variant.name = overrides.get("name", "Variant S")
    variant.sku_suffix = overrides.get("sku_suffix", "-S")
    return variant


class TestCreateSaleVariants:
    @pytest.mark.asyncio
    async def test_create_sale_with_variants_product_no_variant_raises_422(self):
        """Attempting to record a sale for a product with has_variants=True
        without providing variant_id must raise HTTP 422."""
        from fastapi import HTTPException

        product = _make_product(id=uuid.uuid4(), has_variants=True)

        db = _mock_db()

        async def mock_execute(stmt):
            result = MagicMock()
            # First call: product lookup
            result.scalar_one_or_none.return_value = product
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("200"),
            sale_date=date(2026, 7, 9),
            channel="retail",
            # variant_id intentionally omitted
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

        assert exc_info.value.status_code == 422
        assert "variant" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_create_sale_with_variant_id_uses_variant_price(self):
        """When variant_id is provided and the variant has a price_override,
        the sale unit_price must equal the variant price override."""
        product = _make_product(
            id=uuid.uuid4(),
            has_variants=True,
            selling_price=Decimal("150.000000"),
        )
        variant_id = uuid.uuid4()
        variant = _make_variant(
            id=variant_id,
            product_id=product.id,
            price_override=Decimal("175.000000"),
        )
        inventory = _make_inventory(product_id=product.id, quantity_on_hand=50)

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
                # Variant lookup
                result.scalar_one_or_none.return_value = variant
            elif call_count == 3:
                # get_inventory_level (inside adjust_stock) — variant-scoped
                result.scalar_one_or_none.return_value = inventory
            elif call_count == 4:
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
            quantity=3,
            unit_price=None,  # no explicit price — should use variant override
            sale_date=date(2026, 7, 9),
            channel="retail",
            variant_id=variant_id,
        )
        sale = await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

        # Sale price must come from the variant price_override
        assert sale.unit_price == Decimal("175.000000")
        assert sale.total_amount == Decimal("525.000000")  # 175 * 3
        assert sale.variant_id == variant_id

    @pytest.mark.asyncio
    async def test_create_sale_variant_not_found_raises_404(self):
        """Supplying an unrecognised or inactive variant_id must raise HTTP 404."""
        from fastapi import HTTPException

        product = _make_product(id=uuid.uuid4(), has_variants=True)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product
            else:
                # Variant lookup → not found
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("200"),
            sale_date=date(2026, 7, 9),
            channel="retail",
            variant_id=uuid.uuid4(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

        assert exc_info.value.status_code == 404
