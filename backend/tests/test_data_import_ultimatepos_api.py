"""Tests for the UltimatePOS live API extractor.

All HTTP is mocked via unittest.mock — no real network calls are made and no
real UltimatePOS credentials exist in this environment. Fixture shapes below
match a real UltimatePOS v5 instance's confirmed field shapes (verified via a
read-only, credentialed probe against a live instance) rather than the
generic API docs — several fields (contact id, business-location rows,
category linkage) differ from what a naive reading of the docs would
suggest, and the extractor is written against the real shapes.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.data_import.etl.adapters.ultimatepos_api import (
    UltimatePOSAPIExtractor,
    _extract_contact_id,
    _extract_pos_id,
    _parse_purchase_lines_from_html,
    _parse_qty,
    _parse_sell_lines_from_html,
    _parse_stock_adjustment_lines_from_html,
)
from src.data_import.etl.extractor import APIExtractor

CREDS = {"username": "trader", "password": "s3cret-pw"}


def _resp(body: str, status: int = 200):
    """Build a fake urllib response object usable as a context manager."""
    m = MagicMock()
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    m.status = status
    m.read.return_value = body.encode("utf-8")
    return m


LOGIN_HTML = '<html><input name="_token" value="csrf-abc"></html>'

PRODUCTS_JSON = json.dumps(
    {
        "data": [
            {
                "id": 10101,
                "product": "Ankara Fabric",
                "sku": "SKU-1",
                "barcode": "111222",
                "category": "Fabrics",
                "selling_price": "2,000.00",
                "max_price": "1,200.00",
                "is_inactive": 0,
                "not_for_selling": 0,
                "variations": [
                    {
                        "id": 501,
                        "name": "Red / M",
                        "sub_sku": "SKU-1-RM",
                        "sell_price_inc_tax": "2,100.00",
                        "default_purchase_price": "1,250.00",
                    }
                ],
            },
            {
                "id": 102,
                "product": "Lace Fabric",
                "sku": "SKU-2",
                "barcode": "",
                "category": "Fabrics",
                "selling_price": "3,000.00",
                "max_price": "1,800.00",
                "is_inactive": 1,
                "not_for_selling": 0,
            },
        ]
    }
)

# Real /contacts rows have no top-level "id" — only an "action" column with
# /contacts/{id} links. Both fixtures below intentionally omit "id" to
# exercise the real (action-HTML) extraction path, not the fallback.
CONTACTS_SUPPLIER_JSON = json.dumps(
    {
        "data": [
            {
                "name": "Acme Textiles",
                "email": "sales@acme.test",
                "mobile": "08011112222",
                "action": '<a href="https://pos.example.com/contacts/9/edit">Edit</a>',
            }
        ]
    }
)

CONTACTS_CUSTOMER_JSON = json.dumps(
    {
        "data": [
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "mobile": "08033334444",
                "action": '<a href="https://pos.example.com/contacts/21/edit">Edit</a>',
            }
        ]
    }
)

# Real /business-location rows are plain positional arrays, not keyed
# objects — confirmed live column order: Name, Location ID, Landmark, City,
# Zip Code, State, Country, Price Group, Invoice scheme, Invoice layout
# (POS), Invoice layout (sale), Action.
BUSINESS_LOCATIONS_JSON = json.dumps(
    {
        "data": [
            [
                "Lagos HQ",
                "LGA001",
                None,
                "Lagos",
                "100001",
                "Lagos",
                "Nigeria",
                None,
                "Default",
                "Default",
                "Default",
                '<a href="https://pos.example.com/business-location/1/edit">Edit</a>',
            ]
        ]
    }
)

SELLS_JSON = json.dumps(
    {
        "data": [
            {
                "id": 777,
                "invoice_no": "INV-001",
                "transaction_date": "2026-06-01 10:00:00",
                "payment_type": "cash",
                "business_location": "Lagos HQ",
                "contact_id": "CO0006",
            }
        ]
    }
)

SELL_RECEIPT_HTML = """
<table>
<tr><td>1</td><td>Ankara Fabric

