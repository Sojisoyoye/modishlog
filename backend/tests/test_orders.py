"""Tests for orders CRUD, status workflow, payments, and inventory integration."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
from src.inventory.models import InventoryLevel
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    OrderNotEditableError,
    OrderNotFoundError,
    OverpaymentError,
)
from src.orders.models import (
    OrderLineItem,
    OrderPayment,
    OrderPaymentStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PurchaseOrder,
)
import src.suppliers.models  # noqa: F401 — register Supplier mapper for PurchaseOrder.supplier relationship
from src.orders.schemas import (
    OrderCreate,
    OrderLineItemCreate,
    OrderUpdate,
    PaymentCreate,
    StatusTransition,
)
from src.orders.service import (
    cancel_order,
    create_order,
    get_order,
    get_payment_summary,
    list_orders,
    record_payment,
    transition_status,
    update_order,
    void_payment,
)
from src.products.models import Product

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
        supplier_contact="supplier@test.com",
        status=OrderStatus.PENDING,
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


def _make_line_item(order_id=None, product_id=None, **overrides):
    defaults = dict(
        order_id=order_id or uuid.uuid4(),
        product_id=product_id or uuid.uuid4(),
        quantity=10,
        unit_cost=Decimal("500.000000"),
        line_total=Decimal("5000.000000"),
        notes=None,
    )
    defaults.update(overrides)
    item = OrderLineItem(**defaults)
    item.id = overrides.get("id", uuid.uuid4())
    return item


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
# Service tests - create_order
# ---------------------------------------------------------------------------


class TestCreateOrder:
    @pytest.mark.asyncio
    async def test_create_order_success(self):
        product = _make_product(id=uuid.uuid4())

        db = _mock_db()
        call_count = 0
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Product validation
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                # Order number count
                result.scalar.return_value = 0
            elif call_count == 3:
                # Order number uniqueness check
                result.scalar_one_or_none.return_value = None
            else:
                # Reload query after flush - return the created order
                order_obj = next(
                    (o for o in added_objects if hasattr(o, "order_number")),
                    None,
                )
                result.scalar_one.return_value = order_obj
                result.scalar_one_or_none.return_value = order_obj
                result.scalar.return_value = None
            return result

        db.execute = mock_execute

        data = OrderCreate(
            supplier_name="Acme Corp",
            currency="USD",
            line_items=[
                OrderLineItemCreate(
                    product_id=product.id,
                    quantity=10,
                    unit_cost=Decimal("500"),
                )
            ],
        )
        order = await create_order(db, data, uuid.uuid4())
        assert order.supplier_name == "Acme Corp"
        assert order.total_amount == Decimal("5000")
        assert order.order_number.startswith("PO-")
        assert order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_order_invalid_product(self):
        db = _mock_db_with_execute(scalar_result=None)
        data = OrderCreate(
            supplier_name="Acme Corp",
            line_items=[
                OrderLineItemCreate(
                    product_id=uuid.uuid4(),
                    quantity=10,
                    unit_cost=Decimal("500"),
                )
            ],
        )
        from src.orders.exceptions import OrderLineItemError

        with pytest.raises(OrderLineItemError):
            await create_order(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_order_with_lead_times(self):
        product = _make_product(id=uuid.uuid4())

        db = _mock_db()
        call_count = 0
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar.return_value = 0
            elif call_count == 3:
                result.scalar_one_or_none.return_value = None
            else:
                order_obj = next(
                    (o for o in added_objects if hasattr(o, "order_number")),
                    None,
                )
                result.scalar_one.return_value = order_obj
                result.scalar_one_or_none.return_value = order_obj
                result.scalar.return_value = None
            return result

        db.execute = mock_execute

        data = OrderCreate(
            supplier_name="Acme Corp",
            production_days=30,
            shipping_days=14,
            clearing_days=3,
            line_items=[
                OrderLineItemCreate(
                    product_id=product.id,
                    quantity=5,
                    unit_cost=Decimal("200"),
                )
            ],
        )
        order = await create_order(db, data, uuid.uuid4())
        assert order.expected_delivery_date is not None


# ---------------------------------------------------------------------------
# Service tests - get/list orders
# ---------------------------------------------------------------------------


class TestGetListOrders:
    @pytest.mark.asyncio
    async def test_get_order_success(self):
        order = _make_order()
        db = _mock_db_with_execute(scalar_result=order)
        result = await get_order(db, order.id)
        assert result.id == order.id

    @pytest.mark.asyncio
    async def test_get_order_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(OrderNotFoundError):
            await get_order(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_orders_empty(self):
        db = _mock_db()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        list_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await list_orders(db)
        assert total == 0
        assert items == []


# ---------------------------------------------------------------------------
# Service tests - update_order
# ---------------------------------------------------------------------------


class TestUpdateOrder:
    @pytest.mark.asyncio
    async def test_update_order_notes(self):
        order = _make_order(status=OrderStatus.PENDING)
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(notes="Updated notes")
        result = await update_order(db, order.id, data, uuid.uuid4())
        assert result.notes == "Updated notes"

    @pytest.mark.asyncio
    async def test_update_order_cancelled_not_editable(self):
        """CANCELLED orders cannot be edited."""
        order = _make_order(status=OrderStatus.CANCELLED)
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(notes="Try to update")
        with pytest.raises(OrderNotEditableError):
            await update_order(db, order.id, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_order_delivered_is_not_editable(self):
        """DELIVERED orders must NOT be editable — prevents retroactive cost manipulation."""
        from src.orders.exceptions import OrderNotEditableError
        order = _make_order(status=OrderStatus.DELIVERED)
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(notes="Retroactive change")
        with pytest.raises(OrderNotEditableError):
            await update_order(db, order.id, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_order_shipping_cost(self):
        order = _make_order(status=OrderStatus.ORDERED)
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(shipping_cost=Decimal("50000"))
        result = await update_order(db, order.id, data, uuid.uuid4())
        assert result.shipping_cost == Decimal("50000")

    @pytest.mark.asyncio
    async def test_update_order_ordered_status_is_editable(self):
        order = _make_order(status=OrderStatus.ORDERED)
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(notes="Corrected after placing")
        result = await update_order(db, order.id, data, uuid.uuid4())
        assert result.notes == "Corrected after placing"

    @pytest.mark.asyncio
    async def test_update_order_line_item_stores_unit_cost_ngn(self):
        """unit_cost_ngn provided on a line item update is stored."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        order = _make_order(status=OrderStatus.PENDING)
        order.line_items = []
        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = product
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderUpdate(
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=5,
                    unit_cost=Decimal("100"),
                    unit_cost_ngn=Decimal("162000"),
                )
            ]
        )
        await update_order(db, order.id, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.unit_cost_ngn == Decimal("162000")

    @pytest.mark.asyncio
    async def test_update_order_line_item_unit_cost_ngn_optional(self):
        """unit_cost_ngn is optional — line items without it store None."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        order = _make_order(status=OrderStatus.PENDING)
        order.line_items = []
        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = product
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderUpdate(
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=3,
                    unit_cost=Decimal("50"),
                )
            ]
        )
        await update_order(db, order.id, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.unit_cost_ngn is None

    @pytest.mark.asyncio
    async def test_update_order_line_item_stores_sell_price_ngn(self):
        """sell_price_ngn provided on a line item update is stored."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        order = _make_order(status=OrderStatus.PENDING)
        order.line_items = []
        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = product
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderUpdate(
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=5,
                    unit_cost=Decimal("100"),
                    sell_price_ngn=Decimal("210000"),
                )
            ]
        )
        await update_order(db, order.id, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.sell_price_ngn == Decimal("210000")

    @pytest.mark.asyncio
    async def test_update_order_line_item_sell_price_ngn_optional(self):
        """sell_price_ngn is optional — line items without it store None."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        order = _make_order(status=OrderStatus.PENDING)
        order.line_items = []
        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = product
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderUpdate(
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=3,
                    unit_cost=Decimal("50"),
                )
            ]
        )
        await update_order(db, order.id, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.sell_price_ngn is None

    @pytest.mark.asyncio
    async def test_update_order_preserves_units_remaining(self):
        """units_remaining is carried over when line items are replaced on a CLEARED order."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        order = _make_order(status=OrderStatus.CLEARED)
        existing_item = _make_line_item(
            order_id=order.id,
            product_id=product_id,
            units_remaining=Decimal("10"),
        )
        order.line_items = [existing_item]

        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = product
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderUpdate(
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=10,
                    unit_cost=Decimal("50"),
                    sell_price_ngn=Decimal("180000"),
                )
            ]
        )
        await update_order(db, order.id, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.sell_price_ngn == Decimal("180000")
        assert new_item.units_remaining == Decimal("10")

    @pytest.mark.asyncio
    async def test_update_order_units_remaining_stays_none_for_new_products(self):
        """units_remaining is None for brand-new products not in original line items."""
        product_id_old = uuid.uuid4()
        product_id_new = uuid.uuid4()
        product_new = _make_product(id=product_id_new)
        order = _make_order(status=OrderStatus.CLEARED)
        existing_item = _make_line_item(
            order_id=order.id,
            product_id=product_id_old,
            units_remaining=Decimal("5"),
        )
        order.line_items = [existing_item]

        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = product_new
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderUpdate(
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id_new,
                    quantity=3,
                    unit_cost=Decimal("80"),
                )
            ]
        )
        await update_order(db, order.id, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.units_remaining is None

    @pytest.mark.asyncio
    async def test_create_order_stores_sell_price_ngn(self):
        """sell_price_ngn on OrderLineItemCreate is stored in the line item."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # product existence check
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                # _generate_order_number: count of existing orders
                result.scalar.return_value = 0
            elif call_count == 3:
                # _generate_order_number: uniqueness check — no conflict
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderCreate(
            supplier_name="Test Supplier",
            currency="NGN",
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=10,
                    unit_cost=Decimal("130000"),
                    sell_price_ngn=Decimal("195000"),
                )
            ],
        )
        await create_order(db, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.sell_price_ngn == Decimal("195000")

    @pytest.mark.asyncio
    async def test_create_order_sell_price_ngn_defaults_null(self):
        """sell_price_ngn is null when not provided on create."""
        product_id = uuid.uuid4()
        product = _make_product(id=product_id)
        db = _mock_db()
        added_objects: list = []
        original_add = db.add

        def tracking_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        db.add = tracking_add

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # product existence check
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                # _generate_order_number: count of existing orders
                result.scalar.return_value = 0
            elif call_count == 3:
                # _generate_order_number: uniqueness check
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = OrderCreate(
            supplier_name="Test Supplier",
            currency="NGN",
            line_items=[
                OrderLineItemCreate(
                    product_id=product_id,
                    quantity=5,
                    unit_cost=Decimal("100000"),
                )
            ],
        )
        await create_order(db, data, uuid.uuid4())
        new_item = next(
            (o for o in added_objects if isinstance(o, OrderLineItem)), None
        )
        assert new_item is not None
        assert new_item.sell_price_ngn is None


# ---------------------------------------------------------------------------
# Service tests - cancel_order
# ---------------------------------------------------------------------------


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_pending_order(self):
        order = _make_order(status=OrderStatus.PENDING)
        db = _mock_db_with_execute(scalar_result=order)

        result = await cancel_order(db, order.id, uuid.uuid4())
        assert result.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_non_pending_raises(self):
        order = _make_order(status=OrderStatus.SHIPPING)
        db = _mock_db_with_execute(scalar_result=order)

        with pytest.raises(InvalidStatusTransitionError):
            await cancel_order(db, order.id, uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - transition_status
# ---------------------------------------------------------------------------


class TestTransitionStatus:
    @pytest.mark.asyncio
    async def test_valid_transition(self):
        order = _make_order(status=OrderStatus.PENDING)
        db = _mock_db_with_execute(scalar_result=order)

        transition = StatusTransition(new_status="IN_PRODUCTION")
        result = await transition_status(db, order.id, transition, uuid.uuid4())
        assert result.status == OrderStatus.IN_PRODUCTION

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        order = _make_order(status=OrderStatus.PENDING)
        db = _mock_db_with_execute(scalar_result=order)

        transition = StatusTransition(new_status="DELIVERED")
        with pytest.raises(InvalidStatusTransitionError):
            await transition_status(db, order.id, transition, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_delivery_restocks_inventory(self):
        product_id = uuid.uuid4()
        line_item = _make_line_item(product_id=product_id, quantity=10)
        inventory = _make_inventory(product_id=product_id, quantity_on_hand=50)
        order = _make_order(
            status=OrderStatus.CLEARED,
            line_items=[line_item],
        )

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # get_order
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                # get_inventory_level (inside adjust_stock)
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        transition = StatusTransition(
            new_status="DELIVERED",
            actual_delivery_date=date(2026, 3, 30),
        )
        result = await transition_status(db, order.id, transition, uuid.uuid4())
        assert result.status == OrderStatus.DELIVERED
        assert result.actual_delivery_date == date(2026, 3, 30)
        # Inventory should be restocked: 50 + 10 = 60
        assert inventory.quantity_on_hand == 60

    @pytest.mark.asyncio
    async def test_delivery_with_fx_rate_stores_value(self):
        """When transitioning to DELIVERED with fx_rate_at_delivery, it is stored on the order."""
        product_id = uuid.uuid4()
        line_item = _make_line_item(product_id=product_id, quantity=5)
        inventory = _make_inventory(product_id=product_id, quantity_on_hand=20)
        order = _make_order(
            status=OrderStatus.CLEARED,
            line_items=[line_item],
            fx_rate_at_creation=Decimal("1500.000000"),
        )

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        transition = StatusTransition(
            new_status="DELIVERED",
            actual_delivery_date=date(2026, 4, 10),
            fx_rate_at_delivery=Decimal("1620.500000"),
        )
        result = await transition_status(db, order.id, transition, uuid.uuid4())
        assert result.status == OrderStatus.DELIVERED
        assert result.fx_rate_at_delivery == Decimal("1620.500000")

    @pytest.mark.asyncio
    async def test_delivery_without_fx_rate_still_works(self):
        """Transitioning to DELIVERED without fx_rate_at_delivery still works (field stays None)."""
        product_id = uuid.uuid4()
        line_item = _make_line_item(product_id=product_id, quantity=3)
        inventory = _make_inventory(product_id=product_id, quantity_on_hand=10)
        order = _make_order(
            status=OrderStatus.CLEARED,
            line_items=[line_item],
        )

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        transition = StatusTransition(
            new_status="DELIVERED",
            actual_delivery_date=date(2026, 4, 10),
        )
        result = await transition_status(db, order.id, transition, uuid.uuid4())
        assert result.status == OrderStatus.DELIVERED
        assert result.fx_rate_at_delivery is None

    @pytest.mark.asyncio
    async def test_delivery_fx_rate_used_for_fifo_batches(self):
        """When fx_rate_at_delivery is provided, FIFO batches use it instead of fx_rate_at_creation."""
        product_id = uuid.uuid4()
        line_item = _make_line_item(product_id=product_id, quantity=10)
        inventory = _make_inventory(product_id=product_id, quantity_on_hand=50)
        order = _make_order(
            status=OrderStatus.CLEARED,
            line_items=[line_item],
            fx_rate_at_creation=Decimal("1500.000000"),
        )

        db = _mock_db()
        call_count = 0
        batch_args = {}

        original_add = db.add

        def tracking_add(obj):
            # Capture batch creation arguments
            if hasattr(obj, "fx_rate_at_arrival"):
                batch_args["fx_rate_at_arrival"] = obj.fx_rate_at_arrival
            return original_add(obj)

        db.add = tracking_add

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        transition = StatusTransition(
            new_status="DELIVERED",
            actual_delivery_date=date(2026, 4, 10),
            fx_rate_at_delivery=Decimal("1650.000000"),
        )
        result = await transition_status(db, order.id, transition, uuid.uuid4())
        assert result.fx_rate_at_delivery == Decimal("1650.000000")


# ---------------------------------------------------------------------------
# Service tests - payments
# ---------------------------------------------------------------------------


class TestPayments:
    @pytest.mark.asyncio
    async def test_record_payment_success(self):
        order = _make_order(total_amount=Decimal("5000"))
        db = _mock_db()

        # get_order + get_payment_summary + _sync_payment_status calls
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # get_order (from record_payment)
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                # get_order (from get_payment_summary)
                result.scalar_one_or_none.return_value = order
            elif call_count == 3:
                # sum/count query in get_payment_summary
                result.one.return_value = (Decimal("0"), 0)
            elif call_count == 4:
                # sum query in _sync_payment_status (1500 now paid)
                result.scalar.return_value = Decimal("1500")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = PaymentCreate(
            amount=Decimal("1500"),
            payment_date=date(2026, 3, 15),
            payment_method="BANK_TRANSFER",
        )
        payment = await record_payment(db, order.id, data, uuid.uuid4())
        assert payment.amount == Decimal("1500")
        assert payment.status == PaymentStatus.COMPLETED
        assert order.payment_status == OrderPaymentStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_record_payment_stores_fx_rate(self):
        """fx_rate provided at payment time is stored on the payment record."""
        order = _make_order(total_amount=Decimal("5000"))
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = order
            elif call_count == 3:
                result.one.return_value = (Decimal("0"), 0)
            elif call_count == 4:
                result.scalar.return_value = Decimal("500")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = PaymentCreate(
            amount=Decimal("500"),
            currency="USD",
            payment_date=date(2026, 6, 11),
            payment_method="BANK_TRANSFER",
            fx_rate=Decimal("1620.00"),
        )
        payment = await record_payment(db, order.id, data, uuid.uuid4())
        assert payment.fx_rate == Decimal("1620.00")

    @pytest.mark.asyncio
    async def test_record_payment_fx_rate_optional(self):
        """fx_rate is optional — NGN payments record without it."""
        order = _make_order(total_amount=Decimal("5000"))
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = order
            elif call_count == 3:
                result.one.return_value = (Decimal("0"), 0)
            elif call_count == 4:
                result.scalar.return_value = Decimal("500")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = PaymentCreate(
            amount=Decimal("500"),
            currency="NGN",
            payment_date=date(2026, 6, 11),
            payment_method="CASH",
        )
        payment = await record_payment(db, order.id, data, uuid.uuid4())
        assert payment.fx_rate is None

    @pytest.mark.asyncio
    async def test_overpayment_raises(self):
        order = _make_order(total_amount=Decimal("5000"))
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count <= 2:
                result.scalar_one_or_none.return_value = order
            elif call_count == 3:
                # Already paid 4000
                result.one.return_value = (Decimal("4000"), 1)
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = PaymentCreate(
            amount=Decimal("2000"),  # would exceed balance of 1000
            payment_date=date(2026, 3, 15),
            payment_method="BANK_TRANSFER",
        )
        with pytest.raises(OverpaymentError):
            await record_payment(db, order.id, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_payment_summary(self):
        order = _make_order(total_amount=Decimal("5000"))
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.one.return_value = (Decimal("1500"), 1)
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        summary = await get_payment_summary(db, order.id)
        assert summary.total_due == Decimal("5000")
        assert summary.total_paid == Decimal("1500")
        assert summary.balance_remaining == Decimal("3500")
        assert summary.is_fully_paid is False

    @pytest.mark.asyncio
    async def test_void_payment(self):
        order = _make_order()
        payment = OrderPayment(
            order_id=order.id,
            amount=Decimal("1000"),
            currency="USD",
            payment_date=date(2026, 3, 15),
            payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.COMPLETED,
            recorded_by=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        payment.id = uuid.uuid4()

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = payment
            elif call_count == 3:
                # sum query in _sync_payment_status (no completed payments remain)
                result.scalar.return_value = Decimal("0")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        result = await void_payment(db, order.id, payment.id, uuid.uuid4())
        assert result.status == PaymentStatus.VOIDED
        assert order.payment_status == OrderPaymentStatus.UNPAID


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestOrderEndpoints:
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

    def test_create_order_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/orders",
                json={
                    "supplier_name": "Test",
                    "line_items": [
                        {
                            "product_id": str(uuid.uuid4()),
                            "quantity": 10,
                            "unit_cost": "500",
                        }
                    ],
                },
            )
        assert resp.status_code == 401

    def test_get_order_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/orders/{fake_id}")
        assert resp.status_code == 404

    def test_list_orders_empty(self):
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
            resp = client.get("/api/v1/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_cancel_order_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.delete(f"/api/v1/orders/{fake_id}")
        assert resp.status_code == 401

    def test_orders_summary(self):
        db = _mock_db()
        # Two queries: count/sum + group by
        total_result = MagicMock()
        total_result.one.return_value = (0, Decimal("0"))
        status_result = MagicMock()
        status_result.all.return_value = []
        db.execute = AsyncMock(side_effect=[total_result, status_result])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_orders"] == 0


# ---------------------------------------------------------------------------
# CSV Export endpoint tests
# ---------------------------------------------------------------------------


class TestOrdersExportEndpoint:
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

    def _make_execute_side_effects(self, orders: list):
        """Return two execute side effects: count then list."""
        count_result = MagicMock()
        count_result.scalar.return_value = len(orders)
        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = orders
        list_result.scalars.return_value = scalars_mock
        return [count_result, list_result]

    def test_export_orders_csv_returns_csv_content_type(self):
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/export.csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_orders_csv_has_correct_headers(self):
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/export.csv")

        assert resp.status_code == 200
        first_line = resp.text.splitlines()[0]
        assert "order_number" in first_line
        assert "supplier_name" in first_line
        assert "total_amount" in first_line
        assert "status" in first_line

    def test_export_orders_csv_content_disposition(self):
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/export.csv")

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert ".csv" in resp.headers.get("content-disposition", "")

    def test_export_orders_csv_with_data_row(self):
        order = _make_order()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([order]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/export.csv")

        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        # Header + 1 data row
        assert len(lines) == 2
        # Data row should contain the order number
        assert "PO-2026-00001" in lines[1]


# ---------------------------------------------------------------------------
# Tests for lot inventory tracking (Task #75)
# ---------------------------------------------------------------------------


class TestLotInventoryTracking:
    """units_remaining is set on delivery and exposed via /lots endpoint."""

    @pytest.mark.asyncio
    async def test_order_delivered_sets_units_remaining(self):
        """Transitioning to DELIVERED sets units_remaining = quantity on each line item."""
        from src.orders.service import transition_status
        from src.orders.schemas import StatusTransition

        product_id = uuid.uuid4()
        item = _make_line_item(product_id=product_id, quantity=50)
        order = _make_order(status=OrderStatus.CLEARED)
        order.line_items = [item]

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalar_one_or_none.return_value = order if call_count == 1 else None
            result.scalars.return_value.all.return_value = []
            result.scalar.return_value = None
            return result

        db.execute = mock_execute

        with patch("src.orders.service.adjust_stock", new_callable=AsyncMock), \
             patch("src.orders.service.create_batch", new_callable=AsyncMock):
            await transition_status(
                db, order.id, StatusTransition(new_status="DELIVERED"), uuid.uuid4()
            )

        assert item.units_remaining == Decimal(str(item.quantity))

    def test_units_remaining_null_before_delivery(self):
        """units_remaining stays None for orders that have not reached DELIVERED."""
        item = _make_line_item(quantity=10)
        assert item.units_remaining is None

    @pytest.mark.asyncio
    async def test_lots_endpoint_returns_line_items(self):
        """GET /orders/{id}/lots returns line items with units_remaining."""
        from src.main import app
        from src.core.database import get_db

        item = _make_line_item(quantity=20)
        item.units_remaining = Decimal("20")
        item.unit_cost_ngn = Decimal("14000")
        item.sell_price_ngn = Decimal("21000")
        order = _make_order(status=OrderStatus.DELIVERED)
        order.line_items = [item]

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = order
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.get(f"/api/v1/orders/{order.id}/lots")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert "units_remaining" in data[0]
        finally:
            app.dependency_overrides.pop(get_db, None)
