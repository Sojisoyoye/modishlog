"""Tests for suppliers CRUD and detail tab queries."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.suppliers.exceptions import SupplierNotFoundError
from src.suppliers.models import PayTermType, Supplier
from src.suppliers.schemas import SupplierCreate, SupplierUpdate
from src.suppliers.service import (
    create_supplier,
    get_supplier,
    get_supplier_activities,
    get_supplier_ledger,
    get_supplier_purchases,
    get_supplier_stock_report,
    list_suppliers,
    update_supplier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supplier(**overrides):
    defaults = dict(
        name="Acme Imports Ltd",
        contact_person="John Doe",
        email="john@acme.com",
        mobile="+2348000000001",
        alternate_number=None,
        tax_number="TIN-123456",
        address_line_1="10 Trade Road",
        address_line_2=None,
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        zip_code="100001",
        pay_term_number=30,
        pay_term_type=PayTermType.DAYS,
        opening_balance=Decimal("0"),
        notes=None,
        is_active=True,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    supplier = Supplier(**defaults)
    supplier.id = overrides.get("id", uuid.uuid4())
    supplier.created_at = datetime.now(timezone.utc)
    supplier.updated_at = datetime.now(timezone.utc)
    supplier.products = overrides.get("products", [])
    return supplier


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
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
# create_supplier
# ---------------------------------------------------------------------------


class TestCreateSupplier:
    @pytest.mark.asyncio
    async def test_create_supplier_happy_path(self):
        user_id = uuid.uuid4()
        db = _mock_db()
        data = SupplierCreate(
            name="Best Traders",
            contact_person="Jane Smith",
            email="jane@besttraders.com",
            mobile="+2348011111111",
            pay_term_number=14,
            pay_term_type="days",
        )
        supplier = await create_supplier(db, data, user_id)

        assert supplier.name == "Best Traders"
        assert supplier.contact_person == "Jane Smith"
        assert supplier.pay_term_number == 14
        assert supplier.pay_term_type == PayTermType.DAYS
        assert supplier.created_by == user_id
        assert supplier.is_active is True
        assert supplier.opening_balance == Decimal("0")
        db.add.assert_called_once()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_supplier_minimal_fields(self):
        """Only name is required — all other fields optional."""
        db = _mock_db()
        data = SupplierCreate(name="Minimal Supplier")
        supplier = await create_supplier(db, data, uuid.uuid4())

        assert supplier.name == "Minimal Supplier"
        assert supplier.email is None
        assert supplier.mobile is None
        assert supplier.pay_term_number is None
        assert supplier.pay_term_type is None

    @pytest.mark.asyncio
    async def test_create_supplier_with_opening_balance(self):
        db = _mock_db()
        data = SupplierCreate(
            name="Balance Supplier",
            opening_balance=Decimal("50000.00"),
        )
        supplier = await create_supplier(db, data, uuid.uuid4())
        assert supplier.opening_balance == Decimal("50000.00")


# ---------------------------------------------------------------------------
# get_supplier
# ---------------------------------------------------------------------------


class TestGetSupplier:
    @pytest.mark.asyncio
    async def test_get_supplier_found(self):
        supplier = _make_supplier()
        db = _mock_db_with_execute(scalar_result=supplier)
        result = await get_supplier(db, supplier.id)
        assert result.id == supplier.id

    @pytest.mark.asyncio
    async def test_get_supplier_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(SupplierNotFoundError):
            await get_supplier(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# list_suppliers
# ---------------------------------------------------------------------------


class TestListSuppliers:
    @pytest.mark.asyncio
    async def test_list_suppliers_returns_all(self):
        suppliers = [_make_supplier(name=f"Supplier {i}") for i in range(3)]
        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 3
        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = suppliers
        items_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        result, total = await list_suppliers(db)
        assert total == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_suppliers_with_search(self):
        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 1
        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [_make_supplier(name="Acme")]
        items_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        result, total = await list_suppliers(db, search="Acme")
        assert total == 1


# ---------------------------------------------------------------------------
# update_supplier
# ---------------------------------------------------------------------------


class TestUpdateSupplier:
    @pytest.mark.asyncio
    async def test_update_supplier_name(self):
        supplier = _make_supplier(name="Old Name")
        db = _mock_db_with_execute(scalar_result=supplier)
        data = SupplierUpdate(name="New Name")
        updated = await update_supplier(db, supplier.id, data)
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_supplier_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(SupplierNotFoundError):
            await update_supplier(db, uuid.uuid4(), SupplierUpdate(name="X"))

    @pytest.mark.asyncio
    async def test_update_supplier_partial(self):
        """Only provided fields are updated."""
        supplier = _make_supplier(email="old@test.com", city="Old City")
        db = _mock_db_with_execute(scalar_result=supplier)
        data = SupplierUpdate(email="new@test.com")
        updated = await update_supplier(db, supplier.id, data)
        assert updated.email == "new@test.com"
        assert updated.city == "Old City"


# ---------------------------------------------------------------------------
# Supplier detail tabs (purchases, stock report, ledger, activities)
# ---------------------------------------------------------------------------


class TestSupplierPurchases:
    @pytest.mark.asyncio
    async def test_get_supplier_purchases_returns_list(self):
        supplier_id = uuid.uuid4()
        db = _mock_db()
        mock_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        mock_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_supplier_purchases(db, supplier_id)
        assert isinstance(result, list)


class TestSupplierLedger:
    @pytest.mark.asyncio
    async def test_get_supplier_ledger_returns_list(self):
        supplier_id = uuid.uuid4()
        db = _mock_db()

        # First execute: orders query (returns empty list)
        orders_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        orders_result.scalars.return_value = scalars_mock

        # Second execute: supplier query (returns None — no opening balance entry)
        supplier_result = MagicMock()
        supplier_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[orders_result, supplier_result])

        result = await get_supplier_ledger(db, supplier_id)
        assert isinstance(result, list)


class TestSupplierStockReport:
    @pytest.mark.asyncio
    async def test_get_supplier_stock_report_returns_list(self):
        supplier_id = uuid.uuid4()
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_supplier_stock_report(db, supplier_id)
        assert isinstance(result, list)


class TestSupplierActivities:
    @pytest.mark.asyncio
    async def test_get_supplier_activities_returns_list(self):
        supplier_id = uuid.uuid4()
        db = _mock_db()
        mock_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        mock_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_supplier_activities(db, supplier_id)
        assert isinstance(result, list)
