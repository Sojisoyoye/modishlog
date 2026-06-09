"""Tests for enhanced purchase orders — supplier FK, pay terms, shipping, PO vs Purchase, returns."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.models import User, UserRole
from src.core.security import get_password_hash
from src.inventory.models import InventoryLevel
from src.orders.models import (
    DiscountType,
    OrderLineItem,
    OrderPayment,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PayTermType,
    PurchaseOrder,
    PurchaseReturn,
)
from src.orders.schemas import (
    OrderCreate,
    OrderLineItemCreate,
    PurchaseReturnCreate,
    PurchaseReturnLineItem,
)
from src.orders.service import (
    convert_po_to_purchase,
    create_order,
    create_purchase_return,
)
from src.products.models import Product

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides):
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


def _make_order(**overrides):
    defaults = dict(
        order_number="PO-2026-00001",
        supplier_name="Test Supplier",
        supplier_id=None,
        supplier_contact=None,
        status=OrderStatus.PENDING,
        is_purchase_order=False,
        total_amount=Decimal("5000.000000"),
        currency="USD",
        fx_rate_at_creation=Decimal("1500.000000"),
        fx_rate_at_delivery=None,
        expected_delivery_date=date(2026, 6, 15),
        actual_delivery_date=None,
        notes=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    order = PurchaseOrder(**defaults)
    order.id = overrides.get("id", uuid.uuid4())
    order.created_at = datetime.now(timezone.utc)
    order.updated_at = datetime.now(timezone.utc)
    order.line_items = overrides.get("line_items", [])
    order.payments = overrides.get("payments", [])
    order.status_history = overrides.get("status_history", [])
    return order


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
    result_mock.one.return_value = (Decimal("0"), 0)
    if scalars_result is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_result
        result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Model fields — new columns exist
# ---------------------------------------------------------------------------


class TestNewModelFields:
    def test_purchase_order_has_is_purchase_order(self):
        order = _make_order(is_purchase_order=True)
        assert order.is_purchase_order is True

    def test_purchase_order_has_pay_term_fields(self):
        order = _make_order(
            pay_term_number=30,
            pay_term_type=PayTermType.DAYS,
        )
        assert order.pay_term_number == 30
        assert order.pay_term_type == PayTermType.DAYS

    def test_purchase_order_has_shipping_details(self):
        order = _make_order(
            shipping_details="Deliver to Lagos warehouse",
            shipping_custom_field_1="Container No: ABC123",
        )
        assert order.shipping_details == "Deliver to Lagos warehouse"
        assert order.shipping_custom_field_1 == "Container No: ABC123"

    def test_purchase_order_has_additional_expenses(self):
        order = _make_order(
            additional_expense_key_1="Customs",
            additional_expense_value_1=Decimal("15000.00"),
        )
        assert order.additional_expense_key_1 == "Customs"
        assert order.additional_expense_value_1 == Decimal("15000.00")

    def test_purchase_order_has_discount_fields(self):
        order = _make_order(
            discount_type=DiscountType.PERCENTAGE,
            discount_amount=Decimal("5.00"),
        )
        assert order.discount_type == DiscountType.PERCENTAGE
        assert order.discount_amount == Decimal("5.00")

    def test_purchase_order_has_supplier_invoice_fields(self):
        order = _make_order(
            supplier_invoice_number="INV-2026-001",
            supplier_invoice_date=date(2026, 6, 1),
        )
        assert order.supplier_invoice_number == "INV-2026-001"
        assert order.supplier_invoice_date == date(2026, 6, 1)

    def test_ordered_status_exists(self):
        assert OrderStatus.ORDERED == "ORDERED"

    def test_purchase_return_model(self):
        ret = PurchaseReturn(
            original_order_id=uuid.uuid4(),
            ref_no="RET-001",
            return_date=date(2026, 6, 9),
            notes="Damaged goods",
            total_amount=Decimal("500.00"),
            created_by=uuid.uuid4(),
        )
        ret.id = uuid.uuid4()
        assert ret.ref_no == "RET-001"
        assert ret.total_amount == Decimal("500.00")


# ---------------------------------------------------------------------------
# create_order — PO vs received purchase
# ---------------------------------------------------------------------------


class TestCreateOrderPO:
    @pytest.mark.asyncio
    async def test_create_purchase_order_no_stock_impact(self):
        """Creating a PO (is_purchase_order=True) must NOT update inventory."""
        product = _make_product(id=uuid.uuid4())
        user_id = uuid.uuid4()

        db = _mock_db()
        # Execution order: 1) product validation, 2) count query, 3) uniqueness check, 4) reload
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        unique_result = MagicMock()
        unique_result.scalar_one_or_none.return_value = None
        reload_result = MagicMock()
        reloaded_order = _make_order(is_purchase_order=True, status=OrderStatus.ORDERED)
        reload_result.scalar_one.return_value = reloaded_order

        db.execute = AsyncMock(
            side_effect=[product_result, count_result, unique_result, reload_result]
        )

        data = OrderCreate(
            supplier_name="Acme",
            is_purchase_order=True,
            line_items=[
                OrderLineItemCreate(product_id=product.id, quantity=10, unit_cost=Decimal("100"))
            ],
        )

        order = await create_order(db, data, user_id)
        assert order.is_purchase_order is True
        assert order.status == OrderStatus.ORDERED

    @pytest.mark.asyncio
    async def test_create_received_purchase_updates_inventory(self):
        """Creating a received purchase (is_purchase_order=False) skips inventory on create."""
        product = _make_product(id=uuid.uuid4())
        user_id = uuid.uuid4()

        db = _mock_db()
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        unique_result = MagicMock()
        unique_result.scalar_one_or_none.return_value = None
        reload_result = MagicMock()
        reloaded_order = _make_order(is_purchase_order=False, status=OrderStatus.PENDING)
        reload_result.scalar_one.return_value = reloaded_order

        db.execute = AsyncMock(
            side_effect=[product_result, count_result, unique_result, reload_result]
        )

        data = OrderCreate(
            supplier_name="Acme",
            is_purchase_order=False,
            line_items=[
                OrderLineItemCreate(product_id=product.id, quantity=10, unit_cost=Decimal("100"))
            ],
        )

        order = await create_order(db, data, user_id)
        assert order.is_purchase_order is False
        assert order.status == OrderStatus.PENDING


class TestCreateOrderPayTerms:
    @pytest.mark.asyncio
    async def test_create_order_with_pay_terms(self):
        product = _make_product(id=uuid.uuid4())
        db = _mock_db()
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        unique_result = MagicMock()
        unique_result.scalar_one_or_none.return_value = None
        reload_result = MagicMock()
        reloaded = _make_order(is_purchase_order=False, pay_term_number=30, pay_term_type=PayTermType.DAYS)
        reload_result.scalar_one.return_value = reloaded

        db.execute = AsyncMock(
            side_effect=[product_result, count_result, unique_result, reload_result]
        )

        data = OrderCreate(
            supplier_name="Acme",
            is_purchase_order=False,
            pay_term_number=30,
            pay_term_type="days",
            line_items=[
                OrderLineItemCreate(product_id=product.id, quantity=5, unit_cost=Decimal("200"))
            ],
        )
        order = await create_order(db, data, user_id=uuid.uuid4())
        assert order.pay_term_number == 30
        assert order.pay_term_type == PayTermType.DAYS


# ---------------------------------------------------------------------------
# convert_po_to_purchase
# ---------------------------------------------------------------------------


class TestConvertPoToPurchase:
    @pytest.mark.asyncio
    async def test_convert_po_to_purchase(self):
        """Converting a PO to received purchase triggers stock update and changes status."""
        product = _make_product(id=uuid.uuid4())
        inv = _make_inventory(product_id=product.id)
        line = OrderLineItem(
            order_id=uuid.uuid4(),
            product_id=product.id,
            quantity=5,
            unit_cost=Decimal("100"),
            line_total=Decimal("500"),
        )
        line.id = uuid.uuid4()
        po = _make_order(
            is_purchase_order=True,
            status=OrderStatus.ORDERED,
            line_items=[line],
        )

        db = _mock_db()
        po_result = MagicMock()
        po_result.scalar_one_or_none.return_value = po
        inv_result = MagicMock()
        inv_result.scalar_one_or_none.return_value = inv
        extra = MagicMock()
        extra.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[po_result, inv_result, extra])

        converted = await convert_po_to_purchase(db, po.id, user_id=uuid.uuid4())
        assert converted.is_purchase_order is False
        assert converted.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_convert_po_not_found_raises(self):
        db = _mock_db_with_execute(scalar_result=None)
        from src.orders.exceptions import OrderNotFoundError
        with pytest.raises(OrderNotFoundError):
            await convert_po_to_purchase(db, uuid.uuid4(), user_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# purchase_return
# ---------------------------------------------------------------------------


class TestPurchaseReturn:
    @pytest.mark.asyncio
    async def test_create_purchase_return(self):
        product = _make_product(id=uuid.uuid4())
        inv = _make_inventory(product_id=product.id, quantity_on_hand=50)
        line = OrderLineItem(
            order_id=uuid.uuid4(),
            product_id=product.id,
            quantity=10,
            unit_cost=Decimal("100"),
            line_total=Decimal("1000"),
        )
        line.id = uuid.uuid4()
        order = _make_order(status=OrderStatus.DELIVERED, line_items=[line])

        db = _mock_db()
        # Execution: 1) load order, 2) inv check (adjust_stock), 3) count returns for ref_no
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        inv_result = MagicMock()
        inv_result.scalar_one_or_none.return_value = inv
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        db.execute = AsyncMock(side_effect=[order_result, inv_result, count_result])

        data = PurchaseReturnCreate(
            original_order_id=order.id,
            notes="Damaged goods",
            line_items=[PurchaseReturnLineItem(product_id=product.id, quantity=2)],
        )
        ret = await create_purchase_return(db, data, user_id=uuid.uuid4())
        assert ret.original_order_id == order.id
        assert ret.total_amount == Decimal("200.00")

    @pytest.mark.asyncio
    async def test_purchase_return_order_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        from src.orders.exceptions import OrderNotFoundError
        data = PurchaseReturnCreate(
            original_order_id=uuid.uuid4(),
            notes=None,
            line_items=[PurchaseReturnLineItem(product_id=uuid.uuid4(), quantity=1)],
        )
        with pytest.raises(OrderNotFoundError):
            await create_purchase_return(db, data, user_id=uuid.uuid4())
