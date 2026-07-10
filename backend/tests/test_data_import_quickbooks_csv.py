"""Tests for the QuickBooks CSV adapter (task 162 — QuickBooks vendor adapter).

QuickBooks exports one CSV per entity, each with its own vendor-specific
header names. These tests exercise `QuickBooksCSVAdapter.map_row` against the
well-documented standard QuickBooks Desktop/Online CSV export headers for
Items, Vendors, Customers and Invoices.
"""

import pytest

from src.data_import.etl.adapters.quickbooks import QuickBooksCSVAdapter


@pytest.fixture
def adapter() -> QuickBooksCSVAdapter:
    return QuickBooksCSVAdapter()


# ---------------------------------------------------------------------------
# Items export -> products
# ---------------------------------------------------------------------------


class TestItemsToProducts:
    def test_maps_full_item_row(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Item Name": "Blue Widget",
            "Description": "A widget, but blue",
            "Type": "Inventory Part",
            "Sales Price": "19.99",
            "Purchase Cost": "9.50",
            "Manufacturer's Part Number": "SKU-BW-001",
            "Category": "Widgets",
        }
        mapped = adapter.map_row("products", raw_row)

        assert mapped["name"] == "Blue Widget"
        assert mapped["sku"] == "SKU-BW-001"
        assert mapped["selling_price"] == "19.99"
        assert mapped["unit_cost"] == "9.50"
        # No stable numeric ID column in a QuickBooks Items export — derive a
        # stable source_id from the natural key (Item Name), since QuickBooks
        # itself matches items by name.
        assert mapped["source_id"] == "Blue Widget"
        assert mapped["category_source_id"] == "Widgets"
        assert mapped["is_active"] == "true"

    def test_missing_optional_fields_default_sensibly(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Item Name": "Red Widget",
            "Description": "",
            "Type": "Service",
            "Sales Price": "",
            "Purchase Cost": "",
            "Manufacturer's Part Number": "",
            "Category": "",
        }
        mapped = adapter.map_row("products", raw_row)

        assert mapped["name"] == "Red Widget"
        assert mapped["source_id"] == "Red Widget"
        assert mapped["sku"] == ""
        assert mapped["unit_cost"] == "0"
        assert mapped["selling_price"] == "0"
        assert mapped["category_source_id"] == ""

    def test_missing_item_name_raises(self, adapter: QuickBooksCSVAdapter):
        raw_row = {"Description": "No name given", "Sales Price": "5.00"}
        with pytest.raises(ValueError):
            adapter.map_row("products", raw_row)


# ---------------------------------------------------------------------------
# Vendors export -> suppliers
# ---------------------------------------------------------------------------


class TestVendorsToSuppliers:
    def test_maps_full_vendor_row(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Vendor Name": "Acme Supplies",
            "Company Name": "Acme Supplies Ltd",
            "Main Phone": "555-1234",
            "Main Email": "sales@acme.example",
        }
        mapped = adapter.map_row("suppliers", raw_row)

        assert mapped["source_id"] == "Acme Supplies"
        assert mapped["name"] == "Acme Supplies Ltd"
        assert mapped["email"] == "sales@acme.example"
        assert mapped["mobile"] == "555-1234"

    def test_falls_back_to_vendor_name_when_company_name_blank(
        self, adapter: QuickBooksCSVAdapter
    ):
        raw_row = {
            "Vendor Name": "Jane's Beads",
            "Company Name": "",
            "Main Phone": "",
            "Main Email": "",
        }
        mapped = adapter.map_row("suppliers", raw_row)

        assert mapped["source_id"] == "Jane's Beads"
        assert mapped["name"] == "Jane's Beads"
        assert mapped["email"] == ""
        assert mapped["mobile"] == ""

    def test_missing_vendor_name_raises(self, adapter: QuickBooksCSVAdapter):
        raw_row = {"Company Name": "No Vendor Name Co"}
        with pytest.raises(ValueError):
            adapter.map_row("suppliers", raw_row)


# ---------------------------------------------------------------------------
# Customers export -> customers
# ---------------------------------------------------------------------------


class TestCustomersToCustomers:
    def test_maps_full_customer_row(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Customer Name": "John Doe",
            "Company Name": "Doe Enterprises",
            "Main Phone": "555-5678",
            "Main Email": "john@doe.example",
        }
        mapped = adapter.map_row("customers", raw_row)

        assert mapped["source_id"] == "John Doe"
        assert mapped["name"] == "Doe Enterprises"
        assert mapped["email"] == "john@doe.example"
        assert mapped["contact_number"] == "555-5678"

    def test_falls_back_to_customer_name_when_company_name_blank(
        self, adapter: QuickBooksCSVAdapter
    ):
        raw_row = {
            "Customer Name": "Mary Smith",
            "Company Name": "",
            "Main Phone": "555-9999",
            "Main Email": "",
        }
        mapped = adapter.map_row("customers", raw_row)

        assert mapped["source_id"] == "Mary Smith"
        assert mapped["name"] == "Mary Smith"
        assert mapped["contact_number"] == "555-9999"

    def test_missing_customer_name_raises(self, adapter: QuickBooksCSVAdapter):
        raw_row = {"Company Name": "No Customer Name Inc"}
        with pytest.raises(ValueError):
            adapter.map_row("customers", raw_row)


