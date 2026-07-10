"""Tests for the UltimatePOS live API extractor (task 162, Phase 1 work unit).

All HTTP is mocked via unittest.mock — no real network calls are made and no
real UltimatePOS credentials exist in this environment.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.data_import.etl.adapters.ultimatepos_api import (
    UltimatePOSAPIExtractor,
    _extract_pos_id,
    _parse_qty,
    _parse_sell_lines_from_html,
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
                "selling_price": "2,000.00",
                "max_price": "1,200.00",
                "category_id": 5,
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
                "selling_price": "3,000.00",
                "max_price": "1,800.00",
                "category_id": None,
                "is_inactive": 1,
                "not_for_selling": 0,
            },
        ]
    }
)

CATEGORIES_JSON = json.dumps(
    {"data": [{"id": 5, "name": "Fabrics", "description": "All fabrics", "parent_id": None}]}
)

CONTACTS_SUPPLIER_JSON = json.dumps(
    {
        "data": [
            {
                "id": 9,
                "name": "Acme Textiles",
                "email": "sales@acme.test",
                "mobile": "08011112222",
            }
        ]
    }
)

CONTACTS_CUSTOMER_JSON = json.dumps(
    {
        "data": [
            {
                "id": 21,
                "name": "Jane Doe",
                "email": "jane@example.com",
                "mobile": "08033334444",
            }
        ]
    }
)

BUSINESS_LOCATIONS_JSON = json.dumps(
    {"data": [{"id": 1, "name": "Lagos HQ", "location_id": "LGA001"}]}
)

SELLS_JSON = json.dumps(
    {
        "data": [
            {
                "id": 777,
                "invoice_no": "INV-001",
                "transaction_date": "2026-06-01 10:00:00",
                "payment_type": "cash",
                "location_id": 1,
                "contact_id": 21,
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


def _get_side_effect(url: str, headers=None, **kwargs):
    if url.endswith("/login"):
        return _resp(LOGIN_HTML)
    if url.endswith("/dashboard"):
        return _resp("<html>Welcome back, trader</html>")
    if "/products" in url:
        return _resp(PRODUCTS_JSON)
    if "/categories" in url:
        return _resp(CATEGORIES_JSON)
    if "type=supplier" in url:
        return _resp(CONTACTS_SUPPLIER_JSON)
    if "type=customer" in url:
        return _resp(CONTACTS_CUSTOMER_JSON)
    if "/business-locations" in url:
        return _resp(BUSINESS_LOCATIONS_JSON)
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
        assert product["category_source_id"] == "5"
        assert product["is_active"] == "true"

        variants = result["product_variants"]
        assert len(variants) == 1
        assert variants[0]["source_id"] == "501"
        assert variants[0]["product_source_id"] == "10101"
        assert variants[0]["price_override"] == "2100.00"
        assert variants[0]["cost_price_override"] == "1250.00"

        categories = result["product_categories"]
        assert categories[0]["source_id"] == "5"
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
        assert sale["customer_source_id"] == "21"

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
        _products, variants, _pos_map, _name_map = extractor._map_products(raw_products)
        assert variants[0]["price_override"] == "0"
        assert variants[0]["cost_price_override"] == "0"

    def test_category_id_zero_is_preserved_not_blanked(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        raw_products = [
            {
                "id": 10101,
                "product": "Widget",
                "sku": "SKU-9",
                "selling_price": "100",
                "max_price": "50",
                "category_id": 0,
                "is_inactive": 0,
                "not_for_selling": 0,
            }
        ]
        products, _variants, _pos_map, _name_map = extractor._map_products(raw_products)
        assert products[0]["category_source_id"] == "0"


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


class TestTestConnection:
    @pytest.mark.asyncio
    async def test_returns_counts_and_date_range(self):
        extractor = UltimatePOSAPIExtractor("https://pos.example.com", CREDS)
        result = await extractor.test_connection()

        assert "counts" in result
        assert "date_range" in result
        assert result["counts"]["products"] == 1  # only active product counted
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
