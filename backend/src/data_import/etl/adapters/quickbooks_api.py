"""QuickBooks Online API extractor — Phase 1 work unit.

OAuth 2.0 flow — the access token is passed in from the frontend after the
OAuth redirect completes; this extractor never handles the OAuth handshake
itself. Credentials/tokens must never be persisted or logged — see
`etl/extractor.APIExtractor`'s docstring.

Pulls Item, Customer, Vendor and Invoice entities from the QBO Accounting API
query endpoint (`/query?query=SELECT ...`) and maps them onto ModishLog's
entity field names. QuickBooks has no native product-variant concept, so
`product_variants` is always returned empty.
"""

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog

from src.data_import.etl.extractor import APIExtractor, ExtractedData

logger = structlog.get_logger()

_PAGE_SIZE = 1000

# QBO Item.Type == "Category" rows are folder/grouping entries, not sellable
# items — anything else (Inventory, NonInventory, Service, ...) is a product.
_CATEGORY_ITEM_TYPE = "Category"

# Minor version 40+ is required for QBO to include the `Sku` field on Item
# query responses; older/unspecified minor versions silently omit it.
_MINOR_VERSION = "65"


class QuickBooksAPIExtractor(APIExtractor):
    def __init__(self, base_url: str, credentials: dict[str, str]) -> None:
        super().__init__(base_url, credentials)
        # Test hook: tests inject an httpx.MockTransport here instead of
        # hitting the network. Production code leaves this unset and a real
        # AsyncClient is built per request.
        self._transport: httpx.BaseTransport | None = None

    async def extract(self) -> ExtractedData:
        items, customers, vendors, invoices = await self._query_all_entities()

        categories, products = self._map_items(items)

        return {
            "product_categories": categories,
            "products": products,
            "product_variants": [],
            "suppliers": [self._map_vendor(v) for v in vendors],
            "customers": [self._map_customer(c) for c in customers],
            "business_locations": [],
            "sales": self._map_invoices_to_sales(invoices),
        }

    async def test_connection(self) -> dict:
        items, customers, vendors, invoices = await self._query_all_entities()

        categories, products = self._map_items(items)
        sales = self._map_invoices_to_sales(invoices)

        dates = sorted(s["sale_date"] for s in sales if s.get("sale_date"))
        date_range = {
            "earliest": dates[0] if dates else None,
            "latest": dates[-1] if dates else None,
        }

        return {
            "counts": {
                "product_categories": len(categories),
                "products": len(products),
                "product_variants": 0,
                "suppliers": len(vendors),
                "customers": len(customers),
                "business_locations": 0,
                "sales": len(sales),
            },
            "date_range": date_range,
        }

    # ------------------------------------------------------------------
    # HTTP / pagination
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=30.0)

    async def _query_all_entities(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Pull Item/Customer/Vendor/Invoice concurrently — the four pulls are
        independent, so awaiting them one at a time would multiply total
        latency by up to 4x for no benefit."""
        return await asyncio.gather(
            self._query_all("Item"),
            self._query_all("Customer"),
            self._query_all("Vendor"),
            self._query_all("Invoice"),
        )

    async def _query_all(self, entity: str) -> list[dict[str, Any]]:
        """Pull every row for a QBO entity type, paginating via STARTPOSITION/
        MAXRESULTS in the SQL-like query syntax."""
        access_token = self._credentials.get("access_token")
        if not access_token:
            raise ValueError("QuickBooks extraction requires an access_token credential")

        rows: list[dict[str, Any]] = []
        start_position = 1
        while True:
            query = (
                f"SELECT * FROM {entity} "
                f"STARTPOSITION {start_position} MAXRESULTS {_PAGE_SIZE}"
            )
            body = await self._run_query(access_token, query)
            page = body.get("QueryResponse", {}).get(entity, [])
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            start_position += _PAGE_SIZE
        return rows

    async def _run_query(self, access_token: str, query: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        try:
            async with self._client() as client:
                response = await client.get(
                    f"{self._base_url}/query",
                    params={"query": query, "minorversion": _MINOR_VERSION},
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            # Never let response text/headers (which may echo the request) or
            # the token leak into the exception message.
            status_code = e.response.status_code
            await logger.awarning("quickbooks_api_http_error", status_code=status_code)
            raise ValueError(f"QuickBooks API request failed with status {status_code}") from None
        except httpx.RequestError as e:
            await logger.awarning("quickbooks_api_request_error", error_type=type(e).__name__)
            raise ValueError("QuickBooks API request failed") from None

    # ------------------------------------------------------------------
    # Field mapping — QBO entity -> ModishLog field names
    # ------------------------------------------------------------------

    @staticmethod
    def _map_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        categories = []
        products = []
        for item in items:
            if item.get("Type") == _CATEGORY_ITEM_TYPE:
                categories.append(
                    {
                        "source_id": str(item["Id"]),
                        "name": item.get("Name", ""),
                        "description": item.get("Description", ""),
                        "parent_source_id": _parent_ref_id(item),
                    }
                )
                continue

            products.append(
                {
                    "source_id": str(item["Id"]),
                    "name": item.get("Name", ""),
                    "sku": item.get("Sku", "") or "",
                    "barcode": "",
                    "unit_cost": _stringify_amount(item.get("PurchaseCost")),
                    "selling_price": _stringify_amount(item.get("UnitPrice")),
                    "currency": "NGN",
                    "category_source_id": _parent_ref_id(item),
                    "is_active": "true" if item.get("Active", True) else "false",
                }
            )
        return categories, products

    @staticmethod
    def _map_customer(customer: dict[str, Any]) -> dict[str, str]:
        return {
            "source_id": str(customer["Id"]),
            "name": customer.get("DisplayName", ""),
            "email": customer.get("PrimaryEmailAddr", {}).get("Address", ""),
            "contact_number": customer.get("PrimaryPhone", {}).get("FreeFormNumber", ""),
        }

    @staticmethod
    def _map_vendor(vendor: dict[str, Any]) -> dict[str, str]:
        return {
            "source_id": str(vendor["Id"]),
            "name": vendor.get("DisplayName", ""),
            "email": vendor.get("PrimaryEmailAddr", {}).get("Address", ""),
            # QBO Vendor has no dedicated contact-name field like Customer's
            # GivenName/FamilyName — PrintOnCheckName is the closest proxy for
            # a human contact at the supplier and is commonly populated.
            "contact_person": vendor.get("PrintOnCheckName", ""),
            "mobile": vendor.get("PrimaryPhone", {}).get("FreeFormNumber", ""),
        }

    @staticmethod
    def _map_invoices_to_sales(invoices: list[dict[str, Any]]) -> list[dict[str, str]]:
        sales = []
        for invoice in invoices:
            sale_date = invoice.get("TxnDate", "")
            currency = invoice.get("CurrencyRef", {}).get("value", "NGN")
            customer_source_id = str(invoice.get("CustomerRef", {}).get("value", "")) or ""

            for line in invoice.get("Line", []):
                if line.get("DetailType") != "SalesItemLineDetail":
                    continue
                detail = line.get("SalesItemLineDetail", {})
                item_ref = detail.get("ItemRef")
                if not item_ref or not item_ref.get("value"):
                    continue

                qty = detail.get("Qty", "1")
                sales.append(
                    {
                        "product_source_id": str(item_ref["value"]),
                        "variant_source_id": "",
                        "customer_source_id": customer_source_id,
                        "quantity": str(qty),
                        "unit_price": _line_unit_price(detail, line, qty),
                        "sale_date": sale_date,
                        "currency": currency,
                        "channel": "online",
                        "payment_method": "",
                        "location_name": "",
                    }
                )
        return sales


def _stringify_amount(value: Any) -> str:
    """Normalise a QBO numeric field to a plain decimal string, defaulting to
    "0" for missing/unparseable values. Runs through Decimal (never float) to
    avoid introducing binary floating-point error into a financial value."""
    if value is None or value == "":
        return "0"
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return "0"


def _parent_ref_id(entity: dict[str, Any]) -> str:
    """Extract a QBO ParentRef.value as a stringified source_id, or "" when
    the entity has no parent. Shared by both the category and product
    branches of `_map_items`, which both read the same `ParentRef` shape."""
    parent_ref = entity.get("ParentRef")
    if not parent_ref or not parent_ref.get("value"):
        return ""
    return str(parent_ref["value"])


def _line_unit_price(detail: dict[str, Any], line: dict[str, Any], qty: Any) -> str:
    """QBO invoice lines frequently omit SalesItemLineDetail.UnitPrice (e.g.
    when a user enters a flat line Amount without a quantity breakdown) while
    Line.Amount is always populated — fall back to Amount / Qty so a missing
    UnitPrice doesn't silently zero out the imported sale's revenue."""
    if detail.get("UnitPrice") not in (None, ""):
        return _stringify_amount(detail["UnitPrice"])

    amount = line.get("Amount")
    if amount in (None, ""):
        return "0"
    try:
        qty_decimal = Decimal(str(qty))
        if qty_decimal == 0:
            return "0"
        return str(Decimal(str(amount)) / qty_decimal)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return "0"