# ---------------------------------------------------------------------------
# Invoices export -> sales
# ---------------------------------------------------------------------------


class TestInvoicesToSales:
    def test_maps_full_invoice_row(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Customer": "John Doe",
            "Product/Service": "Blue Widget",
            "Qty": "3",
            "Rate": "19.99",
            "Amount": "59.97",
            # US MM/DD/YYYY, as QuickBooks always exports — July 10.
            "Invoice Date": "07/10/2026",
        }
        mapped = adapter.map_row("sales", raw_row)

        assert mapped["product_source_id"] == "Blue Widget"
        assert mapped["customer_source_id"] == "John Doe"
        assert mapped["quantity"] == "3"
        assert mapped["unit_price"] == "19.99"
        # Normalised to unambiguous ISO 8601 so the shared flexible date
        # parser (which tries day-first before month-first) can't misread
        # QuickBooks' US-ordered date as 7 October instead of 10 July.
        assert mapped["sale_date"] == "2026-07-10"
        # QuickBooks invoices are B2B/wholesale-style transactions, distinct
        # from POS retail sales.
        assert mapped["channel"] == "wholesale"
        assert mapped["variant_source_id"] == ""

    def test_us_date_not_misread_as_day_first(self, adapter: QuickBooksCSVAdapter):
        # A date where day <= 12 is exactly the case that would silently
        # flip under a naive day-first parse: 03/04/2026 must mean March 4,
        # not 3 April.
        raw_row = {
            "Customer": "John Doe",
            "Product/Service": "Blue Widget",
            "Qty": "1",
            "Rate": "1.00",
            "Amount": "1.00",
            "Invoice Date": "03/04/2026",
        }
        mapped = adapter.map_row("sales", raw_row)
        assert mapped["sale_date"] == "2026-03-04"

    def test_missing_qty_defaults_to_one(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Customer": "Jane Roe",
            "Product/Service": "Red Widget",
            "Qty": "",
            "Rate": "5.00",
            "Amount": "5.00",
            "Invoice Date": "07/10/2026",
        }
        mapped = adapter.map_row("sales", raw_row)
        assert mapped["quantity"] == "1"

    def test_fractional_qty_is_rounded_to_whole_unit(self, adapter: QuickBooksCSVAdapter):
        # QuickBooks allows fractional Qty for weight/hour-billed items, but
        # the transformer does a hard int() cast downstream — a fractional
        # string would otherwise cause the whole sale row to be dropped.
        raw_row = {
            "Customer": "Jane Roe",
            "Product/Service": "Ribbon (per metre)",
            "Qty": "2.6",
            "Rate": "5.00",
            "Amount": "13.00",
            "Invoice Date": "07/10/2026",
        }
        mapped = adapter.map_row("sales", raw_row)
        assert mapped["quantity"] == "3"

    def test_missing_product_service_raises(self, adapter: QuickBooksCSVAdapter):
        raw_row = {
            "Customer": "Jane Roe",
            "Product/Service": "",
            "Qty": "1",
            "Rate": "5.00",
            "Amount": "5.00",
            "Invoice Date": "07/10/2026",
        }
        with pytest.raises(ValueError):
            adapter.map_row("sales", raw_row)

    def test_blank_customer_is_allowed(self, adapter: QuickBooksCSVAdapter):
        # A walk-in/cash invoice with no Customer column value should import
        # as a sale with no linked customer, not raise.
        raw_row = {
            "Customer": "",
            "Product/Service": "Blue Widget",
            "Qty": "1",
            "Rate": "19.99",
            "Amount": "19.99",
            "Invoice Date": "07/10/2026",
        }
        mapped = adapter.map_row("sales", raw_row)
        assert mapped["customer_source_id"] == ""


# ---------------------------------------------------------------------------
# Unsupported / unknown entities
# ---------------------------------------------------------------------------


class TestUnsupportedEntities:
    def test_unknown_entity_raises(self, adapter: QuickBooksCSVAdapter):
        with pytest.raises(ValueError):
            adapter.map_row("widgets", {"foo": "bar"})

    def test_product_variants_entity_raises_not_supported(
        self, adapter: QuickBooksCSVAdapter
    ):
        # QuickBooks has no native multi-attribute variant concept, so this
        # entity is intentionally unsupported by this adapter.
        with pytest.raises(ValueError):
            adapter.map_row("product_variants", {"source_id": "x"})


# ---------------------------------------------------------------------------
# map_rows (bulk helper from BaseCSVAdapter)
# ---------------------------------------------------------------------------


class TestMapRows:
    def test_maps_multiple_rows(self, adapter: QuickBooksCSVAdapter):
        rows = [
            {"Item Name": "Widget A", "Sales Price": "1.00", "Purchase Cost": "0.50"},
            {"Item Name": "Widget B", "Sales Price": "2.00", "Purchase Cost": "1.00"},
        ]
        mapped = adapter.map_rows("products", rows)
        assert [r["source_id"] for r in mapped] == ["Widget A", "Widget B"]
