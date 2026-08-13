"""Tests for orders CRUD, status workflow, payments, and inventory integration."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
from src.inventory.models import FifoConsumption, InventoryBatch, InventoryLevel
from src.sales.models import Sale, SaleChannel
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    MissingFxRateError,
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
    OrderCostCorrectionRequest,
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
from tests.conftest import NestedTransaction

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
        business_id=uuid.uuid4(),
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
    async def test_order_date_defaults_to_today_when_not_provided(self):
        """Confirmed live: create_order() never persisted order_date at all
        before this fix — it stayed NULL for every normally-created order,
        silently excluding it from any report that filters PurchaseOrder by
        order_date (e.g. get_profit_loss_report)."""
        product = _make_product(id=uuid.uuid4())
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
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar.return_value = 0
            elif call_count == 3:
                result.scalar_one_or_none.return_value = None
            else:
                order_obj = next(
                    (o for o in added_objects if hasattr(o, "order_number")), None
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
                OrderLineItemCreate(product_id=product.id, quantity=1, unit_cost=Decimal("10"))
            ],
        )
        order = await create_order(db, data, uuid.uuid4())
        assert order.order_date == date.today()

    @pytest.mark.asyncio
    async def test_order_date_preserved_when_explicitly_provided(self):
        product = _make_product(id=uuid.uuid4())
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
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar.return_value = 0
            elif call_count == 3:
                result.scalar_one_or_none.return_value = None
            else:
                order_obj = next(
                    (o for o in added_objects if hasattr(o, "order_number")), None
                )
                result.scalar_one.return_value = order_obj
                result.scalar_one_or_none.return_value = order_obj
                result.scalar.return_value = None
            return result

        db.execute = mock_execute

        data = OrderCreate(
            supplier_name="Acme Corp",
            currency="USD",
            order_date=date(2025, 6, 26),
            line_items=[
                OrderLineItemCreate(product_id=product.id, quantity=1, unit_cost=Decimal("10"))
            ],
        )
        order = await create_order(db, data, uuid.uuid4())
        assert order.order_date == date(2025, 6, 26)

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

    @pytest.mark.asyncio
    async def test_list_orders_sorts_by_order_date_with_deterministic_tiebreak(self):
        """Regression test: list_orders() must sort by order_date (falling
        back to created_at), not created_at alone — otherwise imported
        historical orders display in insertion order instead of real
        chronological order. order_date is day-precision, so a secondary
        tiebreak (PurchaseOrder.id) is required for stable pagination when
        multiple orders share the same date."""
        db = _mock_db()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        list_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        await list_orders(db)

        list_query = db.execute.call_args_list[1].args[0]
        order_by_clauses = list_query._order_by_clause.clauses
        assert len(order_by_clauses) == 2, (
            "expected a primary sort key plus a deterministic tiebreaker"
        )
        primary_sql = str(order_by_clauses[0])
        assert "coalesce" in primary_sql.lower()
        assert "order_date" in primary_sql.lower()
        assert "created_at" in primary_sql.lower()
        assert "id" in str(order_by_clauses[1]).lower()

    @pytest.mark.asyncio
    async def test_get_order_status_counts_returns_dict(self):
        """get_order_status_counts returns a dict mapping status → count."""
        from src.orders.service import get_order_status_counts
        from src.orders.models import OrderStatus

        db = _mock_db()
        rows_result = MagicMock()
        rows_result.all.return_value = [
            (OrderStatus.PENDING, 3),
            (OrderStatus.ORDERED, 1),
        ]
        db.execute = AsyncMock(return_value=rows_result)

        counts = await get_order_status_counts(db)
        assert counts["PENDING"] == 3
        assert counts["ORDERED"] == 1

    @pytest.mark.asyncio
    async def test_get_order_status_counts_empty_db(self):
        """get_order_status_counts returns empty dict when no orders exist."""
        from src.orders.service import get_order_status_counts

        db = _mock_db()
        rows_result = MagicMock()
        rows_result.all.return_value = []
        db.execute = AsyncMock(return_value=rows_result)

        counts = await get_order_status_counts(db)
        assert counts == {}


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
    async def test_update_fx_rate_recomputes_usd_total_from_ngn(self):
        """Updating fx_rate_at_creation alone recomputes unit_cost and total_amount
        from unit_cost_ngn / new_rate for each line item that has unit_cost_ngn."""
        item = _make_line_item(
            unit_cost=Decimal("500.000000"),   # 750000 / 1500
            unit_cost_ngn=Decimal("750000.000000"),
            line_total=Decimal("5000.000000"),  # 500 * 10
            quantity=10,
        )
        order = _make_order(
            status=OrderStatus.ORDERED,
            fx_rate_at_creation=Decimal("1500.000000"),
            total_amount=Decimal("5000.000000"),
            line_items=[item],
        )
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(fx_rate_at_creation=Decimal("1200.000000"))
        result = await update_order(db, order.id, data, uuid.uuid4())

        # 750000 NGN / 1200 = 625 USD per unit × 10 = 6250 USD total
        assert result.line_items[0].unit_cost == Decimal("625.000000")
        assert result.line_items[0].line_total == Decimal("6250.000000")
        assert result.total_amount == Decimal("6250.000000")

    @pytest.mark.asyncio
    async def test_update_fx_rate_no_recompute_without_unit_cost_ngn(self):
        """Updating fx_rate_at_creation does not change total_amount when
        line items have no unit_cost_ngn (USD-native orders)."""
        item = _make_line_item(
            unit_cost=Decimal("500.000000"),
            line_total=Decimal("5000.000000"),
            quantity=10,
        )
        item.unit_cost_ngn = None
        order = _make_order(
            status=OrderStatus.ORDERED,
            fx_rate_at_creation=Decimal("1500.000000"),
            total_amount=Decimal("5000.000000"),
            line_items=[item],
        )
        db = _mock_db_with_execute(scalar_result=order)

        data = OrderUpdate(fx_rate_at_creation=Decimal("1200.000000"))
        result = await update_order(db, order.id, data, uuid.uuid4())

        assert result.total_amount == Decimal("5000.000000")

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
            elif call_count in (2, 3):
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
            elif call_count in (2, 3):
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
            elif call_count in (2, 3):
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
            elif call_count in (2, 3):
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
    async def test_record_payment_fx_rate_optional_when_currency_matches_order(self):
        """fx_rate is optional when the payment currency already matches the
        order's own currency — no conversion is needed."""
        order = _make_order(total_amount=Decimal("5000"), currency="USD")
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
            payment_method="CASH",
        )
        payment = await record_payment(db, order.id, data, uuid.uuid4())
        assert payment.fx_rate is None
        assert payment.amount == Decimal("500")
        assert payment.original_amount is None
        assert payment.original_currency is None

    @pytest.mark.asyncio
    async def test_record_payment_missing_fx_rate_raises_when_currency_differs(self):
        """A payment in a different currency than the order's own must
        supply an fx_rate — otherwise there's no way to know what it's
        actually worth against the order's balance."""
        order = _make_order(total_amount=Decimal("5000"), currency="USD")
        db = _mock_db()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=order))
        )

        data = PaymentCreate(
            amount=Decimal("500"),
            currency="NGN",
            payment_date=date(2026, 6, 11),
            payment_method="CASH",
        )
        with pytest.raises(MissingFxRateError):
            await record_payment(db, order.id, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_record_payment_converts_ngn_to_usd_order(self):
        """Regression test for the real dogfood scenario: paying ₦4,800,000
        at a rate of 1480 against a USD-denominated order must convert to
        $3,243.24 — not be compared/stored as a raw 4,800,000 (which would
        look like a huge overpayment against a small USD balance)."""
        order = _make_order(total_amount=Decimal("16782.7275"), currency="USD")
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
                result.scalar.return_value = Decimal("3243.243243")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = PaymentCreate(
            amount=Decimal("4800000"),
            currency="NGN",
            fx_rate=Decimal("1480"),
            payment_date=date(2026, 1, 14),
            payment_method="BANK_TRANSFER",
        )
        payment = await record_payment(db, order.id, data, uuid.uuid4())
        assert payment.currency == "USD"
        assert payment.amount == Decimal("3243.243243")
        assert payment.fx_rate == Decimal("1480")
        assert payment.original_amount == Decimal("4800000")
        assert payment.original_currency == "NGN"

    @pytest.mark.asyncio
    async def test_overpayment_check_uses_converted_amount_not_raw(self):
        """A large NGN figure that converts to a small USD amount must NOT
        be rejected as an overpayment just because the raw number is bigger
        than the USD balance."""
        order = _make_order(total_amount=Decimal("16782.7275"), currency="USD")
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count <= 2:
                result.scalar_one_or_none.return_value = order
            elif call_count == 3:
                result.one.return_value = (Decimal("0"), 0)
            elif call_count == 4:
                result.scalar.return_value = Decimal("3243.243243")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = PaymentCreate(
            amount=Decimal("4800000"),  # >> balance in raw NGN terms
            currency="NGN",
            fx_rate=Decimal("1480"),  # converts to ~$3,243.24, well within balance
            payment_date=date(2026, 1, 14),
            payment_method="BANK_TRANSFER",
        )
        payment = await record_payment(db, order.id, data, uuid.uuid4())
        assert payment.amount == Decimal("3243.243243")

    def test_payment_create_rejects_zero_or_negative_fx_rate(self):
        """A negative fx_rate would silently flip _convert_to_order_currency()'s
        sign, storing a negative payment that corrupts the order's balance
        instead of reducing it — must be rejected at the schema level, same
        as amount already is."""
        from pydantic import ValidationError

        for bad_rate in (Decimal("0"), Decimal("-1480")):
            with pytest.raises(ValidationError):
                PaymentCreate(
                    amount=Decimal("500"),
                    currency="NGN",
                    fx_rate=bad_rate,
                    payment_date=date(2026, 1, 14),
                    payment_method="BANK_TRANSFER",
                )

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


class TestUpdatePayment:
    """update_payment() — editing an existing payment (e.g. correcting its
    fx_rate so it fully covers the balance), not just void-and-re-record."""

    @pytest.mark.asyncio
    async def test_correcting_fx_rate_recomputes_converted_amount(self):
        """The real use case: a payment was recorded at the wrong rate;
        editing just the fx_rate re-derives amount from the payment's own
        original_amount/original_currency (not its already-converted
        amount), so a smaller/larger rate correctly changes how much of
        the order's balance this payment actually covers."""
        from src.orders.schemas import PaymentUpdate
        from src.orders.service import update_payment

        order = _make_order(total_amount=Decimal("19180.26"), currency="USD")
        payment = OrderPayment(
            order_id=order.id,
            amount=Decimal("2123.239382"),  # 3,142,000 / 1480 (the wrong rate)
            currency="USD",
            fx_rate=Decimal("1480"),
            original_amount=Decimal("3142000"),
            original_currency="NGN",
            payment_date=date(2026, 2, 19),
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
                # get_order() inside get_payment_summary()
                result.scalar_one_or_none.return_value = order
            elif call_count == 4:
                # sum/count in get_payment_summary — this payment's OWN old
                # amount is still counted here (not yet mutated)
                result.one.return_value = (Decimal("2123.239382"), 1)
            elif call_count == 5:
                # sum in _sync_payment_status, post-mutation
                result.scalar.return_value = Decimal("19180.260000")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        # New rate chosen so ₦3,142,000 exactly covers the remaining
        # balance: 3,142,000 / (19180.26 - 0) is not it — the order also
        # has no other payments here, so the rate that exactly zeroes the
        # balance is 3,142,000 / 19,180.26.
        new_rate = (Decimal("3142000") / Decimal("19180.26")).quantize(Decimal("0.000001"))
        result = await update_payment(
            db, order.id, payment.id, PaymentUpdate(fx_rate=new_rate)
        )

        assert result.fx_rate == new_rate
        assert result.original_amount == Decimal("3142000")
        assert result.original_currency == "NGN"
        assert result.amount == (Decimal("3142000") / new_rate).quantize(Decimal("0.000001"))
        assert order.payment_status == OrderPaymentStatus.PAID

    @pytest.mark.asyncio
    async def test_rejects_editing_a_voided_payment(self):
        from src.orders.exceptions import PaymentAlreadyVoidedError
        from src.orders.schemas import PaymentUpdate
        from src.orders.service import update_payment

        order = _make_order()
        payment = OrderPayment(
            order_id=order.id,
            amount=Decimal("1000"),
            currency="USD",
            payment_date=date(2026, 3, 15),
            payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.VOIDED,
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
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        with pytest.raises(PaymentAlreadyVoidedError):
            await update_payment(
                db, order.id, payment.id, PaymentUpdate(fx_rate=Decimal("1500"))
            )

    @pytest.mark.asyncio
    async def test_overpayment_check_excludes_this_payments_own_amount(self):
        """A payment must be editable up to (balance + its own current
        amount) — not rejected just because its existing amount is already
        counted in today's balance_remaining."""
        from src.orders.schemas import PaymentUpdate
        from src.orders.service import update_payment

        order = _make_order(total_amount=Decimal("5000"), currency="USD")
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
                result.scalar_one_or_none.return_value = order
            elif call_count == 4:
                # total_paid=1000 (just this payment) -> balance=4000;
                # balance excluding this payment = 4000 + 1000 = 5000
                result.one.return_value = (Decimal("1000"), 1)
            elif call_count == 5:
                # sum in _sync_payment_status, post-mutation
                result.scalar.return_value = Decimal("5000")
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        # Within the allowed ceiling (5000) — must NOT raise.
        await update_payment(
            db, order.id, payment.id, PaymentUpdate(amount=Decimal("5000"))
        )

    @pytest.mark.asyncio
    async def test_overpayment_still_rejected_beyond_the_ceiling(self):
        from src.orders.exceptions import OverpaymentError
        from src.orders.schemas import PaymentUpdate
        from src.orders.service import update_payment

        order = _make_order(total_amount=Decimal("5000"), currency="USD")
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
                result.scalar_one_or_none.return_value = order
            elif call_count == 4:
                result.one.return_value = (Decimal("1000"), 1)
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        with pytest.raises(OverpaymentError):
            await update_payment(
                db, order.id, payment.id, PaymentUpdate(amount=Decimal("5000.01"))
            )

    def test_schema_rejects_currency_change_without_amount(self):
        """Without a fresh amount, update_payment() would re-derive the raw
        paid figure from the payment's already-converted amount and
        re-interpret it as if denominated in the new currency — wrong
        math. The schema must reject this combination up front."""
        from pydantic import ValidationError
        from src.orders.schemas import PaymentUpdate

        with pytest.raises(ValidationError):
            PaymentUpdate(currency="EUR")

    def test_schema_accepts_currency_change_with_amount(self):
        from src.orders.schemas import PaymentUpdate

        update = PaymentUpdate(currency="EUR", amount=Decimal("100"), fx_rate=Decimal("1200"))
        assert update.currency == "EUR"
        assert update.amount == Decimal("100")


class TestComputeFxVariance:
    """Purely informational (task 182) — booked landed-cost rate vs. the
    payment-amount-weighted average of what was actually paid. Must never
    feed back into InventoryBatch.landed_cost_per_unit or Sale.fifo_cogs —
    only ever surfaced as a read-only figure."""

    def _payment(self, **overrides):
        defaults = dict(
            order_id=uuid.uuid4(),
            amount=Decimal("1000"),
            currency="USD",
            fx_rate=None,
            payment_date=date(2026, 3, 15),
            payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.COMPLETED,
            recorded_by=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        payment = OrderPayment(**defaults)
        payment.id = uuid.uuid4()
        return payment

    def test_no_booked_rate_returns_none(self):
        from src.orders.service import compute_fx_variance

        order = _make_order(fx_rate_at_creation=None, fx_rate_at_delivery=None)
        order.payments = [self._payment(fx_rate=Decimal("1600"))]
        assert compute_fx_variance(order) is None

    def test_no_rated_payments_returns_none(self):
        """Payments in the order's own currency have fx_rate=None (no
        conversion happened) — nothing to compare the booked rate against."""
        from src.orders.service import compute_fx_variance

        order = _make_order(fx_rate_at_delivery=Decimal("1600"))
        order.payments = [self._payment(fx_rate=None)]
        assert compute_fx_variance(order) is None

    def test_prefers_delivery_rate_over_creation_rate(self):
        from src.orders.service import compute_fx_variance

        order = _make_order(
            fx_rate_at_creation=Decimal("1500"), fx_rate_at_delivery=Decimal("1600")
        )
        order.payments = [self._payment(fx_rate=Decimal("1650"))]
        # booked = 1600 (delivery, not creation); paid at 1650 -> +50 variance
        assert compute_fx_variance(order) == Decimal("50")

    def test_falls_back_to_creation_rate_when_no_delivery_rate(self):
        from src.orders.service import compute_fx_variance

        order = _make_order(
            fx_rate_at_creation=Decimal("1500"), fx_rate_at_delivery=None
        )
        order.payments = [self._payment(fx_rate=Decimal("1450"))]
        # booked = 1500 (creation, fallback); paid at 1450 -> -50 variance
        assert compute_fx_variance(order) == Decimal("-50")

    def test_weights_by_payment_amount(self):
        from src.orders.service import compute_fx_variance

        order = _make_order(fx_rate_at_delivery=Decimal("1500"))
        order.payments = [
            self._payment(amount=Decimal("3000"), fx_rate=Decimal("1600")),
            self._payment(amount=Decimal("1000"), fx_rate=Decimal("1400")),
        ]
        # weighted avg = (3000*1600 + 1000*1400) / 4000 = 1550; variance = +50
        assert compute_fx_variance(order) == Decimal("50")

    def test_excludes_voided_payments(self):
        from src.orders.service import compute_fx_variance

        order = _make_order(fx_rate_at_delivery=Decimal("1500"))
        order.payments = [
            self._payment(amount=Decimal("1000"), fx_rate=Decimal("2000"), status=PaymentStatus.VOIDED),
            self._payment(amount=Decimal("1000"), fx_rate=Decimal("1500")),
        ]
        # Voided payment's wildly-off rate must not pull the average —
        # only the COMPLETED one counts, so variance is 0.
        assert compute_fx_variance(order) == Decimal("0")


class TestPaymentBalanceTolerance:
    """Multi-currency payments are converted via amount/fx_rate division
    (see _convert_to_order_currency), which leaves a sub-cent residue once
    several converted amounts are summed. A truly-settled order shouldn't
    stay stuck on PARTIAL/"Partially Paid" because of that residue."""

    @pytest.mark.asyncio
    async def test_sync_payment_status_treats_subcent_residue_as_paid(self):
        """Real-world case: PO-2026-00004's three NGN payments converted to
        USD sum to 19180.259995 against a 19180.26 total — a $0.000005
        shortfall from real Decimal division, not a mocked exact match."""
        from src.orders.models import OrderPaymentStatus
        from src.orders.service import _sync_payment_status

        order = _make_order(total_amount=Decimal("19180.26"), currency="USD")
        total_paid = (
            Decimal("4800000") / Decimal("1480")
            + Decimal("3142000") / Decimal("1363")
            + Decimal("19042334") / Decimal("1396.904540")
        ).quantize(Decimal("0.000001"))

        db = _mock_db()
        result = MagicMock()
        result.scalar.return_value = total_paid
        db.execute = AsyncMock(return_value=result)

        await _sync_payment_status(db, order)

        assert order.total_amount - total_paid <= Decimal("0.01")
        assert order.payment_status == OrderPaymentStatus.PAID

    @pytest.mark.asyncio
    async def test_sync_payment_status_still_partial_beyond_tolerance(self):
        """A real outstanding balance (well above the sub-cent tolerance)
        must still be reported as PARTIAL, not silently marked PAID."""
        from src.orders.models import OrderPaymentStatus
        from src.orders.service import _sync_payment_status

        order = _make_order(total_amount=Decimal("19180.26"), currency="USD")
        db = _mock_db()
        result = MagicMock()
        result.scalar.return_value = Decimal("19175.00")  # $5.26 short
        db.execute = AsyncMock(return_value=result)

        await _sync_payment_status(db, order)

        assert order.payment_status == OrderPaymentStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_get_payment_summary_is_fully_paid_within_tolerance(self):
        from src.orders.service import get_payment_summary

        order = _make_order(total_amount=Decimal("19180.26"), currency="USD")
        total_paid = Decimal("19180.259995")

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            else:
                result.one.return_value = (total_paid, 3)
            return result

        db.execute = mock_execute

        summary = await get_payment_summary(db, order.id, order.created_by)

        assert summary.is_fully_paid is True


class TestCorrectDeliveredOrderCosts:
    """correct_delivered_order_costs() — the narrow, DELIVERED-only cost
    correction that update_order() deliberately can't do (task 179)."""

    @pytest.mark.asyncio
    async def test_rejects_non_delivered_order(self):
        from src.orders.exceptions import OrderNotDeliveredError
        from src.orders.schemas import LineItemCostCorrection
        from src.orders.service import correct_delivered_order_costs

        order = _make_order(status=OrderStatus.PENDING)
        db = _mock_db_with_execute(scalar_result=order)
        correction = LineItemCostCorrection(
            line_item_id=uuid.uuid4(), new_unit_cost=Decimal("6.55")
        )

        with pytest.raises(OrderNotDeliveredError):
            await correct_delivered_order_costs(db, order.id, [correction])

    @pytest.mark.asyncio
    async def test_rejects_line_item_not_on_order(self):
        from src.orders.exceptions import LineItemNotFoundError
        from src.orders.schemas import LineItemCostCorrection
        from src.orders.service import correct_delivered_order_costs

        item = _make_line_item(
            unit_cost=Decimal("5.731250"), quantity=41, line_total=Decimal("235.00")
        )
        order = _make_order(status=OrderStatus.DELIVERED, line_items=[item])
        db = _mock_db_with_execute(scalar_result=order)
        correction = LineItemCostCorrection(
            line_item_id=uuid.uuid4(), new_unit_cost=Decimal("6.55")
        )

        with pytest.raises(LineItemNotFoundError):
            await correct_delivered_order_costs(db, order.id, [correction])

    @pytest.mark.asyncio
    async def test_full_cascade_through_batches_and_mixed_batch_sale(self):
        """Regression test for the real PO-2026-00004 correction: fixing one
        line item's cost must update its InventoryBatch AND recompute every
        sale that drew from it — including a sale that also drew from a
        DIFFERENT (untouched) batch for the same product, which must keep
        its untouched portion's old cost while only the touched portion's
        contribution changes."""
        from src.orders.schemas import LineItemCostCorrection
        from src.orders.service import correct_delivered_order_costs

        product_id = uuid.uuid4()
        untouched_item = _make_line_item(
            product_id=uuid.uuid4(),
            unit_cost=Decimal("5.26"),
            quantity=96,
            line_total=Decimal("504.96"),
        )
        corrected_item = _make_line_item(
            product_id=product_id,
            unit_cost=Decimal("5.731250"),
            quantity=41,
            line_total=Decimal("235.0"),
        )
        order = _make_order(
            status=OrderStatus.DELIVERED,
            line_items=[untouched_item, corrected_item],
        )

        touched_batch = InventoryBatch(
            product_id=product_id,
            order_id=order.id,
            variant_id=None,
            quantity_received=41,
            quantity_remaining=0,
            unit_cost_usd=Decimal("5.731250"),
            fx_rate_at_arrival=Decimal("1600"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=Decimal("9170.000000"),
            received_at=date(2026, 1, 14),
            created_at=datetime.now(timezone.utc),
        )
        touched_batch.id = uuid.uuid4()

        # A sale that drew 10 units from the touched batch and 5 from an
        # untouched batch elsewhere (different order) for the same product.
        mixed_sale_id = uuid.uuid4()
        untouched_batch_landed_cost = Decimal("8000.000000")
        fc_touched = FifoConsumption(
            sale_id=mixed_sale_id, batch_id=touched_batch.id, quantity_consumed=10
        )
        fc_untouched = FifoConsumption(
            sale_id=mixed_sale_id, batch_id=uuid.uuid4(), quantity_consumed=5
        )
        mixed_sale = Sale(
            id=mixed_sale_id,
            product_id=product_id,
            quantity=15,
            unit_price=Decimal("12000"),
            total_amount=Decimal("180000"),
            currency="NGN",
            sale_date=date(2026, 2, 1),
            channel=SaleChannel.RETAIL,
            recorded_by=uuid.uuid4(),
            business_id=uuid.uuid4(),
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
                # InventoryBatch lookup for the corrected line item
                result.scalars.return_value.all.return_value = [touched_batch]
            elif call_count == 3:
                # distinct sale_ids touching the corrected batch
                result.all.return_value = [(mixed_sale_id,)]
            elif call_count == 4:
                # this sale's full consumption set, joined to (now-updated)
                # batch costs
                result.all.return_value = [
                    (fc_touched, touched_batch.landed_cost_per_unit),
                    (fc_untouched, untouched_batch_landed_cost),
                ]
            elif call_count == 5:
                result.scalar_one.return_value = mixed_sale
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        correction = LineItemCostCorrection(
            line_item_id=corrected_item.id, new_unit_cost=Decimal("6.55")
        )
        result = await correct_delivered_order_costs(db, order.id, [correction])

        # Line item + batch corrected
        assert corrected_item.unit_cost == Decimal("6.55")
        assert corrected_item.line_total == Decimal("268.55")  # 6.55 * 41
        assert touched_batch.unit_cost_usd == Decimal("6.55")
        # 6.55 * 1600
        assert touched_batch.landed_cost_per_unit == Decimal("10480.000000")

        # Order total = corrected line item + untouched line item, unchanged
        assert result.total_amount == Decimal("504.96") + Decimal("268.55")

        # Mixed-batch sale: 10 units at the NEW touched cost + 5 units at the
        # OLD untouched cost — not a blanket resum at one rate.
        expected_cogs = (10 * Decimal("10480.000000")) + (
            5 * untouched_batch_landed_cost
        )
        assert mixed_sale.fifo_cogs == expected_cogs.quantize(Decimal("0.000001"))
        expected_profit = mixed_sale.total_amount - mixed_sale.fifo_cogs
        assert mixed_sale.fifo_gross_profit == expected_profit

    @pytest.mark.asyncio
    async def test_order_wide_fx_rate_and_shipping_cascade_to_every_batch(self):
        """Correcting fx_rate_at_creation/shipping_cost (not a line-item
        unit_cost) must recompute EVERY batch on the order — not just ones
        tied to a specific line item — using the identical fallback/formula
        transition_status()'s DELIVERED handling used to create them:
        fx_rate = fx_rate_at_delivery or fx_rate_at_creation or 1500;
        logistics_per_unit = (shipping_cost + clearing_cost) / total_units."""
        from src.orders.service import correct_delivered_order_costs

        item_a = _make_line_item(
            product_id=uuid.uuid4(),
            unit_cost=Decimal("5.26"),
            quantity=80,
            line_total=Decimal("420.80"),
        )
        item_b = _make_line_item(
            product_id=uuid.uuid4(),
            unit_cost=Decimal("6.55"),
            quantity=20,
            line_total=Decimal("131.00"),
        )
        order = _make_order(
            status=OrderStatus.DELIVERED,
            line_items=[item_a, item_b],
            fx_rate_at_creation=Decimal("1600"),
            fx_rate_at_delivery=None,
            shipping_cost=Decimal("0"),
            clearing_cost=Decimal("0"),
        )

        batch_a = InventoryBatch(
            product_id=item_a.product_id,
            order_id=order.id,
            variant_id=None,
            quantity_received=80,
            quantity_remaining=80,
            unit_cost_usd=Decimal("5.26"),
            fx_rate_at_arrival=Decimal("1600"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=Decimal("8416.000000"),
            received_at=date(2026, 1, 14),
            created_at=datetime.now(timezone.utc),
        )
        batch_a.id = uuid.uuid4()
        batch_b = InventoryBatch(
            product_id=item_b.product_id,
            order_id=order.id,
            variant_id=None,
            quantity_received=20,
            quantity_remaining=20,
            unit_cost_usd=Decimal("6.55"),
            fx_rate_at_arrival=Decimal("1600"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=Decimal("10480.000000"),
            received_at=date(2026, 1, 14),
            created_at=datetime.now(timezone.utc),
        )
        batch_b.id = uuid.uuid4()

        sale_id = uuid.uuid4()
        fc = FifoConsumption(sale_id=sale_id, batch_id=batch_a.id, quantity_consumed=10)
        sale = Sale(
            id=sale_id,
            product_id=item_a.product_id,
            quantity=10,
            unit_price=Decimal("12000"),
            total_amount=Decimal("120000"),
            currency="NGN",
            sale_date=date(2026, 2, 1),
            channel=SaleChannel.RETAIL,
            recorded_by=uuid.uuid4(),
            business_id=uuid.uuid4(),
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
                # ALL batches on the order (order-wide correction path)
                result.scalars.return_value.all.return_value = [batch_a, batch_b]
            elif call_count == 3:
                result.all.return_value = [(sale_id,)]
            elif call_count == 4:
                result.all.return_value = [(fc, batch_a.landed_cost_per_unit)]
            elif call_count == 5:
                result.scalar_one.return_value = sale
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        await correct_delivered_order_costs(
            db,
            order.id,
            [],
            fx_rate_at_creation=Decimal("1650"),
            shipping_cost=Decimal("1000"),
        )

        assert order.fx_rate_at_creation == Decimal("1650")
        assert order.shipping_cost == Decimal("1000")

        # logistics_per_unit = (1000 + 0) / (80 + 20) = 10 per unit
        for batch in (batch_a, batch_b):
            assert batch.fx_rate_at_arrival == Decimal("1650")
            assert batch.logistics_allocation_per_unit == Decimal("10.000000")
        # batch_a: 5.26 * 1650 + 10 = 8679 + 10 = 8689
        assert batch_a.landed_cost_per_unit == Decimal("8679.000000") + Decimal("10")
        # batch_b: 6.55 * 1650 + 10 = 10807.5 + 10 = 10817.5
        assert batch_b.landed_cost_per_unit == Decimal("10807.500000") + Decimal("10")

        assert sale.fifo_cogs == 10 * batch_a.landed_cost_per_unit
        assert sale.fifo_gross_profit == sale.total_amount - sale.fifo_cogs

    @pytest.mark.asyncio
    async def test_fx_rate_at_delivery_correction_takes_priority_over_creation_rate(self):
        """fx_rate_at_delivery was never set on the order (the input only
        ever appeared during the DELIVERED transition itself), so COGS was
        booked at fx_rate_at_creation. Correcting fx_rate_at_delivery here
        must persist it AND take priority over fx_rate_at_creation for the
        batch recompute — matching transition_status()'s own fallback."""
        from src.orders.service import correct_delivered_order_costs

        item = _make_line_item(
            product_id=uuid.uuid4(), unit_cost=Decimal("5.26"), quantity=80
        )
        order = _make_order(
            status=OrderStatus.DELIVERED,
            line_items=[item],
            fx_rate_at_creation=Decimal("1400"),
            fx_rate_at_delivery=None,
            shipping_cost=Decimal("0"),
            clearing_cost=Decimal("0"),
        )
        batch = InventoryBatch(
            product_id=item.product_id,
            order_id=order.id,
            variant_id=None,
            quantity_received=80,
            quantity_remaining=80,
            unit_cost_usd=Decimal("5.26"),
            fx_rate_at_arrival=Decimal("1400"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=Decimal("7364.000000"),
            received_at=date(2026, 7, 3),
            created_at=datetime.now(timezone.utc),
        )
        batch.id = uuid.uuid4()

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [batch]
            elif call_count == 3:
                result.all.return_value = []  # no sales consumed from it
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        await correct_delivered_order_costs(
            db, order.id, [], fx_rate_at_delivery=Decimal("1480")
        )

        assert order.fx_rate_at_delivery == Decimal("1480")
        assert order.fx_rate_at_creation == Decimal("1400")  # untouched
        assert batch.fx_rate_at_arrival == Decimal("1480")
        assert batch.landed_cost_per_unit == Decimal("5.26") * Decimal("1480")

    def test_request_accepts_fx_rate_at_delivery_alone(self):
        req = OrderCostCorrectionRequest(corrections=[], fx_rate_at_delivery=Decimal("1480"))
        assert req.fx_rate_at_delivery == Decimal("1480")

    @pytest.mark.asyncio
    async def test_shipping_details_persists_without_touching_costs(self):
        """shipping_details is plain descriptive text (e.g. a tracking
        note) with no COGS impact — it must persist on the order without
        triggering the batch/FIFO cascade that fx_rate_at_creation and
        shipping_cost correctly do trigger."""
        from src.orders.service import correct_delivered_order_costs

        order = _make_order(status=OrderStatus.DELIVERED, shipping_details="old note")

        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = order
        db.execute = AsyncMock(return_value=result)

        updated = await correct_delivered_order_costs(
            db, order.id, [], shipping_details="Shipped via DHL, tracking #12345"
        )

        assert updated.shipping_details == "Shipped via DHL, tracking #12345"
        # only the get_order() lookup ran — no batch/sale cascade query
        assert db.execute.await_count == 1

    def test_request_rejects_when_nothing_to_correct(self):
        """Neither line-item corrections nor any order-wide field provided
        — schema validation must reject before the service layer even
        runs, matching how amount/fx_rate already validate at this layer."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OrderCostCorrectionRequest(corrections=[])

    def test_request_accepts_shipping_details_alone(self):
        """shipping_details alone is a valid correction — no cost field or
        line-item correction required."""
        req = OrderCostCorrectionRequest(corrections=[], shipping_details="Shipped via DHL")
        assert req.shipping_details == "Shipped via DHL"


class TestRevertDeliveredOrder:
    """revert_delivered_order() — undo a DELIVERED transition made in
    error, back to CLEARED. Narrowly gated: only allowed while nothing has
    been sold from the batches that delivery created (task 94 keeps
    DELIVERED locked otherwise, to protect FIFO/COGS history)."""

    @pytest.mark.asyncio
    async def test_reverts_untouched_delivery_back_to_cleared(self):
        from src.orders.service import revert_delivered_order

        item = _make_line_item(product_id=uuid.uuid4(), quantity=80)
        item.units_remaining = Decimal("80")
        order = _make_order(
            status=OrderStatus.DELIVERED,
            line_items=[item],
            actual_delivery_date=date(2026, 7, 3),
            fx_rate_at_delivery=Decimal("1480"),
        )
        batch = InventoryBatch(
            product_id=item.product_id,
            order_id=order.id,
            variant_id=None,
            quantity_received=80,
            quantity_remaining=80,
            unit_cost_usd=Decimal("5.26"),
            fx_rate_at_arrival=Decimal("1480"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=Decimal("7784.800000"),
            received_at=date(2026, 7, 3),
            created_at=datetime.now(timezone.utc),
        )
        batch.id = uuid.uuid4()

        inventory = _make_inventory(product_id=item.product_id, quantity_on_hand=80)

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                # batches for the order
                result.scalars.return_value.all.return_value = [batch]
            elif call_count == 3:
                # no FifoConsumption rows for this batch
                result.scalar_one_or_none.return_value = None
            elif call_count == 4:
                # adjust_stock()'s InventoryLevel lookup (with_for_update)
                result.scalar_one_or_none.return_value = inventory
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        updated = await revert_delivered_order(db, order.id, uuid.uuid4())

        assert updated.status == OrderStatus.CLEARED
        assert updated.actual_delivery_date is None
        assert updated.fx_rate_at_delivery is None
        assert item.units_remaining is None
        assert inventory.quantity_on_hand == 0
        db.delete.assert_called_once_with(batch)

    @pytest.mark.asyncio
    async def test_batch_query_locks_rows_for_update(self):
        """The batch query must lock its rows (SELECT ... FOR UPDATE) —
        otherwise a concurrent sale's fifo_deduct() (which locks the same
        InventoryBatch rows via its own .with_for_update()) could consume
        from a batch in the window between this function's check and its
        delete, slipping past the 'nothing sold yet' guard entirely."""
        from src.orders.service import revert_delivered_order

        order = _make_order(status=OrderStatus.DELIVERED, line_items=[])

        db = _mock_db()
        call_count = 0
        captured = {}

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            else:
                captured["batch_stmt"] = stmt
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        await revert_delivered_order(db, order.id, uuid.uuid4())

        compiled = str(
            captured["batch_stmt"].compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "for update" in compiled

    @pytest.mark.asyncio
    async def test_rejects_when_batch_already_sold_from(self):
        from src.orders.exceptions import OrderAlreadyConsumedError
        from src.orders.service import revert_delivered_order

        item = _make_line_item(product_id=uuid.uuid4(), quantity=80)
        order = _make_order(status=OrderStatus.DELIVERED, line_items=[item])
        batch = InventoryBatch(
            product_id=item.product_id,
            order_id=order.id,
            variant_id=None,
            quantity_received=80,
            quantity_remaining=70,  # 10 already sold
            unit_cost_usd=Decimal("5.26"),
            fx_rate_at_arrival=Decimal("1480"),
            logistics_allocation_per_unit=Decimal("0"),
            landed_cost_per_unit=Decimal("7784.800000"),
            received_at=date(2026, 7, 3),
            created_at=datetime.now(timezone.utc),
        )
        batch.id = uuid.uuid4()

        db = _mock_db()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [batch]
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        with pytest.raises(OrderAlreadyConsumedError) as exc_info:
            await revert_delivered_order(db, order.id, uuid.uuid4())
        assert order.order_number in str(exc_info.value)
        assert str(order.id) not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rejects_non_delivered_order(self):
        from src.orders.exceptions import OrderNotDeliveredError
        from src.orders.service import revert_delivered_order

        order = _make_order(status=OrderStatus.CLEARED)
        db = _mock_db_with_execute(scalar_result=order)

        with pytest.raises(OrderNotDeliveredError) as exc_info:
            await revert_delivered_order(db, order.id, uuid.uuid4())
        assert order.order_number in str(exc_info.value)
        assert str(order.id) not in str(exc_info.value)


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

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user()
        business_id = u.business_id
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/orders/{fake_id}")
        assert resp.status_code == 404

    def test_list_orders_empty(self):
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
        self._override_auth()
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

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user()
        business_id = u.business_id
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

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
        self._override_auth()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/export.csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_orders_csv_has_correct_headers(self):
        self._override_auth()
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
        self._override_auth()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=self._make_execute_side_effects([]))
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/orders/export.csv")

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert ".csv" in resp.headers.get("content-disposition", "")

    def test_export_orders_csv_with_data_row(self):
        self._override_auth()
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

    def _override_auth(self, app):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user()
        business_id = u.business_id
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return business_id
        app.dependency_overrides[get_current_active_user] = _fake_auth
        app.dependency_overrides[get_current_business_id] = _fake_business_id

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

    @pytest.mark.asyncio
    async def test_order_delivered_propagates_variant_id_to_adjust_stock_and_create_batch(
        self,
    ):
        """A PO line item for a specific variant must credit that
        variant's InventoryLevel row (not the product's aggregate row) and
        tag its InventoryBatch with the same variant_id — otherwise the
        delivered stock lands on the wrong row, and fifo_deduct() later
        has no way to scope FIFO consumption to this variant."""
        from src.orders.service import transition_status
        from src.orders.schemas import StatusTransition

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        item = _make_line_item(
            product_id=product_id, variant_id=variant_id, quantity=50
        )
        order = _make_order(status=OrderStatus.CLEARED)
        order.line_items = [item]

        db = _mock_db()
        db.begin_nested = MagicMock(return_value=NestedTransaction())
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

        with (
            patch(
                "src.orders.service.adjust_stock", new_callable=AsyncMock
            ) as mock_adjust,
            patch(
                "src.orders.service.create_batch", new_callable=AsyncMock
            ) as mock_create_batch,
        ):
            await transition_status(
                db, order.id, StatusTransition(new_status="DELIVERED"), uuid.uuid4()
            )

        assert mock_adjust.call_args.kwargs["variant_id"] == variant_id
        assert mock_create_batch.call_args.kwargs["variant_id"] == variant_id

    @pytest.mark.asyncio
    async def test_order_delivered_backfills_missing_variant_inventory_level(self):
        """adjust_stock() is a strict lookup, never an upsert — it raises
        ProductStockNotFoundError if no InventoryLevel(product_id,
        variant_id) row exists yet. Nothing creates one when a variant is
        created (products/service.py's create_variant() only inserts the
        ProductVariant row), so delivering a PO line item for a
        newly-created variant must backfill the missing row first, or
        every such delivery fails outright instead of the prior (wrong but
        non-crashing) behaviour of crediting the product's aggregate row."""
        from src.orders.service import transition_status
        from src.orders.schemas import StatusTransition
        from src.inventory.exceptions import ProductStockNotFoundError

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        item = _make_line_item(
            product_id=product_id, variant_id=variant_id, quantity=50
        )
        order = _make_order(status=OrderStatus.CLEARED)
        order.line_items = [item]

        db = _mock_db()
        db.add = MagicMock()
        db.begin_nested = MagicMock(return_value=NestedTransaction())
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                # The backfill's own existence check — no row yet.
                result.scalar_one_or_none.return_value = None
            elif call_count == 3:
                # The backfill's aggregate-threshold lookup — no aggregate
                # row either in this scenario, falls back to the default.
                result.scalar_one_or_none.return_value = None
            else:
                # adjust_stock()'s own lookup, after the backfill created
                # the row.
                backfilled = InventoryLevel(
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    low_stock_threshold=10,
                )
                result.scalar_one_or_none.return_value = backfilled
            result.scalars.return_value.all.return_value = []
            result.scalar.return_value = None
            return result

        db.execute = mock_execute

        with patch("src.orders.service.create_batch", new_callable=AsyncMock):
            try:
                await transition_status(
                    db,
                    order.id,
                    StatusTransition(new_status="DELIVERED"),
                    uuid.uuid4(),
                )
            except ProductStockNotFoundError:
                pytest.fail(
                    "delivering a variant PO line item must backfill a "
                    "missing InventoryLevel row instead of raising"
                )

    @pytest.mark.asyncio
    async def test_delivered_backfill_threads_migration_id_through(self):
        """When a data-import job delivers a PO to a brand-new variant in
        the same import, the InventoryLevel row transition_status()
        backfills must carry that import's migration_id (task 173) — passed
        through from load_purchase_orders() via transition_status()'s own
        migration_id param, all the way to ensure_inventory_level_exists().
        Untagged, loader.py's rollback() misses the row and later deleting
        the variant it references raises an unhandled FK IntegrityError."""
        from src.orders.service import transition_status
        from src.orders.schemas import StatusTransition

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        migration_id = uuid.uuid4()
        item = _make_line_item(
            product_id=product_id, variant_id=variant_id, quantity=50
        )
        order = _make_order(status=OrderStatus.CLEARED)
        order.line_items = [item]

        db = _mock_db()
        db.add = MagicMock()
        db.begin_nested = MagicMock(return_value=NestedTransaction())
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                result.scalar_one_or_none.return_value = None
            elif call_count == 3:
                result.scalar_one_or_none.return_value = None
            else:
                backfilled = InventoryLevel(
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    low_stock_threshold=10,
                )
                result.scalar_one_or_none.return_value = backfilled
            result.scalars.return_value.all.return_value = []
            result.scalar.return_value = None
            return result

        db.execute = mock_execute

        with patch("src.orders.service.create_batch", new_callable=AsyncMock):
            await transition_status(
                db,
                order.id,
                StatusTransition(new_status="DELIVERED"),
                uuid.uuid4(),
                migration_id=migration_id,
            )

        # db.add() is called multiple times during this transition (the
        # InventoryLevel backfill, then OrderStatusHistory) — find the
        # InventoryLevel one specifically rather than assuming it's last.
        added_inventory_levels = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], InventoryLevel)
        ]
        assert len(added_inventory_levels) == 1
        assert added_inventory_levels[0].migration_id == migration_id

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

        original_overrides = app.dependency_overrides.copy()
        self._override_auth(app)
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
            app.dependency_overrides = original_overrides


# ---------------------------------------------------------------------------
# Lot consumption reversal (task 170)
# ---------------------------------------------------------------------------


def _rows_result(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _scalars_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


class TestReverseLotConsumption:
    @pytest.mark.asyncio
    async def test_restores_units_remaining_for_each_consumed_lot(self):
        """void_sale() needs this to credit back exactly what
        _deduct_lot_units() took, not guess at a delta."""
        from src.orders.service import reverse_lot_consumption

        sale_id = uuid.uuid4()
        lot1 = _make_line_item(units_remaining=Decimal("0"))
        lot2 = _make_line_item(units_remaining=Decimal("15"))

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([(lot1.id, Decimal("10")), (lot2.id, Decimal("5"))]),
                _scalars_result([lot1, lot2]),
                MagicMock(),
            ]
        )

        await reverse_lot_consumption(db, [sale_id])

        assert lot1.units_remaining == Decimal("10")
        assert lot2.units_remaining == Decimal("20")

    @pytest.mark.asyncio
    async def test_lots_are_fetched_in_a_single_bulk_query(self):
        from src.orders.service import reverse_lot_consumption

        sale_id = uuid.uuid4()
        lot1 = _make_line_item(units_remaining=Decimal("0"))
        lot2 = _make_line_item(units_remaining=Decimal("15"))
        lot3 = _make_line_item(units_remaining=Decimal("3"))

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result(
                    [
                        (lot1.id, Decimal("10")),
                        (lot2.id, Decimal("5")),
                        (lot3.id, Decimal("2")),
                    ]
                ),
                _scalars_result([lot1, lot2, lot3]),
                MagicMock(),
            ]
        )

        await reverse_lot_consumption(db, [sale_id])

        # Exactly 3 calls total: grouped sum, one bulk lot fetch, delete —
        # not one lot-fetch call per lot_id.
        assert db.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_deletes_ledger_rows_after_reversal(self):
        from sqlalchemy import delete

        from src.orders.models import LotConsumption
        from src.orders.service import reverse_lot_consumption

        sale_id = uuid.uuid4()
        lot = _make_line_item(units_remaining=Decimal("0"))

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([(lot.id, Decimal("10"))]),
                _scalars_result([lot]),
                MagicMock(),
            ]
        )

        await reverse_lot_consumption(db, [sale_id])

        delete_stmt = db.execute.await_args_list[-1].args[0]
        assert delete_stmt.table.name == delete(LotConsumption).table.name

    @pytest.mark.asyncio
    async def test_skips_a_lot_that_no_longer_exists(self):
        from src.orders.service import reverse_lot_consumption

        sale_id = uuid.uuid4()
        missing_lot_id = uuid.uuid4()

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([(missing_lot_id, Decimal("10"))]),
                _scalars_result([]),  # the bulk fetch finds nothing
                MagicMock(),
            ]
        )

        await reverse_lot_consumption(db, [sale_id])  # must not raise

    @pytest.mark.asyncio
    async def test_empty_sale_ids_is_a_noop(self):
        from src.orders.service import reverse_lot_consumption

        db = _mock_db()
        db.execute = AsyncMock()

        await reverse_lot_consumption(db, [])

        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_consumption_rows_for_the_given_sales_is_a_noop(self):
        """A sale that never went through _deduct_lot_units() with a
        sale_id (e.g. it predates this ledger) has nothing to reverse —
        must not attempt a delete against zero rows or fail."""
        from src.orders.service import reverse_lot_consumption

        db = _mock_db()
        db.execute = AsyncMock(return_value=_rows_result([]))

        await reverse_lot_consumption(db, [uuid.uuid4()])

        db.execute.assert_awaited_once()  # just the grouped-sum query


