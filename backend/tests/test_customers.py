"""Tests for the enriched Customer model (task #159)."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.customers.exceptions import CustomerNotFoundError
from src.customers.models import Customer
from src.customers.schemas import CustomerCreate, CustomerUpdate
from src.customers.service import (
    create_customer,
    get_customer,
    list_customers,
    update_customer,
)
from src.suppliers.models import PayTermType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_customer(**overrides):
    defaults = dict(
        name="Test Customer",
        contact_number="+2348000000001",
        alternate_number=None,
        email="test@example.com",
        address="10 Main Street",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        zip_code="100001",
        tax_number=None,
        pay_term_number=None,
        pay_term_type=None,
        opening_balance=Decimal("0"),
        credit_limit=None,
        is_active=True,
        customer_group=None,
        notes=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    customer = Customer(**defaults)
    customer.id = overrides.get("id", uuid.uuid4())
    customer.created_at = datetime.now(timezone.utc)
    customer.updated_at = datetime.now(timezone.utc)
    return customer


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
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
# create_customer — new fields
# ---------------------------------------------------------------------------


class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_create_customer_with_all_new_fields(self):
        """All 12 new POS fields should be persisted on the model."""
        user_id = uuid.uuid4()
        db = _mock_db()
        data = CustomerCreate(
            name="Ade Traders",
            contact_number="+2348011111111",
            alternate_number="+2348022222222",
            email="ade@traders.ng",
            address="5 Market Lane",
            city="Ibadan",
            state="Oyo",
            country="Nigeria",
            zip_code="200001",
            tax_number="TIN-9876",
            pay_term_number=30,
            pay_term_type="days",
            opening_balance=Decimal("15000.00"),
            credit_limit=Decimal("500000.00"),
            is_active=True,
            customer_group="Wholesale",
        )
        customer = await create_customer(db, data, user_id)

        assert customer.name == "Ade Traders"
        assert customer.alternate_number == "+2348022222222"
        assert customer.city == "Ibadan"
        assert customer.state == "Oyo"
        assert customer.country == "Nigeria"
        assert customer.zip_code == "200001"
        assert customer.tax_number == "TIN-9876"
        assert customer.pay_term_number == 30
        assert customer.pay_term_type == PayTermType.DAYS
        assert customer.opening_balance == Decimal("15000.00")
        assert customer.credit_limit == Decimal("500000.00")
        assert customer.is_active is True
        assert customer.customer_group == "Wholesale"
        assert customer.created_by == user_id
        db.add.assert_called_once()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_customer_minimal_fields_defaults(self):
        """Only name is required; is_active defaults True, opening_balance defaults 0."""
        db = _mock_db()
        data = CustomerCreate(name="Minimal Customer")
        customer = await create_customer(db, data, uuid.uuid4())

        assert customer.name == "Minimal Customer"
        assert customer.is_active is True
        assert customer.opening_balance == Decimal("0")
        assert customer.city is None
        assert customer.credit_limit is None
        assert customer.tax_number is None
        assert customer.customer_group is None


# ---------------------------------------------------------------------------
# list_customers — is_active filter
# ---------------------------------------------------------------------------


class TestListCustomers:
    @pytest.mark.asyncio
    async def test_list_customers_filter_by_is_active_true(self):
        """is_active=True returns only active customers."""
        active = _make_customer(name="Active Co", is_active=True)
        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 1
        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [active]
        items_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        result, total = await list_customers(db, is_active=True)
        assert total == 1
        assert result[0].is_active is True

    @pytest.mark.asyncio
    async def test_list_customers_filter_by_is_active_false(self):
        """is_active=False returns only inactive customers."""
        inactive = _make_customer(name="Inactive Co", is_active=False)
        db = _mock_db()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 1
        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [inactive]
        items_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        result, total = await list_customers(db, is_active=False)
        assert total == 1
        assert result[0].is_active is False


# ---------------------------------------------------------------------------
# update_customer — new fields
# ---------------------------------------------------------------------------


class TestGetCustomer:
    @pytest.mark.asyncio
    async def test_get_customer_found(self):
        """Happy path: returns the customer when found."""
        customer = _make_customer()
        db = _mock_db_with_execute(scalar_result=customer)
        result = await get_customer(db, customer.id)
        assert result.id == customer.id

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self):
        """Raises CustomerNotFoundError when no row is returned."""
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(CustomerNotFoundError):
            await get_customer(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# update_customer — new fields
# ---------------------------------------------------------------------------


class TestUpdateCustomer:
    @pytest.mark.asyncio
    async def test_update_customer_city_and_country(self):
        """Updating city and country should persist through setattr loop."""
        existing = _make_customer(city="Lagos", country="Nigeria")
        db = _mock_db_with_execute(scalar_result=existing)

        data = CustomerUpdate(city="Abuja", country="Nigeria", state="FCT")
        updated = await update_customer(db, existing.id, data)

        assert updated.city == "Abuja"
        assert updated.state == "FCT"
        db.flush.assert_called_once()

    def test_update_customer_null_opening_balance_rejected(self):
        """Explicit null for opening_balance raises ValidationError at schema validation."""
        with pytest.raises(ValidationError):
            CustomerUpdate(**{"opening_balance": None})

    def test_update_customer_null_is_active_rejected(self):
        """Explicit null for is_active raises ValidationError at schema validation."""
        with pytest.raises(ValidationError):
            CustomerUpdate(**{"is_active": None})


# ---------------------------------------------------------------------------
# pay_term_type enum validation
# ---------------------------------------------------------------------------


class TestPayTermTypeValidation:
    def test_create_customer_valid_pay_term_type(self):
        """PayTermType enum values 'days' and 'months' are accepted."""
        data = CustomerCreate(name="Test", pay_term_type=PayTermType.DAYS)
        assert data.pay_term_type == PayTermType.DAYS

        data2 = CustomerCreate(name="Test", pay_term_type="months")
        assert data2.pay_term_type == PayTermType.MONTHS

    def test_create_customer_invalid_pay_term_type_rejected(self):
        """Arbitrary strings like 'weekly' are rejected by the enum validator."""
        with pytest.raises(ValidationError):
            CustomerCreate(name="Test", pay_term_type="weekly")


# ---------------------------------------------------------------------------
# deactivate_customer (soft-delete)
# ---------------------------------------------------------------------------


class TestDeactivateCustomer:
    @pytest.mark.asyncio
    async def test_deactivate_customer_sets_is_active_false(self):
        """deactivate_customer() sets is_active=False when no linked sales."""
        from src.customers.service import deactivate_customer

        customer = _make_customer(is_active=True)

        get_mock = MagicMock()
        get_mock.scalar_one_or_none.return_value = customer

        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[get_mock, count_mock])

        result = await deactivate_customer(db, customer.id)
        assert result.is_active is False
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_customer_with_sales_raises(self):
        """deactivate_customer() raises CustomerHasLinkedSalesError when sales exist."""
        from src.customers.exceptions import CustomerHasLinkedSalesError
        from src.customers.service import deactivate_customer

        customer = _make_customer(is_active=True)

        get_mock = MagicMock()
        get_mock.scalar_one_or_none.return_value = customer

        count_mock = MagicMock()
        count_mock.scalar.return_value = 3  # 3 linked sales

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[get_mock, count_mock])

        with pytest.raises(CustomerHasLinkedSalesError):
            await deactivate_customer(db, customer.id)

    @pytest.mark.asyncio
    async def test_deactivate_customer_not_found_raises(self):
        """deactivate_customer() raises CustomerNotFoundError when customer missing."""
        from src.customers.service import deactivate_customer

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(CustomerNotFoundError):
            await deactivate_customer(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# get_customer_sales
# ---------------------------------------------------------------------------


class TestGetCustomerSales:
    @pytest.mark.asyncio
    async def test_customer_sales_returns_paginated_list(self):
        """get_customer_sales() returns (items, total) for the customer."""
        from src.customers.service import get_customer_sales
        from src.sales.models import Sale, SaleChannel, SaleStatus

        sale = Sale(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=2,
            unit_price=Decimal("1000"),
            total_amount=Decimal("2000"),
            currency="NGN",
            sale_date=datetime.now(timezone.utc).date(),
            channel=SaleChannel.RETAIL,
            status=SaleStatus.COMPLETED,
            recorded_by=uuid.uuid4(),
            customer_id=uuid.uuid4(),
        )
        sale.created_at = datetime.now(timezone.utc)
        sale.updated_at = datetime.now(timezone.utc)

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale]
        items_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        result, total = await get_customer_sales(db, uuid.uuid4())
        assert total == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_customer_sales_empty_returns_zero(self):
        """get_customer_sales() returns empty list and 0 when no sales."""
        from src.customers.service import get_customer_sales

        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        items_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        result, total = await get_customer_sales(db, uuid.uuid4())
        assert total == 0
        assert result == []


# ---------------------------------------------------------------------------
# get_customer_ledger
# ---------------------------------------------------------------------------


class TestGetCustomerLedger:
    @pytest.mark.asyncio
    async def test_customer_ledger_includes_opening_balance(self):
        """Ledger starts with an opening-balance entry when opening_balance > 0."""
        from src.customers.service import get_customer_ledger

        customer = _make_customer(opening_balance=Decimal("5000"))

        get_mock = MagicMock()
        get_mock.scalar_one_or_none.return_value = customer

        sales_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        sales_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[get_mock, sales_mock])

        entries = await get_customer_ledger(db, customer.id)
        assert len(entries) == 1
        assert entries[0].description == "Opening balance"
        assert entries[0].balance == Decimal("5000")

    @pytest.mark.asyncio
    async def test_customer_ledger_sale_creates_debit_entry(self):
        """Each sale adds a debit entry and advances the running balance."""
        from src.customers.service import get_customer_ledger
        from src.sales.models import Sale, SaleChannel, SaleStatus

        customer = _make_customer(opening_balance=Decimal("0"))

        sale = Sale(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=1,
            unit_price=Decimal("3000"),
            total_amount=Decimal("3000"),
            currency="NGN",
            sale_date=datetime.now(timezone.utc).date(),
            channel=SaleChannel.RETAIL,
            status=SaleStatus.COMPLETED,
            recorded_by=uuid.uuid4(),
        )
        sale.created_at = datetime.now(timezone.utc)
        sale.updated_at = datetime.now(timezone.utc)

        get_mock = MagicMock()
        get_mock.scalar_one_or_none.return_value = customer

        sales_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale]
        sales_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[get_mock, sales_mock])

        entries = await get_customer_ledger(db, customer.id)
        # No opening balance entry (0), one sale entry
        assert len(entries) == 1
        assert entries[0].debit == Decimal("3000")
        assert entries[0].balance == Decimal("3000")


# ---------------------------------------------------------------------------
# get_customer_activities
# ---------------------------------------------------------------------------


class TestGetCustomerActivities:
    @pytest.mark.asyncio
    async def test_customer_activities_returns_sale_events(self):
        """Activities list includes a 'sale' event per linked sale."""
        from src.customers.service import get_customer_activities
        from src.sales.models import Sale, SaleChannel, SaleStatus

        sale = Sale(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=1,
            unit_price=Decimal("1500"),
            total_amount=Decimal("1500"),
            currency="NGN",
            sale_date=datetime.now(timezone.utc).date(),
            channel=SaleChannel.RETAIL,
            status=SaleStatus.COMPLETED,
            recorded_by=uuid.uuid4(),
        )
        sale.created_at = datetime.now(timezone.utc)
        sale.updated_at = datetime.now(timezone.utc)

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sale]
        result_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        activities = await get_customer_activities(db, uuid.uuid4())
        assert len(activities) == 1
        assert activities[0].event_type == "sale"
        assert activities[0].amount == Decimal("1500")

    @pytest.mark.asyncio
    async def test_customer_activities_empty_when_no_sales(self):
        """Activities returns empty list when customer has no sales."""
        from src.customers.service import get_customer_activities

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        activities = await get_customer_activities(db, uuid.uuid4())
        assert activities == []


# ---------------------------------------------------------------------------
# export_customers_csv
# ---------------------------------------------------------------------------


class TestExportCustomersCsv:
    @pytest.mark.asyncio
    async def test_export_csv_contains_headers_and_row(self):
        """export_customers_csv() returns CSV text with header + one data row."""
        from src.customers.service import export_customers_csv

        customer = _make_customer(name="Ade Store", email="ade@store.ng", city="Lagos")

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [customer]
        items_mock.scalars.return_value = scalars_mock

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        csv_text = await export_customers_csv(db)
        assert "name" in csv_text
        assert "Ade Store" in csv_text
        assert "Lagos" in csv_text
