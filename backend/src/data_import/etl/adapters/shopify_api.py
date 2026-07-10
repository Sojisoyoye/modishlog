"""Shopify Admin REST API extractor — Phase 1 work unit.

Authenticates with a private/custom-app access token (``X-Shopify-Access-Token``
header) and pulls products (with nested variants), orders (as sales) and
customers live via Shopify's Admin REST API, following cursor-based
pagination via the ``Link`` response header.

Credentials must never be persisted or logged — see
`etl/extractor.APIExtractor`'s docstring. ``self._credentials["access_token"]``
is used only to set a request header for the lifetime of this extraction and
is never written to a URL, a log line, or an exception message.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog

from src.data_import.etl.extractor import APIExtractor, ExtractedData

logger = structlog.get_logger()

# Shopify's Admin REST API paginates at up to 250 records per page.
_PAGE_LIMIT = 250

_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


class ShopifyAPIError(Exception):
    """Raised when the Shopify Admin API returns an error response.

    Deliberately carries only the HTTP status and a short, credential-free
    message — never the request URL (which may carry auth params) or headers.
    """


class ShopifyAPIExtractor(APIExtractor):
    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def extract(self) -> ExtractedData:
        async with self._client() as client:
            shop_currency = await self._get_shop_currency(client)
            products = await self._get_all(client, "products.json", "products")
            customers = await self._get_all(client, "customers.json", "customers")
            orders = await self._get_all(client, "orders.json", "orders")

        return {
            "product_categories": [],
            "products": [self._map_product(p, shop_currency) for p in products],
            "product_variants": [
                self._map_variant(v, product_id=p["id"])
                for p in products
                for v in (p.get("variants") or [])
            ],
            "suppliers": [],
            "customers": [self._map_customer(c) for c in customers],
            "business_locations": [],
            "sales": [row for order in orders for row in self._map_order_sales(order)],
        }

    async def test_connection(self) -> dict:
        # Deliberately cheap: a single page (up to _PAGE_LIMIT rows) per
        # entity, not a full paginated pull — this endpoint exists so the
        # UI can preview row counts/date range before committing to the
        # potentially many-request cost of a full extract().
        async with self._client() as client:
            products = await self._get_page(client, "products.json", "products")
            customers = await self._get_page(client, "customers.json", "customers")
            orders = await self._get_page(client, "orders.json", "orders")

        order_dates = sorted(
            o["created_at"][:10] for o in orders if o.get("created_at")
        )
        date_range = None
        if order_dates:
            date_range = {"earliest": order_dates[0], "latest": order_dates[-1]}

        return {
            "counts": {
                "products": len(products),
                "customers": len(customers),
                "sales": len(orders),
            },
            "date_range": date_range,
        }

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        token = self._credentials.get("access_token", "")
        headers = {
            "X-Shopify-Access-Token": token,
            "Accept": "application/json",
        }
        if not self._base_url.lower().startswith("https://"):
            raise ShopifyAPIError("Shopify base_url must use https://")
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=30.0,
        )

    async def _get_shop_currency(self, client: httpx.AsyncClient) -> str:
        """Currency lives on the Shop resource in Shopify's API, not on
        individual Product objects — fetched once per extraction and reused
        for every product row.
        """
        response = await client.get("shop.json")
        self._raise_for_status(response)
        shop = response.json().get("shop") or {}
        return shop.get("currency") or "NGN"

    async def _get_page(
        self, client: httpx.AsyncClient, path: str, key: str
    ) -> list[dict[str, Any]]:
        """Fetch a single page (used by test_connection — a cheap preview,
        never a full paginated pull).
        """
        response = await client.get(path, params={"limit": _PAGE_LIMIT})
        self._raise_for_status(response)
        return response.json().get(key, [])

    async def _get_all(
        self, client: httpx.AsyncClient, path: str, key: str
    ) -> list[dict[str, Any]]:
        """Follow Shopify's cursor-based (Link header) pagination until exhausted."""
        results: list[dict[str, Any]] = []
        url: str | None = path
        params: dict[str, Any] | None = {"limit": _PAGE_LIMIT}

        while url is not None:
            response = await client.get(url, params=params)
            self._raise_for_status(response)
            payload = response.json()
            results.extend(payload.get(key, []))

            # Subsequent requests use the fully-qualified `next` URL returned
            # by Shopify, which already carries the cursor query params.
            url = self._next_page_url(response)
            params = None

        return results

    @staticmethod
    def _next_page_url(response: httpx.Response) -> str | None:
        link_header = response.headers.get("Link") or response.headers.get("link")
        if not link_header:
            return None
        match = _LINK_NEXT_RE.search(link_header)
        return match.group(1) if match else None

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            # Never include the request URL/headers (which carry the access
            # token) in the raised message — status + short reason only.
            logger.warning(
                "shopify_api.error_response",
                status_code=response.status_code,
            )
            raise ShopifyAPIError(
                f"Shopify API request failed with status {response.status_code}"
            )

    # ------------------------------------------------------------------
    # Entity mapping — Shopify JSON -> ModishLog field names
    # ------------------------------------------------------------------

    @staticmethod
    def _map_product(product: dict[str, Any], shop_currency: str) -> dict[str, str]:
        # Shopify's Product resource has no per-product currency field —
        # currency is a shop-level setting, fetched once via shop.json and
        # passed in here rather than read (non-existently) off `product`.
        variants = product.get("variants") or []
        first_variant = variants[0] if variants else {}
        return {
            "source_id": str(product["id"]),
            "name": (product.get("title") or "").strip(),
            "sku": first_variant.get("sku") or "",
            "barcode": first_variant.get("barcode") or "",
            "unit_cost": _decimal_str(first_variant.get("cost")),
            "selling_price": _decimal_str(first_variant.get("price")),
            "currency": shop_currency,
            "category_source_id": "",
            "is_active": "true" if product.get("status") == "active" else "false",
        }

    @staticmethod
    def _map_variant(variant: dict[str, Any], *, product_id: Any) -> dict[str, str]:
        attributes = ";".join(
            f"{opt_key}:{variant[opt_key]}"
            for opt_key in ("option1", "option2", "option3")
            if variant.get(opt_key)
        )
        return {
            "source_id": str(variant["id"]),
            "product_source_id": str(product_id),
            "name": (variant.get("title") or "").strip(),
            "sku": variant.get("sku") or "",
            "barcode": variant.get("barcode") or "",
            "attributes": attributes,
            # `is not None` rather than plain truthiness — a variant legitimately
            # priced/costed at 0 must still produce "0", not be treated as
            # "no override present" and dropped as "".
            "price_override": (
                _decimal_str(variant["price"]) if variant.get("price") is not None else ""
            ),
            "cost_price_override": (
                _decimal_str(variant["cost"]) if variant.get("cost") is not None else ""
            ),
        }

    @staticmethod
    def _map_customer(customer: dict[str, Any]) -> dict[str, str]:
        name = " ".join(
            part
            for part in (customer.get("first_name"), customer.get("last_name"))
            if part
        ).strip()
        return {
            "source_id": str(customer["id"]),
            "name": name or customer.get("email") or f"Customer {customer['id']}",
            "email": customer.get("email") or "",
            "contact_number": customer.get("phone") or "",
        }

    @staticmethod
    def _map_order_sales(order: dict[str, Any]) -> list[dict[str, str]]:
        customer = order.get("customer") or {}
        customer_source_id = str(customer["id"]) if customer.get("id") is not None else ""
        sale_date = (order.get("created_at") or "")[:10]
        currency = order.get("currency") or "NGN"
        payment_methods = order.get("payment_gateway_names") or []
        payment_method = payment_methods[0] if payment_methods else ""

        rows = []
        for line_item in order.get("line_items") or []:
            product_id = line_item.get("product_id")
            if product_id is None:
                # Custom/manual line items with no linked product can't be
                # resolved against the products upload — skip rather than
                # emit a row the transformer can never match.
                continue
            variant_id = line_item.get("variant_id")
            rows.append(
                {
                    "product_source_id": str(product_id),
                    "variant_source_id": str(variant_id) if variant_id is not None else "",
                    "customer_source_id": customer_source_id,
                    "quantity": str(line_item.get("quantity") or 0),
                    "unit_price": _decimal_str(line_item.get("price")),
                    "sale_date": sale_date,
                    "currency": currency,
                    "channel": "online",
                    "payment_method": payment_method,
                    "location_name": "",
                }
            )
        return rows


def _decimal_str(raw: Any) -> str:
    """Round-trip a Shopify numeric-as-string field through Decimal so the
    transformer always receives a clean amount string, never a float repr.
    """
    if raw is None or raw == "":
        return "0"
    try:
        return str(Decimal(str(raw)))
    except InvalidOperation:
        return "0"