10101
</td><td><span data-is_quantity="true">2.00</span></td>
<td><span data-currency_symbol="true">2000.0000</span></td>
<td>0</td><td>0</td><td>0</td>
<td><span data-currency_symbol="true">4000.0000</span></td></tr>
</table>
"""

PURCHASES_JSON = json.dumps(
    {
        "data": [
            {
                "id": 555,
                "ref_no": "PO2026/0001",
                "transaction_date": "26-06-2025 12:08",
                "name": "Acme Textiles",
                "location_name": "Lagos HQ",
            }
        ]
    }
)

PURCHASE_PRINT_JSON = json.dumps(
    {
        "receipt": {
            "html_content": """
            <table>
            <tr><td>1</td><td>Ankara Fabric</td><td>SKU-1</td>
            <td><span data-is_quantity="true">10.00</span> Pieces</td>
            <td>1200.0000</td><td>0.00</td><td>1200.0000</td>
            <td>12000.0000</td><td>0</td><td>1200.0000</td><td>12000.0000</td></tr>
            </table>
            """
        }
    }
)

EXPENSE_CATEGORIES_JSON = json.dumps(
    {"data": [{"id": 3, "name": "Rent", "description": "Monthly shop rent"}]}
)

EXPENSES_JSON = json.dumps(
    {
        "data": [
            {
                "id": 88,
                "expense_category_id": 3,
                "ref_no": "EXP-001",
                "amount": "150,000.00",
                "expense_date": "2026-01-05",
                "payment_method": "cash",
                "note": "January rent",
            }
        ]
    }
)

STOCK_ADJUSTMENTS_JSON = json.dumps(
    {
        "data": [
            {
                "id": 2602569,
                "ref_no": "SA2026/0001",
                "transaction_date": "2026-01-10 09:00:00",
                "adjustment_type": "Normal",
                "additional_notes": "Wasn't delivered by Shipping Agent (AY)",
            }
        ]
    }
)

STOCK_ADJUSTMENT_DETAIL_HTML = """
<table>
<tr class="bg-green"><th>Product</th><th>Quantity</th><th>Unit Price</th><th>Subtotal</th></tr>
<tr><td>Ankara Fabric (10101)</td><td>92.0</td><td>16,979.00</td><td>1,562,068.00</td></tr>
</table>
"""


def _get_side_effect(url: str, headers=None, **kwargs):
    if url.endswith("/login"):
        return _resp(LOGIN_HTML)
    if url.endswith("/dashboard"):
        return _resp("<html>Welcome back, trader</html>")
    if "/products" in url:
        return _resp(PRODUCTS_JSON)
    if "type=supplier" in url:
        return _resp(CONTACTS_SUPPLIER_JSON)
    if "type=customer" in url:
        return _resp(CONTACTS_CUSTOMER_JSON)
    if "/business-location" in url:
        return _resp(BUSINESS_LOCATIONS_JSON)
    if "/purchases/print/555" in url:
        return _resp(PURCHASE_PRINT_JSON)
    if "/purchases" in url:
        return _resp(PURCHASES_JSON)
    if "/expense-categories" in url:
        return _resp(EXPENSE_CATEGORIES_JSON)
    if "/expenses" in url:
        return _resp(EXPENSES_JSON)
    if "/stock-adjustments/2602569" in url:
        return _resp(STOCK_ADJUSTMENT_DETAIL_HTML)
    if "/stock-adjustments" in url:
        return _resp(STOCK_ADJUSTMENTS_JSON)
    if "/sells" in url and "sells/" not in url:
        return _resp(SELLS_JSON)
    if "/sells/777" in url:
        return _resp(SELL_RECEIPT_HTML)
    raise AssertionError(f"Unexpected GET {url}")


class _FakeOpener:
    """Stand-in for urllib.request.build_opener(...) that records requests."""

    def __init__(self):
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        url = req.full_url
        headers = {k.lower(): v for k, v in req.header_items()}
        if req.get_method() == "POST" and url.endswith("/login"):
            return _resp("home dashboard redirect", status=200)
        return _get_side_effect(url, headers=headers)


@pytest.fixture
def fake_opener():
    return _FakeOpener()


@pytest.fixture(autouse=True)
def _patch_build_opener(fake_opener):
    with patch(
        "src.data_import.etl.adapters.ultimatepos_api.build_opener",
        return_value=fake_opener,
    ):
        yield fake_opener


class TestInterfaceCompliance:
    def test_is_an_api_extractor(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        assert isinstance(extractor, APIExtractor)

    def test_rejects_non_https_base_url(self):
        with pytest.raises(ValueError):
            UltimatePOSAPIExtractor("http://pos.example.com", CREDS)


class TestExtract:
    @pytest.mark.asyncio
    async def test_extract_returns_all_target_entities_in_modishlog_shape(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        result = await extractor.extract()

        assert set(result.keys()) >= {
            "product_categories",
            "products",
            "product_variants",
            "suppliers",
            "customers",
            "business_locations",
            "sales",
            "purchase_orders",
            "expense_categories",
            "expenses",
            "stock_adjustments",
        }

        products = result["products"]
        active_skus = {p["sku"] for p in products}
        assert "SKU-1" in active_skus
        # inactive product excluded
        assert "SKU-2" not in active_skus

        product = next(p for p in products if p["sku"] == "SKU-1")
        assert product["source_id"] == "10101"
        assert product["name"] == "Ankara Fabric"
        assert product["unit_cost"] == "1200.00"
        assert product["selling_price"] == "2000.00"
        assert product["currency"] == "NGN"
        assert product["category_source_id"] == "Fabrics"
        assert product["is_active"] == "true"

        variants = result["product_variants"]
        assert len(variants) == 1
        assert variants[0]["source_id"] == "501"
        assert variants[0]["product_source_id"] == "10101"
        assert variants[0]["price_override"] == "2100.00"
        assert variants[0]["cost_price_override"] == "1250.00"

        categories = result["product_categories"]
        assert categories[0]["source_id"] == "Fabrics"
        assert categories[0]["name"] == "Fabrics"

        suppliers = result["suppliers"]
        assert suppliers[0]["source_id"] == "9"
        assert suppliers[0]["name"] == "Acme Textiles"

        customers = result["customers"]
        assert customers[0]["source_id"] == "21"
        assert customers[0]["email"] == "jane@example.com"

        locations = result["business_locations"]
        assert locations[0]["source_id"] == "1"
        assert locations[0]["name"] == "Lagos HQ"
        assert locations[0]["location_code"] == "LGA001"

        sales = result["sales"]
        assert len(sales) == 1
        sale = sales[0]
        assert sale["product_source_id"] == "10101"
        assert sale["quantity"] == "2"
        assert sale["unit_price"] == "2000.0000"
        assert sale["sale_date"] == "2026-06-01"
        assert sale["currency"] == "NGN"
        assert sale["channel"] == "retail"
        assert sale["payment_method"] == "cash"
        assert sale["location_name"] == "Lagos HQ"
        # contact_id is a display code (e.g. "CO0006"), not a resolvable
        # customer numeric id — left unresolved, not guessed.
        assert sale["customer_source_id"] == ""

        purchase_orders = result["purchase_orders"]
        assert len(purchase_orders) == 1
        po = purchase_orders[0]
        assert po["source_id"] == "PO2026/0001"
        assert po["supplier_source_id"] == "9"
        assert po["supplier_name"] == "Acme Textiles"
        assert po["product_source_id"] == "10101"
        assert po["quantity"] == "10"
        assert po["currency"] == "USD"
        assert po["order_date"] == "2025-06-26"
        # 1200 NGN / 1600 fallback rate = 0.75 USD
        assert po["unit_cost"] == "0.750000"
        assert po["fx_rate"] == "1600"

        expense_categories = result["expense_categories"]
        assert expense_categories[0]["source_id"] == "3"
        assert expense_categories[0]["name"] == "Rent"

        expenses = result["expenses"]
        assert len(expenses) == 1
        exp = expenses[0]
        assert exp["category_source_id"] == "3"
        assert exp["ref_no"] == "EXP-001"
        assert exp["amount"] == "150000.00"
        assert exp["expense_date"] == "2026-01-05"
        assert exp["payment_method"] == "cash"
        assert exp["note"] == "January rent"

        stock_adjustments = result["stock_adjustments"]
        assert len(stock_adjustments) == 1
        adj = stock_adjustments[0]
        assert adj["source_id"] == "SA2026/0001"
        assert adj["product_source_id"] == "10101"
        # "Normal" is a loss/write-off category, not an addition — the
        # extractor infers a negative sign since UltimatePOS's Quantity
        # cell itself carries none.
        assert adj["quantity_change"] == "-92"
        assert adj["adjustment_type"] == "Normal"
        assert adj["reason"] == "Wasn't delivered by Shipping Agent (AY)"
        assert adj["adjustment_date"] == "2026-01-10"

    @pytest.mark.asyncio
    async def test_extract_never_logs_credentials(self, capsys):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        await extractor.extract()
        captured = capsys.readouterr()
        assert CREDS["password"] not in captured.out
        assert CREDS["password"] not in captured.err
        assert CREDS["username"] not in captured.out
        assert CREDS["username"] not in captured.err

    @pytest.mark.asyncio
    async def test_extract_raises_when_login_fails(self, fake_opener):
        class _FailingOpener:
            def open(self, req, timeout=None):
                if req.get_method() == "POST":
                    raise OSError("connection refused")
                raise AssertionError("should not reach GET after failed login")

        with patch(
            "src.data_import.etl.adapters.ultimatepos_api.build_opener",
            return_value=_FailingOpener(),
        ):
            extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
            with pytest.raises(Exception):
                await extractor.extract()

    @pytest.mark.asyncio
    async def test_extract_raises_when_missing_credentials(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", {})
        with pytest.raises(Exception):
            await extractor.extract()

    @pytest.mark.asyncio
    async def test_extract_raises_when_post_login_probe_still_shows_login_form(self):
        """The '\"home\" in body' success heuristic can false-positive (e.g.
        shared layout markup containing the word 'home'), so login() also
        probes an authenticated page and fails loudly if it's still the
        login form — this must not silently proceed unauthenticated."""

        class _StaleSessionOpener:
            def open(self, req, timeout=None):
                url = req.full_url
                if req.get_method() == "POST" and url.endswith("/login"):
                    # Body contains "home" (e.g. a nav link) despite bad creds.
                    return _resp("<a href='/home'>Home</a> Invalid credentials", status=200)
                if url.endswith("/login"):
                    return _resp(LOGIN_HTML)
                if url.endswith("/dashboard"):
                    return _resp('<html><form action="/login"><input name="_token" value="csrf-abc"></form></html>')
                raise AssertionError(f"Unexpected GET {url}")

        with patch(
            "src.data_import.etl.adapters.ultimatepos_api.build_opener",
            return_value=_StaleSessionOpener(),
        ):
            extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
            with pytest.raises(Exception):
                await extractor.extract()


class TestMapProductsZeroValueHandling:
    def test_zero_price_override_is_preserved_not_blanked(self):
        """Decimal('0') is falsy in Python — a naive `if price_override else ''`
        check would collapse a genuine free/zero-priced variant override into
        an empty string indistinguishable from 'no override'."""
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw_products = [
            {
                "id": 10101,
                "product": "Promo Bundle",
                "sku": "SKU-9",
                "selling_price": "1000",
                "max_price": "500",
                "is_inactive": 0,
                "not_for_selling": 0,
                "variations": [
                    {"id": 900, "name": "Free Sample", "sell_price_inc_tax": "0", "default_purchase_price": "0"}
                ],
            }
        ]
        _products, variants, _pos_map, _name_map = extractor._map_products(raw_products, {})
        assert variants[0]["price_override"] == "0"
        assert variants[0]["cost_price_override"] == "0"

    def test_uncategorized_product_gets_blank_category_source_id(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw_products = [
            {
                "id": 10101,
                "product": "Widget",
                "sku": "SKU-9",
                "selling_price": "100",
                "max_price": "50",
                "category": "",
                "is_inactive": 0,
                "not_for_selling": 0,
            }
        ]
        products, _variants, _pos_map, _name_map = extractor._map_products(raw_products, {})
        assert products[0]["category_source_id"] == ""


class TestMapCategories:
    def test_derives_distinct_categories_from_products_not_a_separate_endpoint(self):
        """No standalone /categories endpoint exists on the real API — this
        must never call one; category names live only on product rows."""
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw_products = [
            {"id": 1, "category": "Boards"},
            {"id": 2, "category": "Boards"},
            {"id": 3, "category": "Doors"},
            {"id": 4, "category": ""},
        ]
        categories, name_to_source = extractor._map_categories(raw_products)
        names = {c["name"] for c in categories}
        assert names == {"Boards", "Doors"}
        assert name_to_source["Boards"] == "Boards"

    def test_products_resolve_category_source_id_via_derived_map(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw_products = [
            {
                "id": 1,
                "product": "Board A",
                "sku": "B-1",
                "selling_price": "100",
                "max_price": "50",
                "category": "Boards",
                "is_inactive": 0,
                "not_for_selling": 0,
            }
        ]
        _categories, name_to_source = extractor._map_categories(raw_products)
        products, _v, _p, _n = extractor._map_products(raw_products, name_to_source)
        assert products[0]["category_source_id"] == "Boards"


class TestExtractContactId:
    def test_prefers_direct_id_field_when_present(self):
        assert _extract_contact_id({"id": 42}) == "42"

    def test_falls_back_to_action_html_link_when_no_id_field(self):
        """Confirmed real shape: /contacts rows have no top-level id."""
        contact = {
            "name": "Acme",
            "action": '<a href="https://pos.example.com/contacts/56902/edit">Edit</a>',
        }
        assert _extract_contact_id(contact) == "56902"

    def test_no_id_and_no_action_link_returns_none(self):
        assert _extract_contact_id({"name": "Acme"}) is None


class TestMapLocationsPositionalArray:
    def test_parses_confirmed_real_column_order(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw_locations = [
            [
                "Modish Standard Limited",
                "BL0001",
                "Challenge",
                "Mushin",
                "102215",
                "Lagos",
                "Nigeria",
                None,
                "Default",
                "Default",
                "Default",
                '<a href="https://pos.example.com/business-location/928/edit">Edit</a>',
            ]
        ]
        locations = extractor._map_locations(raw_locations)
        assert locations == [
            {
                "source_id": "928",
                "name": "Modish Standard Limited",
                "location_code": "BL0001",
            }
        ]

    def test_still_accepts_keyed_object_shape_for_forward_compat(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        locations = extractor._map_locations(
            [{"id": 1, "name": "Lagos HQ", "location_id": "LGA001"}]
        )
        assert locations == [
            {"source_id": "1", "name": "Lagos HQ", "location_code": "LGA001"}
        ]

    def test_row_too_short_is_skipped_not_crashed(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        assert extractor._map_locations([["Too short"]]) == []


class TestParseQty:
    def test_fractional_quantity_rounds_up_to_at_least_one(self):
        """Matches pos_migrate.py's ceil/min-1 behavior — a length-based good
        like 0.5m of edge tape must not truncate to 0 and get dropped."""
        assert _parse_qty("0.5") == 1

    def test_whole_fractional_quantity_rounds_up(self):
        assert _parse_qty("2.1") == 3

    def test_zero_or_negative_quantity_is_zero(self):
        assert _parse_qty("0") == 0
        assert _parse_qty("-1") == 0

    def test_unparseable_quantity_is_zero(self):
        assert _parse_qty("not-a-number") == 0


class TestExtractPosId:
    def test_id_zero_is_not_treated_as_missing(self):
        assert _extract_pos_id({"id": 0}, "sells") == "0"

    def test_missing_id_falls_back_to_dt_row_id(self):
        assert _extract_pos_id({"DT_RowId": "row_42"}, "sells") == "42"

    def test_no_id_anywhere_returns_none(self):
        assert _extract_pos_id({}, "sells") is None


class TestParseSellLinesFromHtml:
    def test_falls_back_to_name_match_when_trailing_id_missing(self):
        html = """
        <table><tr><td>1</td><td>Ankara Fabric</td>
        <td><span data-is_quantity="true">1.00</span></td>
        <td><span data-currency_symbol="true">500.0000</span></td>
        <td>0</td><td>0</td><td>0</td>
        <td><span data-currency_symbol="true">500.0000</span></td></tr></table>
        """
        lines = _parse_sell_lines_from_html(html, {}, {"ankara fabric": "10101"})
        assert len(lines) == 1
        assert lines[0]["product_source_id"] == "10101"

    def test_unmatched_row_is_skipped(self):
        html = """
        <table><tr><td>1</td><td>Unknown Item</td>
        <td><span data-is_quantity="true">1.00</span></td>
        <td><span data-currency_symbol="true">500.0000</span></td>
        <td>0</td><td>0</td><td>0</td>
        <td><span data-currency_symbol="true">500.0000</span></td></tr></table>
        """
        lines = _parse_sell_lines_from_html(html, {}, {})
        assert lines == []

    def test_captures_authoritative_subtotal_over_unit_price_times_qty(self):
        """The subtotal cell reflects post-discount/tax totals — must be used
        over a naive unit_price * quantity recomputation when present."""
        html = """
        <table><tr><td>1</td><td>Ankara Fabric

        10101
        </td><td><span data-is_quantity="true">2.00</span></td>
        <td><span data-currency_symbol="true">500.0000</span></td>
        <td>0</td><td>0</td><td>0</td>
        <td><span data-currency_symbol="true">900.0000</span></td></tr></table>
        """
        lines = _parse_sell_lines_from_html(html, {"10101": "10101"})
        assert lines[0]["line_total"] == Decimal("900.0000")


class TestParsePurchaseLinesFromHtml:
    def test_matches_by_sku_and_parses_ngn_unit_cost(self):
        html = """
        <table>
        <tr><td>1</td><td>Ankara Fabric</td><td>SKU-1</td>
        <td><span data-is_quantity="true">10.00</span> Pieces</td>
        <td>1200.0000</td><td>0.00</td><td>1200.0000</td>
        <td>12000.0000</td><td>0</td><td>1200.0000</td><td>12000.0000</td></tr>
        </table>
        """
        lines = _parse_purchase_lines_from_html(html, {"SKU-1": "10101"})
        assert lines == [
            {"product_source_id": "10101", "quantity": 10, "unit_cost_ngn": Decimal("1200.0000")}
        ]

    def test_unmatched_sku_is_skipped(self):
        html = """
        <table>
        <tr><td>1</td><td>Unknown</td><td>SKU-X</td>
        <td><span data-is_quantity="true">1.00</span></td>
        <td>100.0000</td><td>0</td><td>100</td><td>100</td><td>0</td><td>100</td><td>100</td></tr>
        </table>
        """
        assert _parse_purchase_lines_from_html(html, {}) == []

    def test_zero_quantity_line_is_skipped(self):
        html = """
        <table>
        <tr><td>1</td><td>Item</td><td>SKU-1</td>
        <td><span data-is_quantity="true">0.00</span></td>
        <td>100.0000</td><td>0</td><td>100</td><td>100</td><td>0</td><td>100</td><td>100</td></tr>
        </table>
        """
        assert _parse_purchase_lines_from_html(html, {"SKU-1": "10101"}) == []


class TestMapPurchaseOrders:
    @pytest.mark.asyncio
    async def test_groups_lines_and_resolves_supplier_by_name(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_products = [{"id": 10101, "sku": "SKU-1"}]
        raw_suppliers = [
            {
                "name": "Acme Textiles",
                "action": '<a href="https://pos.example.com/contacts/9/edit">Edit</a>',
            }
        ]
        raw_purchases = [
            {
                "id": 555,
                "ref_no": "PO2026/0001",
                "transaction_date": "26-06-2025 12:08",
                "name": "Acme Textiles",
            }
        ]
        rows = await extractor._map_purchase_orders(
            client, raw_purchases, raw_products, raw_suppliers
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["source_id"] == "PO2026/0001"
        assert row["supplier_source_id"] == "9"
        assert row["product_source_id"] == "10101"
        assert row["quantity"] == "10"
        assert row["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_purchase_line_for_discontinued_product_still_resolves(self):
        """Regression: sku_to_source must be built from ALL products, not
        just the active/for-sale subset _map_products() returns — a
        historical PO can reference a since-discontinued product and that
        line must not silently vanish."""
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_products = [
            {"id": 10101, "sku": "SKU-1", "is_inactive": 1, "not_for_selling": 1}
        ]
        raw_purchases = [
            {
                "id": 555,
                "ref_no": "PO2026/0001",
                "transaction_date": "26-06-2025 12:08",
                "name": "Acme Textiles",
            }
        ]
        rows = await extractor._map_purchase_orders(client, raw_purchases, raw_products, [])
        assert len(rows) == 1
        assert rows[0]["product_source_id"] == "10101"

    @pytest.mark.asyncio
    async def test_unmatched_supplier_name_leaves_supplier_source_id_blank(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_products = [{"id": 10101, "sku": "SKU-1"}]
        raw_purchases = [
            {
                "id": 555,
                "ref_no": "PO2026/0001",
                "transaction_date": "26-06-2025 12:08",
                "name": "Unknown Supplier",
            }
        ]
        rows = await extractor._map_purchase_orders(client, raw_purchases, raw_products, [])
        assert rows[0]["supplier_source_id"] == ""
        assert rows[0]["supplier_name"] == "Unknown Supplier"

    @pytest.mark.asyncio
    async def test_empty_print_html_produces_no_rows(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_purchases = [{"id": 9999, "ref_no": "PO-EMPTY", "transaction_date": "01-01-2026"}]
        rows = await extractor._map_purchase_orders(client, raw_purchases, [], [])
        assert rows == []


class TestParseStockAdjustmentLinesFromHtml:
    def test_matches_by_trailing_parenthetical_pos_id(self):
        html = """
        <table>
        <tr class="bg-green"><th>Product</th><th>Quantity</th><th>Unit Price</th><th>Subtotal</th></tr>
        <tr><td>Off White MDF UV (301406)</td><td>92.0</td><td>16,979.00</td><td>1,562,068.00</td></tr>
        </table>
        """
        lines = _parse_stock_adjustment_lines_from_html(html, {"301406": "301406"})
        assert lines == [{"product_source_id": "301406", "quantity": 92}]

    def test_unresolvable_product_id_is_skipped(self):
        html = "<table><tr><td>Unknown (999)</td><td>5</td><td>10</td><td>50</td></tr></table>"
        assert _parse_stock_adjustment_lines_from_html(html, {}) == []

    def test_product_cell_without_parenthetical_id_is_skipped(self):
        html = "<table><tr><td>Off White MDF UV</td><td>5</td><td>10</td><td>50</td></tr></table>"
        assert _parse_stock_adjustment_lines_from_html(html, {"301406": "301406"}) == []

    def test_zero_quantity_line_is_skipped(self):
        html = "<table><tr><td>Item (301406)</td><td>0</td><td>10</td><td>0</td></tr></table>"
        assert _parse_stock_adjustment_lines_from_html(html, {"301406": "301406"}) == []

    def test_activity_log_rows_without_matching_id_are_ignored(self):
        """The same detail page also has an activity-log table (Date/Action/By/
        Note) below the line-item table — must not be misread as products."""
        html = """
        <table>
        <tr><td>Item (301406)</td><td>92.0</td><td>16,979.00</td><td>1,562,068.00</td></tr>
        </table>
        <table>
        <tr><td>2026-01-10</td><td>Created</td><td>Admin</td><td>Initial adjustment</td></tr>
        </table>
        """
        lines = _parse_stock_adjustment_lines_from_html(html, {"301406": "301406"})
        assert lines == [{"product_source_id": "301406", "quantity": 92}]


class TestMapStockAdjustments:
    @pytest.mark.asyncio
    async def test_maps_header_and_html_line_together(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_adjustments = [
            {
                "id": 2602569,
                "ref_no": "SA2026/0001",
                "transaction_date": "2026-01-10 09:00:00",
                "adjustment_type": "Normal",
                "additional_notes": "Wasn't delivered by Shipping Agent (AY)",
            }
        ]
        rows = await extractor._map_stock_adjustments(
            client, raw_adjustments, {"10101": "10101"}
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["source_id"] == "SA2026/0001"
        assert row["product_source_id"] == "10101"
        assert row["quantity_change"] == "-92"
        assert row["adjustment_type"] == "Normal"
        assert row["reason"] == "Wasn't delivered by Shipping Agent (AY)"
        assert row["adjustment_date"] == "2026-01-10"

    @pytest.mark.asyncio
    async def test_opening_stock_type_is_a_positive_addition(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_adjustments = [
            {
                "id": 2602569,
                "ref_no": "SA2026/0002",
                "transaction_date": "2026-01-10",
                "adjustment_type": "Opening Stock",
            }
        ]
        rows = await extractor._map_stock_adjustments(
            client, raw_adjustments, {"10101": "10101"}
        )
        assert rows[0]["quantity_change"] == "92"

    @pytest.mark.asyncio
    async def test_missing_ref_no_falls_back_to_pos_id_source_id(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_adjustments = [{"id": 2602569, "transaction_date": "2026-01-10"}]
        rows = await extractor._map_stock_adjustments(
            client, raw_adjustments, {"10101": "10101"}
        )
        assert rows[0]["source_id"] == "POS-ADJ-2602569"

    @pytest.mark.asyncio
    async def test_no_pos_id_on_header_is_skipped(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        rows = await extractor._map_stock_adjustments(client, [{"foo": "bar"}], {})
        assert rows == []

    @pytest.mark.asyncio
    async def test_empty_detail_html_produces_no_rows(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        client = extractor._build_client()
        raw_adjustments = [
            {"id": 9999, "ref_no": "SA-EMPTY", "transaction_date": "2026-01-01"}
        ]
        rows = await extractor._map_stock_adjustments(client, raw_adjustments, {})
        assert rows == []


class TestMapExpenseCategories:
    def test_maps_id_name_description(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw = [{"id": 3, "name": "Rent", "description": "Monthly shop rent"}]
        categories, id_to_source = extractor._map_expense_categories(raw)
        assert categories == [
            {"source_id": "3", "name": "Rent", "description": "Monthly shop rent"}
        ]
        assert id_to_source == {"3": "3"}

    def test_row_with_no_id_is_skipped(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        categories, _map = extractor._map_expense_categories([{"name": "No ID"}])
        assert categories == []


class TestMapExpenses:
    def test_resolves_category_and_parses_fields(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw = [
            {
                "id": 88,
                "expense_category_id": 3,
                "ref_no": "EXP-001",
                "amount": "150,000.00",
                "expense_date": "2026-01-05",
                "payment_method": "cash",
                "note": "January rent",
            }
        ]
        rows = extractor._map_expenses(raw, {"3": "3"})
        assert len(rows) == 1
        row = rows[0]
        assert row["source_id"] == "88"
        assert row["category_source_id"] == "3"
        assert row["ref_no"] == "EXP-001"
        assert row["amount"] == "150000.00"
        assert row["expense_date"] == "2026-01-05"
        assert row["payment_method"] == "cash"
        assert row["note"] == "January rent"

    def test_unresolvable_category_leaves_category_source_id_blank(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw = [{"id": 1, "expense_category_id": 999, "amount": "100", "expense_date": "2026-01-01"}]
        rows = extractor._map_expenses(raw, {})
        assert rows[0]["category_source_id"] == ""

    def test_row_with_no_parseable_date_is_skipped(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw = [{"id": 1, "amount": "100", "expense_date": ""}]
        assert extractor._map_expenses(raw, {}) == []

    def test_falls_back_to_final_total_and_transaction_date_and_additional_notes(self):
        """pos_migrate.py's proven expense mapping accepts either field name
        pair — mirrored here since the live business this was built against
        had zero real expense records to confirm which one this API version
        actually uses."""
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw = [
            {
                "id": 1,
                "final_total": "5000",
                "transaction_date": "2026-02-01",
                "additional_notes": "Fallback note",
            }
        ]
        rows = extractor._map_expenses(raw, {})
        assert rows[0]["amount"] == "5000"
        assert rows[0]["expense_date"] == "2026-02-01"
        assert rows[0]["note"] == "Fallback note"


class TestTestConnection:
    @pytest.mark.asyncio
    async def test_returns_counts_and_date_range(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        result = await extractor.test_connection()

        assert "counts" in result
        assert "date_range" in result
        assert result["counts"]["products"] == 1  # only active product counted
        assert result["counts"]["product_categories"] == 1  # "Fabrics", deduped
        assert result["counts"]["customers"] == 1
        assert result["counts"]["suppliers"] == 1
        assert result["date_range"]["earliest"] == "2026-06-01"
        assert result["date_range"]["latest"] == "2026-06-01"

    @pytest.mark.asyncio
    async def test_test_connection_never_logs_credentials(self, capsys):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        await extractor.test_connection()
        captured = capsys.readouterr()
        assert CREDS["password"] not in captured.out
        assert CREDS["password"] not in captured.err

    @pytest.mark.asyncio
    async def test_test_connection_raises_on_auth_failure(self):
        class _FailingOpener:
            def open(self, req, timeout=None):
                raise OSError("connection refused")

        with patch(
            "src.data_import.etl.adapters.ultimatepos_api.build_opener",
            return_value=_FailingOpener(),
        ):
            extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
            with pytest.raises(Exception):
                await extractor.test_connection()
