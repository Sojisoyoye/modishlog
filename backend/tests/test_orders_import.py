"""Tests for bulk order import via CSV/Excel file upload."""

import csv
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.suppliers.models  # noqa: F401 — registers Supplier mapper
from src.orders.models import OrderStatus, PurchaseOrder
from src.orders.service import import_orders_from_file, build_import_template_csv
from src.products.models import Product


def _make_product(sku="SKU-001", id=None, **overrides):
    defaults = dict(
        name="Test Product",
        sku=sku,
        description="desc",
        category_id=uuid.uuid4(),
        unit_cost=Decimal("100.000000"),
        selling_price=Decimal("150.000000"),
        currency="NGN",
        is_active=True,
    )
    defaults.update(overrides)
    p = Product(**defaults)
    p.id = id if id is not None else uuid.uuid4()
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


def _make_order(**overrides):
    defaults = dict(
        order_number="PO-2026-00001",
        supplier_name="Acme",
        supplier_id=None,
        supplier_contact=None,
        status=OrderStatus.PENDING,
        is_purchase_order=False,
        total_amount=Decimal("1000.000000"),
        currency="USD",
        fx_rate_at_creation=None,
        fx_rate_at_delivery=None,
        expected_delivery_date=None,
        actual_delivery_date=None,
        notes=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    o = PurchaseOrder(**defaults)
    o.id = overrides.get("id", uuid.uuid4())
    o.created_at = datetime.now(timezone.utc)
    o.updated_at = datetime.now(timezone.utc)
    o.line_items = overrides.get("line_items", [])
    o.payments = overrides.get("payments", [])
    o.status_history = overrides.get("status_history", [])
    return o


def _make_csv(*rows: dict) -> bytes:
    """Build a CSV bytes object from a list of row dicts."""
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# build_import_template_csv
# ---------------------------------------------------------------------------


class TestBuildImportTemplateCsv:
    def test_template_contains_required_headers(self):
        content = build_import_template_csv()
        assert "supplier_name" in content
        assert "line_item_sku" in content
        assert "line_item_quantity" in content
        assert "line_item_unit_cost" in content
        assert "currency" in content

    def test_template_contains_optional_headers(self):
        content = build_import_template_csv()
        assert "pay_term_number" in content
        assert "discount_type" in content
        assert "tax_rate" in content
        assert "supplier_invoice_number" in content

    def test_template_has_example_row(self):
        content = build_import_template_csv()
        lines = [l for l in content.splitlines() if l.strip()]
        assert len(lines) >= 2  # header + at least one example row


# ---------------------------------------------------------------------------
# import_orders_from_file — happy path
# ---------------------------------------------------------------------------


def _truthy_result():
    """Mock execute result that returns a truthy object from scalar_one_or_none."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = MagicMock()
    return r


def _count_result(n: int = 0):
    r = MagicMock()
    r.scalar.return_value = n
    return r


def _none_result():
    """Mock that returns None from scalar_one_or_none (e.g. order-number unique check)."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _reload_result(order):
    r = MagicMock()
    r.scalar_one.return_value = order
    return r


def _sku_result(product):
    r = MagicMock()
    r.scalar_one_or_none.return_value = product
    return r


class TestImportOrdersHappyPath:
    @pytest.mark.asyncio
    async def test_single_order_single_line_item(self):
        """
        Execute call order inside import_orders_from_file + create_order:
          1. SKU lookup (import_orders_from_file)
          2. Product-ID validation (create_order)
          3. Order-number count (create_order → _generate_order_number)
          4. Order-number uniqueness check
          5. Reload after insert
        """
        product = _make_product(id=uuid.uuid4(), sku="SKU-001")
        user_id = uuid.uuid4()
        reloaded = _make_order()

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _sku_result(product),   # 1. import: SKU-001 → product
                _truthy_result(),       # 2. create_order: product-ID validation
                _count_result(0),       # 3. _generate_order_number count
                _none_result(),         # 4. _generate_order_number uniqueness
                _reload_result(reloaded),  # 5. reload
            ]
        )

        csv_bytes = _make_csv(
            {
                "supplier_name": "Acme Ltd",
                "currency": "USD",
                "line_item_sku": "SKU-001",
                "line_item_quantity": "5",
                "line_item_unit_cost": "100.00",
            }
        )

        result = await import_orders_from_file(db, csv_bytes, "orders.csv", user_id)
        assert result["created"] == 1
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_two_orders_three_line_items(self):
        """
        Order 1: SKU-A + SKU-B (blank supplier_name continues order 1)
        Order 2: SKU-C

        Execute sequence:
          SKU-A, SKU-B         — import SKU lookups for order 1
          prod-id-A, prod-id-B — create_order product validation
          count, unique, reload — create_order order 1
          SKU-C                — import SKU lookup for order 2
          prod-id-C            — create_order product validation
          count, unique, reload — create_order order 2
        """
        prod1 = _make_product(id=uuid.uuid4(), sku="SKU-A")
        prod2 = _make_product(id=uuid.uuid4(), sku="SKU-B")
        prod3 = _make_product(id=uuid.uuid4(), sku="SKU-C")
        user_id = uuid.uuid4()
        reloaded = _make_order()

        db = _mock_db()
        # All SKU lookups happen before any create_order calls
        db.execute = AsyncMock(
            side_effect=[
                _sku_result(prod1), _sku_result(prod2),          # SKU lookups: order 1
                _sku_result(prod3),                               # SKU lookups: order 2
                _truthy_result(), _truthy_result(),               # create order1: prod-ID validation
                _count_result(0), _none_result(), _reload_result(reloaded),  # create order1
                _truthy_result(),                                 # create order2: prod-ID validation
                _count_result(1), _none_result(), _reload_result(reloaded),  # create order2
            ]
        )

        csv_bytes = _make_csv(
            {"supplier_name": "Acme", "currency": "USD", "line_item_sku": "SKU-A", "line_item_quantity": "2", "line_item_unit_cost": "50.00"},
            {"supplier_name": "",     "currency": "",    "line_item_sku": "SKU-B", "line_item_quantity": "3", "line_item_unit_cost": "80.00"},
            {"supplier_name": "Beta", "currency": "NGN", "line_item_sku": "SKU-C", "line_item_quantity": "1", "line_item_unit_cost": "200.00"},
        )

        result = await import_orders_from_file(db, csv_bytes, "orders.csv", user_id)
        assert result["created"] == 2
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# import_orders_from_file — error cases
# ---------------------------------------------------------------------------


