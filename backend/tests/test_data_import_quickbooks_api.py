"""Tests for the QuickBooks Online API extractor (task 162 — QBO adapter).

All HTTP calls are mocked via httpx.MockTransport — no real network access,
no real QuickBooks credentials are used anywhere in this file.
"""

from decimal import Decimal

import httpx
import pytest

from src.data_import.etl.adapters.quickbooks_api import QuickBooksAPIExtractor

BASE_URL = "https://sandbox-quickbooks.api.intuit.com/v3/company/123456789"
CREDENTIALS = {"access_token": "fake-token-do-not-log", "realm_id": "123456789"}


def _query_response(entities: list[dict], entity_key: str, start_position: int = 1, max_results: int | None = None):
    body = {"QueryResponse": {}, "time": "2026-07-10T00:00:00.000Z"}
    if entities:
        body["QueryResponse"][entity_key] = entities
    body["QueryResponse"]["startPosition"] = start_position
    body["QueryResponse"]["maxResults"] = max_results if max_results is not None else len(entities)
    return body


def _item(id_="1", name="Ankara Fabric", sku="SKU-1", unit_price="2000.00", cost="1200.00", active=True, category_id=None):
    item = {
        "Id": id_,
        "Name": name,
        "Sku": sku,
        "UnitPrice": unit_price,
        "PurchaseCost": cost,
        "Active": active,
        "Type": "Inventory",
    }
    if category_id:
        item["ParentRef"] = {"value": category_id}
    return item


def _category_item(id_="10", name="Fabrics", parent_id=None):
    item = {"Id": id_, "Name": name, "Active": True, "Type": "Category"}
    if parent_id:
        item["ParentRef"] = {"value": parent_id}
    return item


def _customer(id_="1", name="Jane Doe", email="jane@example.com", phone="08012345678"):
    c = {"Id": id_, "DisplayName": name}
    if email:
        c["PrimaryEmailAddr"] = {"Address": email}
    if phone:
        c["PrimaryPhone"] = {"FreeFormNumber": phone}
    return c


def _vendor(id_="1", name="Fabric Supplier Co", email="supplier@example.com", phone="08099999999", print_on_check_name=None):
    v = {"Id": id_, "DisplayName": name}
    if email:
        v["PrimaryEmailAddr"] = {"Address": email}
    if phone:
        v["PrimaryPhone"] = {"FreeFormNumber": phone}
    if print_on_check_name:
        v["PrintOnCheckName"] = print_on_check_name
    return v


def _invoice(id_="1", txn_date="2026-01-15", customer_id="1", customer_name="Jane Doe", item_id="1", item_name="Ankara Fabric", qty="2", unit_price="2000.00"):
    return {
        "Id": id_,
        "TxnDate": txn_date,
        "CurrencyRef": {"value": "NGN"},
        "CustomerRef": {"value": customer_id, "name": customer_name},
        "Line": [
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": str(Decimal(qty) * Decimal(unit_price)),
                "SalesItemLineDetail": {
                    "ItemRef": {"value": item_id, "name": item_name},
                    "Qty": qty,
                    "UnitPrice": unit_price,
                },
            }
        ],
    }


def _make_transport(responses: dict[str, list[dict]]):
    """responses: entity name in the SQL query (e.g. 'Item') -> list of query
    response bodies to return in order, one per call to that entity (paginates)."""
    call_counts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        for entity_name, bodies in responses.items():
            if f"FROM {entity_name}" in query:
                idx = call_counts.get(entity_name, 0)
                call_counts[entity_name] = idx + 1
                if idx >= len(bodies):
                    return httpx.Response(200, json=_query_response([], entity_name))
                return httpx.Response(200, json=bodies[idx])
        return httpx.Response(404, json={"Fault": {"Error": [{"Message": "Unknown query"}]}})

    return httpx.MockTransport(handler), call_counts


def _extractor_with_transport(responses: dict[str, list[dict]]):
    transport, call_counts = _make_transport(responses)
    extractor = QuickBooksAPIExtractor(BASE_URL, dict(CREDENTIALS))
    extractor._transport = transport  # test hook — see implementation
    return extractor, call_counts


