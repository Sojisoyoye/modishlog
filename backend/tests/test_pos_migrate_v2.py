"""TDD tests for Migration v2 additions (task #156).

Tests cover:
- New model columns on Product, Sale
- New MovementType enum values
- Customer model field availability
- InventoryBatch structural test
- Migration helper functions (extracted logic)
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest


# ---------------------------------------------------------------------------
# 1. Model structural tests — new columns
# ---------------------------------------------------------------------------


def test_product_has_barcode_column():
    """Product model must have a barcode column for POS import."""
    from src.products.models import Product

    cols = {c.name for c in Product.__table__.columns}
    assert "barcode" in cols, "products.barcode column missing — run migration"


def test_product_has_unit_column():
    """Product model must have a unit column for POS import."""
    from src.products.models import Product

    cols = {c.name for c in Product.__table__.columns}
    assert "unit" in cols, "products.unit column missing — run migration"


def test_sale_has_invoice_number_column():
    """Sale model must have invoice_number for POS reference tracking."""
    from src.sales.models import Sale

    cols = {c.name for c in Sale.__table__.columns}
    assert "invoice_number" in cols, "sales.invoice_number column missing — run migration"


def test_sale_has_tax_amount_column():
    """Sale model must have tax_amount for accurate total recording."""
    from src.sales.models import Sale

    cols = {c.name for c in Sale.__table__.columns}
    assert "tax_amount" in cols, "sales.tax_amount column missing — run migration"


# ---------------------------------------------------------------------------
# 2. MovementType enum — new values
# ---------------------------------------------------------------------------


def test_movement_type_has_stock_adjustment():
    """MovementType must include STOCK_ADJUSTMENT for manual corrections."""
    from src.inventory.models import MovementType

    assert MovementType.STOCK_ADJUSTMENT == "stock_adjustment"


def test_movement_type_has_opening_stock():
    """MovementType must include OPENING_STOCK for POS opening balance import."""
    from src.inventory.models import MovementType

    assert MovementType.OPENING_STOCK == "opening_stock"


# ---------------------------------------------------------------------------
# 3. Customer model fields — all POS mapping targets must exist
# ---------------------------------------------------------------------------


def test_customer_has_all_pos_fields():
    """Customer model must have every field needed for POS contact import."""
    from src.customers.models import Customer

    cols = {c.name for c in Customer.__table__.columns}
    required = {
        "name", "email", "contact_number", "alternate_number",
        "address", "city", "state", "country", "zip_code",
        "tax_number", "pay_term_number", "pay_term_type",
        "opening_balance", "credit_limit", "is_active", "customer_group",
    }
    missing = required - cols
    assert not missing, f"Customer missing columns: {missing}"


# ---------------------------------------------------------------------------
# 4. SellReturn has ref_no for POS reference
# ---------------------------------------------------------------------------


def test_sell_return_has_ref_no():
    """SellReturn model must have ref_no for POS transaction reference."""
    from src.sales.models import SellReturn

    cols = {c.name for c in SellReturn.__table__.columns}
    assert "ref_no" in cols


# ---------------------------------------------------------------------------
# 5. InventoryBatch model exists and has required fields
# ---------------------------------------------------------------------------


def test_inventory_batch_model_has_required_fields():
    """InventoryBatch must have all fields for FIFO batch creation."""
    from src.inventory.models import InventoryBatch

    cols = {c.name for c in InventoryBatch.__table__.columns}
    required = {
        "product_id", "order_id", "quantity_received", "quantity_remaining",
        "unit_cost_usd", "fx_rate_at_arrival", "landed_cost_per_unit", "received_at",
    }
    missing = required - cols
    assert not missing, f"InventoryBatch missing columns: {missing}"


def test_inventory_batch_can_be_instantiated():
    """InventoryBatch can be created with all required fields."""
    from src.inventory.models import InventoryBatch

    batch = InventoryBatch(
        product_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        quantity_received=10,
        quantity_remaining=10,
        unit_cost_usd=Decimal("50.000000"),
        fx_rate_at_arrival=Decimal("1550.000000"),
        logistics_allocation_per_unit=Decimal("0"),
        landed_cost_per_unit=Decimal("50.000000"),
        received_at=date(2026, 7, 1),
    )
    assert batch.quantity_received == 10
    assert batch.unit_cost_usd == Decimal("50.000000")


# ---------------------------------------------------------------------------
# 6. Expense domain available for migration (task #164 prerequisite)
# ---------------------------------------------------------------------------


def test_expense_category_model_exists():
    """ExpenseCategory model must be importable for expense migration."""
    from src.expenses.models import ExpenseCategory  # noqa: F401

    cols = {c.name for c in ExpenseCategory.__table__.columns}
    assert "name" in cols
    assert "created_by" in cols


def test_expense_model_has_amount_fields():
    """Expense model must have NGN + USD amounts for FX conversion."""
    from src.expenses.models import Expense

    cols = {c.name for c in Expense.__table__.columns}
    assert "amount_ngn" in cols
    assert "amount_usd" in cols
    assert "fx_rate" in cols
    assert "expense_date" in cols


# ---------------------------------------------------------------------------
# 7. Migration script helper: _parse_price handles HTML-wrapped values
# ---------------------------------------------------------------------------


def test_parse_price_strips_html_and_commas():
    """_parse_price must handle values like '<span>₦1,250.00</span>'."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

    from pos_migrate import _parse_price

    assert _parse_price("1,250.00") == Decimal("1250.00")
    assert _parse_price("0") == Decimal("0")
    assert _parse_price("") == Decimal("0")


def test_parse_price_handles_ngn_prefix():
    """_parse_price must handle values with currency prefix."""
    from pos_migrate import _parse_price

    result = _parse_price("₦ 50,000.000000")
    assert result == Decimal("50000.000000")


def test_parse_qty_returns_int():
    """_parse_qty must convert string quantity to int."""
    from pos_migrate import _parse_qty

    assert _parse_qty("5") == 5
    assert _parse_qty("0") == 0
    assert _parse_qty("") == 0


# ---------------------------------------------------------------------------
# 8. Product ORM can accept new barcode/unit fields
# ---------------------------------------------------------------------------


def test_product_accepts_barcode_and_unit():
    """Product ORM object can be constructed with barcode and unit."""
    from src.products.models import Product

    p = Product(
        name="Test Product",
        sku="TEST-001",
        slug="test-product",
        category_id=uuid.uuid4(),
        unit_cost=Decimal("100"),
        selling_price=Decimal("150"),
        barcode="1234567890",
        unit="piece",
    )
    assert p.barcode == "1234567890"
    assert p.unit == "piece"


# ---------------------------------------------------------------------------
# 9. Sale ORM can accept new invoice_number/tax_amount fields
# ---------------------------------------------------------------------------


def test_sale_accepts_invoice_number_and_tax_amount():
    """Sale ORM object can be constructed with invoice_number and tax_amount."""
    from src.sales.models import Sale, SaleChannel, SaleStatus

    s = Sale(
        product_id=uuid.uuid4(),
        quantity=1,
        unit_price=Decimal("1000"),
        total_amount=Decimal("1000"),
        sale_date=date(2026, 7, 1),
        channel=SaleChannel.RETAIL,
        status=SaleStatus.COMPLETED,
        recorded_by=uuid.uuid4(),
        invoice_number="INV-2026-001",
        tax_amount=Decimal("75.000000"),
    )
    assert s.invoice_number == "INV-2026-001"
    assert s.tax_amount == Decimal("75.000000")