class TestImportOrdersErrors:
    @pytest.mark.asyncio
    async def test_unknown_sku_returns_error(self):
        user_id = uuid.uuid4()
        db = _mock_db()
        sku_result = MagicMock()
        sku_result.scalar_one_or_none.return_value = None  # SKU not found
        db.execute = AsyncMock(return_value=sku_result)

        csv_bytes = _make_csv(
            {
                "supplier_name": "Acme",
                "currency": "USD",
                "line_item_sku": "UNKNOWN-SKU",
                "line_item_quantity": "1",
                "line_item_unit_cost": "50.00",
            }
        )
        result = await import_orders_from_file(db, csv_bytes, "orders.csv", user_id)
        assert result["created"] == 0
        assert len(result["errors"]) > 0
        assert any("UNKNOWN-SKU" in e["message"] for e in result["errors"])

    @pytest.mark.asyncio
    async def test_missing_required_column_returns_error(self):
        user_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock()

        # CSV missing line_item_sku column
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["supplier_name", "currency", "line_item_quantity", "line_item_unit_cost"])
        writer.writerow(["Acme", "USD", "5", "100.00"])
        csv_bytes = buf.getvalue().encode()

        result = await import_orders_from_file(db, csv_bytes, "orders.csv", user_id)
        assert result["created"] == 0
        assert any("line_item_sku" in e["message"] for e in result["errors"])

    @pytest.mark.asyncio
    async def test_invalid_quantity_returns_error(self):
        user_id = uuid.uuid4()
        db = _mock_db()
        product = _make_product(sku="SKU-001")
        sku_result = MagicMock()
        sku_result.scalar_one_or_none.return_value = product
        db.execute = AsyncMock(return_value=sku_result)

        csv_bytes = _make_csv(
            {
                "supplier_name": "Acme",
                "currency": "USD",
                "line_item_sku": "SKU-001",
                "line_item_quantity": "not-a-number",
                "line_item_unit_cost": "100.00",
            }
        )
        result = await import_orders_from_file(db, csv_bytes, "orders.csv", user_id)
        assert result["created"] == 0
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_empty_file_returns_error(self):
        user_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock()

        result = await import_orders_from_file(db, b"", "orders.csv", user_id)
        assert result["created"] == 0
        assert len(result["errors"]) > 0