class TestQuickBooksExtractProducts:
    @pytest.mark.asyncio
    async def test_extracts_items_as_products(self):
        responses = {
            "Item": [_query_response([_item()], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)

        result = await extractor.extract()

        assert len(result["products"]) == 1
        product = result["products"][0]
        assert product["source_id"] == "1"
        assert product["name"] == "Ankara Fabric"
        assert product["sku"] == "SKU-1"
        assert product["selling_price"] == "2000.00"
        assert product["unit_cost"] == "1200.00"
        assert product["is_active"] == "true"
        assert product["currency"] == "NGN"

    @pytest.mark.asyncio
    async def test_inactive_item_maps_is_active_false(self):
        responses = {
            "Item": [_query_response([_item(active=False)], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert result["products"][0]["is_active"] == "false"

    @pytest.mark.asyncio
    async def test_paginates_beyond_first_page(self):
        page1 = [_item(id_=str(i)) for i in range(1, 1001)]
        page2 = [_item(id_="1001")]
        responses = {
            "Item": [
                _query_response(page1, "Item", start_position=1, max_results=1000),
                _query_response(page2, "Item", start_position=1001, max_results=1),
            ],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, call_counts = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert len(result["products"]) == 1001
        assert call_counts["Item"] == 2


class TestQuickBooksExtractCategories:
    @pytest.mark.asyncio
    async def test_category_items_mapped_to_product_categories(self):
        responses = {
            "Item": [_query_response([_category_item(), _item(category_id="10")], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()

        assert len(result["product_categories"]) == 1
        assert result["product_categories"][0]["source_id"] == "10"
        assert result["product_categories"][0]["name"] == "Fabrics"

        assert len(result["products"]) == 1
        assert result["products"][0]["category_source_id"] == "10"


class TestQuickBooksExtractCustomers:
    @pytest.mark.asyncio
    async def test_extracts_customers(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([_customer()], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()

        assert len(result["customers"]) == 1
        customer = result["customers"][0]
        assert customer["source_id"] == "1"
        assert customer["name"] == "Jane Doe"
        assert customer["email"] == "jane@example.com"
        assert customer["contact_number"] == "08012345678"

    @pytest.mark.asyncio
    async def test_customer_without_email_has_empty_string(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([_customer(email=None)], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert result["customers"][0]["email"] == ""


class TestQuickBooksExtractSuppliers:
    @pytest.mark.asyncio
    async def test_extracts_vendors_as_suppliers(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([_vendor()], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()

        assert len(result["suppliers"]) == 1
        supplier = result["suppliers"][0]
        assert supplier["source_id"] == "1"
        assert supplier["name"] == "Fabric Supplier Co"
        assert supplier["email"] == "supplier@example.com"
        assert supplier["mobile"] == "08099999999"

    @pytest.mark.asyncio
    async def test_vendor_print_on_check_name_maps_to_contact_person(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([_vendor(print_on_check_name="John Adeyemi")], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert result["suppliers"][0]["contact_person"] == "John Adeyemi"

    @pytest.mark.asyncio
    async def test_vendor_without_print_on_check_name_has_empty_contact_person(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([_vendor()], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert result["suppliers"][0]["contact_person"] == ""


class TestQuickBooksExtractSales:
    @pytest.mark.asyncio
    async def test_extracts_invoice_lines_as_sales(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([_invoice()], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()

        assert len(result["sales"]) == 1
        sale = result["sales"][0]
        assert sale["product_source_id"] == "1"
        assert sale["customer_source_id"] == "1"
        assert sale["quantity"] == "2"
        assert sale["unit_price"] == "2000.00"
        assert sale["sale_date"] == "2026-01-15"
        assert sale["currency"] == "NGN"
        assert sale["channel"] == "online"

    @pytest.mark.asyncio
    async def test_invoice_with_multiple_lines_produces_multiple_sales(self):
        invoice = _invoice()
        invoice["Line"].append(
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": "500.00",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": "2", "name": "Lace Fabric"},
                    "Qty": "1",
                    "UnitPrice": "500.00",
                },
            }
        )
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([invoice], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert len(result["sales"]) == 2
        assert {s["product_source_id"] for s in result["sales"]} == {"1", "2"}

    @pytest.mark.asyncio
    async def test_line_missing_unit_price_falls_back_to_amount_over_qty(self):
        """QBO commonly omits SalesItemLineDetail.UnitPrice on lines entered as
        a flat amount — Amount is always present, so unit_price must be
        derived from Amount / Qty rather than silently defaulting to 0."""
        invoice = _invoice()
        invoice["Line"] = [
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": "5000.00",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": "1", "name": "Ankara Fabric"},
                    "Qty": "2",
                    # UnitPrice intentionally omitted.
                },
            }
        ]
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([invoice], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert result["sales"][0]["unit_price"] == "2500.00"

    @pytest.mark.asyncio
    async def test_invoice_line_missing_item_ref_is_skipped(self):
        invoice = _invoice()
        # A subtotal/discount line has no SalesItemLineDetail.ItemRef
        invoice["Line"].append(
            {"DetailType": "SubTotalLineDetail", "Amount": "2000.00", "SubTotalLineDetail": {}}
        )
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([invoice], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert len(result["sales"]) == 1


class TestQuickBooksProductVariantsEmpty:
    @pytest.mark.asyncio
    async def test_product_variants_key_present_and_empty(self):
        responses = {
            "Item": [_query_response([_item()], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.extract()
        assert result["product_variants"] == []


class TestQuickBooksAuth:
    @pytest.mark.asyncio
    async def test_sends_bearer_token_header(self):
        seen_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers["Authorization"] = request.headers.get("Authorization")
            seen_headers["Accept"] = request.headers.get("Accept")
            query = request.url.params.get("query", "")
            entity = "Item"
            for name in ("Item", "Customer", "Vendor", "Invoice"):
                if f"FROM {name}" in query:
                    entity = name
            return httpx.Response(200, json=_query_response([], entity))

        transport = httpx.MockTransport(handler)
        extractor = QuickBooksAPIExtractor(BASE_URL, dict(CREDENTIALS))
        extractor._transport = transport

        await extractor.extract()

        assert seen_headers["Authorization"] == "Bearer fake-token-do-not-log"
        assert seen_headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_sends_minorversion_so_sku_is_included_in_response(self):
        """QBO only includes the Sku field on Item responses at minorversion
        40+ — omitting this query param would silently blank every SKU."""
        seen_params = {}

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.params.get("query", "")
            entity = "Item"
            for name in ("Item", "Customer", "Vendor", "Invoice"):
                if f"FROM {name}" in query:
                    entity = name
            seen_params[entity] = request.url.params.get("minorversion")
            return httpx.Response(200, json=_query_response([], entity))

        transport = httpx.MockTransport(handler)
        extractor = QuickBooksAPIExtractor(BASE_URL, dict(CREDENTIALS))
        extractor._transport = transport

        await extractor.extract()

        assert seen_params["Item"] is not None
        assert int(seen_params["Item"]) >= 40

    @pytest.mark.asyncio
    async def test_missing_access_token_raises_without_calling_network(self):
        extractor = QuickBooksAPIExtractor(BASE_URL, {})

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("must not attempt network call without a token")

        extractor._transport = httpx.MockTransport(handler)

        with pytest.raises(Exception):
            await extractor.extract()

    @pytest.mark.asyncio
    async def test_http_error_does_not_leak_token_in_exception_message(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"Fault": {"Error": [{"Message": "Unauthorized"}]}})

        transport = httpx.MockTransport(handler)
        extractor = QuickBooksAPIExtractor(BASE_URL, dict(CREDENTIALS))
        extractor._transport = transport

        with pytest.raises(Exception) as exc_info:
            await extractor.extract()

        assert "fake-token-do-not-log" not in str(exc_info.value)


class TestQuickBooksTestConnection:
    @pytest.mark.asyncio
    async def test_returns_counts_and_date_range(self):
        responses = {
            "Item": [_query_response([_item()], "Item")],
            "Customer": [_query_response([_customer()], "Customer")],
            "Vendor": [_query_response([_vendor()], "Vendor")],
            "Invoice": [
                _query_response(
                    [
                        _invoice(id_="1", txn_date="2026-01-15"),
                        _invoice(id_="2", txn_date="2026-03-20"),
                    ],
                    "Invoice",
                )
            ],
        }
        extractor, _ = _extractor_with_transport(responses)

        result = await extractor.test_connection()

        assert result["counts"]["products"] == 1
        assert result["counts"]["customers"] == 1
        assert result["counts"]["suppliers"] == 1
        assert result["counts"]["sales"] == 2
        assert result["date_range"]["earliest"] == "2026-01-15"
        assert result["date_range"]["latest"] == "2026-03-20"

    @pytest.mark.asyncio
    async def test_no_invoices_gives_none_date_range(self):
        responses = {
            "Item": [_query_response([], "Item")],
            "Customer": [_query_response([], "Customer")],
            "Vendor": [_query_response([], "Vendor")],
            "Invoice": [_query_response([], "Invoice")],
        }
        extractor, _ = _extractor_with_transport(responses)
        result = await extractor.test_connection()
        assert result["counts"]["sales"] == 0
        assert result["date_range"]["earliest"] is None
        assert result["date_range"]["latest"] is None

    @pytest.mark.asyncio
    async def test_auth_failure_raises_without_leaking_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"Fault": {"Error": [{"Message": "Unauthorized"}]}})

        transport = httpx.MockTransport(handler)
        extractor = QuickBooksAPIExtractor(BASE_URL, dict(CREDENTIALS))
        extractor._transport = transport

        with pytest.raises(Exception) as exc_info:
            await extractor.test_connection()
        assert "fake-token-do-not-log" not in str(exc_info.value)
