"""Tests for the Shopify Admin REST API extractor (task 162).

All HTTP calls are mocked via ``httpx.MockTransport`` wired in through a
``unittest.mock.patch`` of ``httpx.AsyncClient`` — the same pattern already
used for external API calls in ``tests/test_fx.py`` — so no real network
access and no real Shopify credentials are required, and production code
carries no test-only seams.
"""

from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest

from src.data_import.etl.adapters.shopify_api import ShopifyAPIExtractor

BASE_URL = "https://test-shop.myshopify.com/admin/api/2024-01"
CREDENTIALS = {"access_token": "shpat_supersecrettoken"}

SHOP_1 = {"currency": "USD"}


def _json_response(request: httpx.Request, payload: dict, link: str | None = None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if link:
        headers["Link"] = link
    return httpx.Response(200, json=payload, headers=headers, request=request)


@contextmanager
def _mocked_client(handler):
    """Patch ``httpx.AsyncClient`` in the adapter module so every client the
    adapter constructs is transparently backed by ``httpx.MockTransport``,
    without the adapter itself needing any test-only constructor hook.
    """
    real_async_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    with patch(
        "src.data_import.etl.adapters.shopify_api.httpx.AsyncClient",
        side_effect=_client_factory,
    ):
        yield


def _make_extractor() -> ShopifyAPIExtractor:
    return ShopifyAPIExtractor(BASE_URL, dict(CREDENTIALS))


def _default_shop_handler(handler):
    """Wrap a handler so shop.json is answered automatically unless the
    caller's handler already deals with it — keeps entity-focused tests
    from having to special-case the shop-currency lookup every time.
    """

    def wrapped(request: httpx.Request) -> httpx.Response:
        if "shop.json" in str(request.url):
            return _json_response(request, {"shop": SHOP_1})
        return handler(request)

    return wrapped


PRODUCT_1 = {
    "id": 111,
    "title": "Blue Shirt",
    "body_html": "<p>Nice shirt</p>",
    "product_type": "Shirts",
    "status": "active",
    "variants": [
        {
            "id": 1111,
            "product_id": 111,
            "title": "Small / Blue",
            "sku": "SHIRT-S-BLUE",
            "barcode": "012345",
            "price": "19.99",
            "option1": "Small",
            "option2": "Blue",
        },
        {
            "id": 1112,
            "product_id": 111,
            "title": "Large / Blue",
            "sku": "SHIRT-L-BLUE",
            "barcode": "012346",
            "price": "21.99",
            "option1": "Large",
            "option2": "Blue",
        },
    ],
}

CUSTOMER_1 = {
    "id": 222,
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com",
    "phone": "+2348012345678",
}

ORDER_1 = {
    "id": 333,
    "created_at": "2026-06-01T10:00:00-04:00",
    "currency": "USD",
    "customer": {"id": 222},
    "line_items": [
        {
            "product_id": 111,
            "variant_id": 1111,
            "quantity": 2,
            "price": "19.99",
        }
    ],
    "payment_gateway_names": ["shopify_payments"],
}


class TestShopifyAPIExtractorExtract:
    @pytest.mark.asyncio
    async def test_extracts_products_customers_and_sales_single_page(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Shopify-Access-Token"] == "shpat_supersecrettoken"
            assert request.url.scheme == "https"
            if "products.json" in str(request.url):
                return _json_response(request, {"products": [PRODUCT_1]})
            if "customers.json" in str(request.url):
                return _json_response(request, {"customers": [CUSTOMER_1]})
            if "orders.json" in str(request.url):
                return _json_response(request, {"orders": [ORDER_1]})
            raise AssertionError(f"Unexpected URL: {request.url}")

        with _mocked_client(_default_shop_handler(handler)):
            extractor = _make_extractor()
            data = await extractor.extract()

        assert {row["source_id"] for row in data["products"]} == {"111"}
        product_row = data["products"][0]
        assert product_row["name"] == "Blue Shirt"
        assert product_row["is_active"] == "true"
        # Currency comes from the shop resource (shop.json), never a
        # nonexistent per-product field.
        assert product_row["currency"] == "USD"

        assert len(data["product_variants"]) == 2
        variant_row = next(r for r in data["product_variants"] if r["source_id"] == "1111")
        assert variant_row["product_source_id"] == "111"
        assert variant_row["sku"] == "SHIRT-S-BLUE"
        assert "option1:Small" in variant_row["attributes"]
        assert "option2:Blue" in variant_row["attributes"]

        assert data["customers"] == [
            {
                "source_id": "222",
                "name": "Jane Doe",
                "email": "jane@example.com",
                "contact_number": "+2348012345678",
            }
        ]

        assert len(data["sales"]) == 1
        sale = data["sales"][0]
        assert sale["product_source_id"] == "111"
        assert sale["variant_source_id"] == "1111"
        assert sale["customer_source_id"] == "222"
        assert sale["quantity"] == "2"
        assert sale["unit_price"] == "19.99"
        assert sale["currency"] == "USD"
        assert sale["channel"] == "online"
        assert sale["sale_date"] == "2026-06-01"

    @pytest.mark.asyncio
    async def test_zero_priced_variant_override_is_not_dropped(self):
        """A variant explicitly priced/costed at 0 must produce '0', not ''
        (regression test for a falsy-vs-None bug)."""
        zero_priced = {
            **PRODUCT_1,
            "id": 888,
            "variants": [
                {
                    "id": 8881,
                    "product_id": 888,
                    "title": "Free Sample",
                    "sku": "FREE-1",
                    "barcode": "",
                    "price": "0.00",
                    "cost": 0,
                }
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if "products.json" in str(request.url):
                return _json_response(request, {"products": [zero_priced]})
            if "customers.json" in str(request.url):
                return _json_response(request, {"customers": []})
            if "orders.json" in str(request.url):
                return _json_response(request, {"orders": []})
            raise AssertionError(f"Unexpected URL: {request.url}")

        with _mocked_client(_default_shop_handler(handler)):
            extractor = _make_extractor()
            data = await extractor.extract()

        variant_row = data["product_variants"][0]
        assert variant_row["price_override"] == "0.00"
        assert variant_row["cost_price_override"] == "0"

    @pytest.mark.asyncio
    async def test_paginates_using_link_header(self):
        calls = {"products": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "products.json" in url:
                calls["products"] += 1
                if calls["products"] == 1:
                    next_link = f'<{BASE_URL}/products.json?page_info=abc123>; rel="next"'
                    return _json_response(
                        request, {"products": [PRODUCT_1]}, link=next_link
                    )
                return _json_response(request, {"products": []})
            if "customers.json" in url:
                return _json_response(request, {"customers": []})
            if "orders.json" in url:
                return _json_response(request, {"orders": []})
            raise AssertionError(f"Unexpected URL: {url}")

        with _mocked_client(_default_shop_handler(handler)):
            extractor = _make_extractor()
            data = await extractor.extract()

        assert calls["products"] == 2
        assert len(data["products"]) == 1

    @pytest.mark.asyncio
    async def test_never_logs_or_leaks_access_token(self, caplog):
        def handler(request: httpx.Request) -> httpx.Response:
            if "products.json" in str(request.url):
                return _json_response(request, {"products": [PRODUCT_1]})
            if "customers.json" in str(request.url):
                return _json_response(request, {"customers": []})
            if "orders.json" in str(request.url):
                return _json_response(request, {"orders": []})
            raise AssertionError(f"Unexpected URL: {request.url}")

        with _mocked_client(_default_shop_handler(handler)):
            extractor = _make_extractor()
            with caplog.at_level("DEBUG"):
                await extractor.extract()

        assert "shpat_supersecrettoken" not in caplog.text

    @pytest.mark.asyncio
    async def test_http_error_raises_without_leaking_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errors": "Unauthorized"}, request=request)

        with _mocked_client(handler):
            extractor = _make_extractor()
            with pytest.raises(Exception) as exc_info:
                await extractor.extract()

        assert "shpat_supersecrettoken" not in str(exc_info.value)


class TestShopifyAPIExtractorTestConnection:
    @pytest.mark.asyncio
    async def test_returns_counts_and_date_range(self):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "products.json" in url:
                return _json_response(request, {"products": [PRODUCT_1, {**PRODUCT_1, "id": 112}]})
            if "customers.json" in url:
                return _json_response(request, {"customers": [CUSTOMER_1]})
            if "orders.json" in url:
                return _json_response(
                    request,
                    {
                        "orders": [
                            ORDER_1,
                            {**ORDER_1, "id": 334, "created_at": "2026-06-15T08:00:00-04:00"},
                        ]
                    },
                )
            raise AssertionError(f"Unexpected URL: {url}")

        with _mocked_client(handler):
            extractor = _make_extractor()
            result = await extractor.test_connection()

        assert result["counts"]["products"] == 2
        assert result["counts"]["customers"] == 1
        assert result["counts"]["sales"] == 2
        assert result["date_range"]["earliest"] == "2026-06-01"
        assert result["date_range"]["latest"] == "2026-06-15"

    @pytest.mark.asyncio
    async def test_does_not_paginate_beyond_first_page(self):
        """test_connection is a cheap preview — it must not follow Link-header
        pagination the way a full extract() does."""
        calls = {"orders": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "products.json" in url:
                return _json_response(request, {"products": []})
            if "customers.json" in url:
                return _json_response(request, {"customers": []})
            if "orders.json" in url:
                calls["orders"] += 1
                next_link = f'<{BASE_URL}/orders.json?page_info=xyz>; rel="next"'
                return _json_response(request, {"orders": [ORDER_1]}, link=next_link)
            raise AssertionError(f"Unexpected URL: {url}")

        with _mocked_client(handler):
            extractor = _make_extractor()
            result = await extractor.test_connection()

        assert calls["orders"] == 1
        assert result["counts"]["sales"] == 1

    @pytest.mark.asyncio
    async def test_invalid_credentials_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errors": "Invalid API key"}, request=request)

        with _mocked_client(handler):
            extractor = _make_extractor()
            with pytest.raises(Exception):
                await extractor.test_connection()

    @pytest.mark.asyncio
    async def test_uses_https_and_auth_header(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["scheme"] = request.url.scheme
            seen["token_header"] = request.headers.get("X-Shopify-Access-Token")
            if "products.json" in str(request.url):
                return _json_response(request, {"products": []})
            if "customers.json" in str(request.url):
                return _json_response(request, {"customers": []})
            if "orders.json" in str(request.url):
                return _json_response(request, {"orders": []})
            raise AssertionError(f"Unexpected URL: {request.url}")

        with _mocked_client(handler):
            extractor = _make_extractor()
            await extractor.test_connection()

        assert seen["scheme"] == "https"
        assert seen["token_header"] == "shpat_supersecrettoken"


class TestShopifyAPIExtractorEdgeCases:
    @pytest.mark.asyncio
    async def test_product_without_variants_still_extracted(self):
        product_no_variants = {**PRODUCT_1, "id": 999, "variants": []}

        def handler(request: httpx.Request) -> httpx.Response:
            if "products.json" in str(request.url):
                return _json_response(request, {"products": [product_no_variants]})
            if "customers.json" in str(request.url):
                return _json_response(request, {"customers": []})
            if "orders.json" in str(request.url):
                return _json_response(request, {"orders": []})
            raise AssertionError(f"Unexpected URL: {request.url}")

        with _mocked_client(_default_shop_handler(handler)):
            extractor = _make_extractor()
            data = await extractor.extract()

        assert len(data["products"]) == 1
        assert data["products"][0]["source_id"] == "999"
        assert data["product_variants"] == []

    @pytest.mark.asyncio
    async def test_order_without_customer_has_blank_customer_source_id(self):
        order_no_customer = {**ORDER_1, "id": 555, "customer": None}

        def handler(request: httpx.Request) -> httpx.Response:
            if "products.json" in str(request.url):
                return _json_response(request, {"products": []})
            if "customers.json" in str(request.url):
                return _json_response(request, {"customers": []})
            if "orders.json" in str(request.url):
                return _json_response(request, {"orders": [order_no_customer]})
            raise AssertionError(f"Unexpected URL: {request.url}")

        with _mocked_client(_default_shop_handler(handler)):
            extractor = _make_extractor()
            data = await extractor.extract()

        assert len(data["sales"]) == 1
        assert data["sales"][0]["customer_source_id"] == ""