# ---------------------------------------------------------------------------
# IDOR ownership checks
# ---------------------------------------------------------------------------


class TestOrdersOwnershipChecks:
    """Non-admin users can only access orders they created."""

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
        business_id = user.business_id or uuid.uuid4()
        async def _fake_auth():
            return user
        async def _fake_business_id():
            return business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_user_cannot_delete_other_users_order(self):
        """Non-admin cannot DELETE (cancel) an order created by someone else."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        requester = _make_user(role=UserRole.SALES_MANAGER)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(requester)

        with TestClient(self.app) as client:
            resp = client.delete(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 403

    def test_user_can_delete_own_order(self):
        """User can DELETE (cancel) an order they created — ownership check must not block."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(owner)

        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/orders/{order.id}")
        assert resp.status_code != 403

    def test_admin_can_delete_any_order(self):
        """Admin bypasses ownership check and can cancel any order."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        admin = _make_user(role=UserRole.ADMIN)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(admin)

        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/orders/{order.id}")
        assert resp.status_code != 403

    def test_user_cannot_transition_other_users_order(self):
        """Non-admin cannot PUT /{id}/status on an order they don't own."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        requester = _make_user(role=UserRole.SALES_MANAGER)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(requester)

        with TestClient(self.app) as client:
            resp = client.put(
                f"/api/v1/orders/{order.id}/status",
                json={"new_status": "CANCELLED"},
            )
        assert resp.status_code == 403

    def test_admin_can_transition_any_order(self):
        """Admin bypasses ownership check on PUT /{id}/status."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        admin = _make_user(role=UserRole.ADMIN)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(admin)

        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/v1/orders/{order.id}/status",
                json={"new_status": "CANCELLED"},
            )
        assert resp.status_code != 403

    def test_get_order_returns_fx_variance(self):
        """GET /{id} surfaces the computed fx_variance field (task 182)."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        order = _make_order(
            created_by=owner.id,
            fx_rate_at_delivery=Decimal("1600"),
            # GET /{id} serializes the full OrderDetailRead — _make_order()
            # doesn't set these (no other existing test previously hit this
            # endpoint via TestClient), so supply the model's own defaults.
            is_purchase_order=True,
            shipping_cost=Decimal("0"),
            clearing_cost=Decimal("0"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
        )
        payment = OrderPayment(
            order_id=order.id,
            amount=Decimal("1000"),
            currency="USD",
            fx_rate=Decimal("1650"),
            payment_date=date(2026, 3, 15),
            payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.COMPLETED,
            recorded_by=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        payment.id = uuid.uuid4()
        order.payments = [payment]
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(owner)

        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200
        assert Decimal(resp.json()["fx_variance"]) == Decimal("50")

    def test_user_cannot_record_payment_on_other_users_order(self):
        """Non-admin cannot POST /{id}/payments on an order they don't own."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        requester = _make_user(role=UserRole.SALES_MANAGER)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(requester)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/orders/{order.id}/payments",
                json={
                    "amount": "100.00",
                    "payment_method": "CASH",
                    "payment_date": "2026-06-13",
                },
            )
        assert resp.status_code == 403

    def test_admin_can_record_payment_on_any_order(self):
        """Admin bypasses ownership check on POST /{id}/payments."""
        from src.auth.models import UserRole
        owner = _make_user(role=UserRole.SALES_MANAGER)
        admin = _make_user(role=UserRole.ADMIN)
        order = _make_order(created_by=owner.id)
        db = _mock_db_with_execute(scalar_result=order)
        self._override_db(db)
        self._override_auth_as(admin)

        with TestClient(self.app, raise_server_exceptions=False) as client:
            resp = client.post(
                f"/api/v1/orders/{order.id}/payments",
                json={
                    "amount": "100.00",
                    "payment_method": "CASH",
                    "payment_date": "2026-06-13",
                },
            )
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Business isolation tests (Task #159)
# ---------------------------------------------------------------------------


class TestOrdersBusinessIsolation:
    @pytest.mark.asyncio
    async def test_orders_isolates_by_business(self):
        """list_orders returns only orders belonging to the requested business_id."""
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

        result_a = await list_orders(db_a, business_id=business_a_id)
        result_b = await list_orders(db_b, business_id=business_b_id)
        items_a = result_a[0] if isinstance(result_a, tuple) else result_a
        items_b = result_b[0] if isinstance(result_b, tuple) else result_b
        assert len(items_a) > 0
        assert len(items_b) == 0

    @pytest.mark.asyncio
    async def test_orders_owner_sees_own_data(self):
        """list_orders returns the caller's orders when business_id matches."""
        business_id = uuid.uuid4()
        mock_order = MagicMock()

        async def fake_execute(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [mock_order]
            r.scalar.return_value = 1
            return r

        db = AsyncMock()
        db.execute = fake_execute
        result = await list_orders(db, business_id=business_id)
        items = result[0] if isinstance(result, tuple) else result
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_create_order_sets_business_id(self):
        """create_order stores the business_id on the PurchaseOrder object."""
        business_id = uuid.uuid4()
        product = _make_product(id=uuid.uuid4())

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
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                result.scalar.return_value = 0
            elif call_count == 3:
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = _make_order()
            return result

        db.execute = mock_execute

        data = OrderCreate(
            supplier_name="Test Supplier",
            currency="USD",
            line_items=[
                OrderLineItemCreate(
                    product_id=product.id,
                    quantity=5,
                    unit_cost=Decimal("100"),
                )
            ],
        )
        await create_order(db, data, user_id=uuid.uuid4(), business_id=business_id)

        purchase_orders = [o for o in added_objects if isinstance(o, PurchaseOrder)]
        assert len(purchase_orders) == 1
        assert purchase_orders[0].business_id == business_id
