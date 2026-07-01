"""Tests for the enriched Customer model (task #159)."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.customers.exceptions import CustomerNotFoundError
from src.customers.models import Customer
from src.customers.schemas import CustomerCreate, CustomerUpdate
from src.customers.service import (
    create_customer,
    get_customer,
    list_customers,
    update_customer,
)


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
        assert customer.pay_term_type == "days"
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
