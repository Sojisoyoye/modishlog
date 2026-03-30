"""Tests for sales CRUD, inventory integration, and audit trail."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
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

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides):
    from src.auth.models import User

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test User",
        is_active=True,
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
            # Odd calls = product lookup, even calls = inventory lookup
            if call_count % 2 == 1:
                result.scalar_one_or_none.return_value = product
            else:
                result.scalar_one_or_none.return_value = inventory
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
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/{fake_id}")
        assert resp.status_code == 404

    def test_list_sales_empty(self):
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
