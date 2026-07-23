"""UltimatePOS live API extractor — Phase 1 work unit.

Ports the `POSClient` auth + entity-pull logic from `backend/scripts/pos_migrate.py`
(cookie/CSRF auth, product/sell/purchase/contact pulls, HTML receipt parsing)
onto the `APIExtractor` interface, producing rows already shaped to
ModishLog's target field names (see `etl/transformer.py` and
`service._TEMPLATE_COLUMNS`) instead of pos_migrate's own internal ORM format.

Credentials (`self._credentials`) are used only for the duration of a single
`extract()`/`test_connection()` call — never persisted, never logged. Only
non-sensitive event names/counts are logged (see `etl/extractor.APIExtractor`
docstring). All outbound calls are HTTPS-only.
"""

import json
import math
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import anyio
import structlog

from src.data_import.etl.extractor import APIExtractor, ExtractedData

logger = structlog.get_logger()

_REQUIRED_CREDENTIAL_FIELDS = ("username", "password")


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _parse_price(raw: Any) -> Decimal:
    digits = re.sub(r"[^\d.\-]", "", _strip_html(str(raw)))
    if not digits:
        return Decimal("0")
    try:
        return Decimal(digits)
    except Exception:
        return Decimal("0")


def _parse_qty(raw: Any) -> int:
    """Round fractional quantities up to at least 1, matching pos_migrate.py's
    sell-line handling — length/weight-based goods (e.g. 0.5m of edge tape)
    must not be truncated to 0 and dropped.
    """
    m = re.match(r"^(-?[\d.]+)", str(raw or ""))
    if not m:
        return 0
    qty_float = float(m.group(1))  # financial-float-ok — quantity, not money
    if qty_float <= 0:
        return 0
    return max(1, math.ceil(qty_float))


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _extract_pos_id(item: dict, path_prefix: str) -> str | None:
    direct_id = item.get("id")
    if direct_id is not None:
        return str(direct_id)
    dt_attr = item.get("DT_RowAttr") or {}
    href = dt_attr.get("data-href", "")
    m = re.search(rf"/{re.escape(path_prefix)}/(\d+)", href)
    if m:
        return m.group(1)
    row_id = str(item.get("DT_RowId", ""))
    m2 = re.match(r"row_(\d+)", row_id)
    if m2:
        return m2.group(1)
    return None


def _extract_contact_id(contact: dict) -> str | None:
    """Contacts have no top-level `id` and no `DT_RowAttr` on this API
    version — confirmed live: `/contacts` rows carry a human-facing
    `contact_id` code (e.g. "CO0002") but the only place the real numeric
    primary key appears is inside the `action` column's `/contacts/{id}`
    links. Falls back to `id` first for forward-compat with any API
    version that does return one directly.
    """
    direct_id = contact.get("id")
    if direct_id is not None:
        return str(direct_id)
    action_html = str(contact.get("action") or "")
    m = re.search(r"/contacts/(\d+)", action_html)
    return m.group(1) if m else None


_CHANNEL_FALLBACK = "retail"

# Fallback NGN/USD rate used to convert purchase-order unit costs when no
# live rate is available (the extractor has no DB session, so it can't call
# src.fx.service.get_live_usdngn_rate() the way pos_migrate.py does) — same
# fallback value pos_migrate.py itself falls back to on a failed live fetch.
_FALLBACK_NGN_USD_RATE = Decimal("1600")


class _POSAPIClient:
    """Cookie/CSRF-authenticated UltimatePOS v5 client, ported from
    `backend/scripts/pos_migrate.py`'s `POSClient`. All HTTP is synchronous
    urllib, matching the reference implementation — callers wrap blocking
    calls with `anyio.to_thread.run_sync`.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._jar))

    def _get(self, path: str, headers: dict[str, str] | None = None) -> str:
        req = Request(f"{self._base_url}{path}", headers=headers or {})
        with self._opener.open(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _post(self, path: str, data: dict[str, str], headers: dict[str, str] | None = None) -> tuple[int, str]:
        body = urlencode(data).encode()
        req = Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
        )
        req.get_method = lambda: "POST"  # type: ignore[method-assign]
        try:
            with self._opener.open(req, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError) as exc:
            raise ConnectionError("UltimatePOS login request failed") from exc

    def _csrf(self, path: str) -> str:
        html = self._get(path)
        m = re.search(r'name="_token"\s+value="([^"]+)"', html)
        if not m:
            m = re.search(r'content="([^"]+)"\s+name="csrf-token"', html)
        if not m:
            raise ConnectionError("CSRF token not found — unexpected login page shape")
        return m.group(1)

    def login(self) -> None:
        csrf = self._csrf("/login")
        status, body = self._post("/login", {"_token": csrf, "username": self._username, "password": self._password})  # risk-ok — posts the login form, not a log call
        # Same success heuristic as pos_migrate.py's proven POSClient.login —
        # UltimatePOS redirects to /home on success. This substring check
        # alone can false-negative-pass a failed login if shared layout
        # markup happens to contain "home" (e.g. a nav link), so it's
        # backed up by an authenticated-probe check below.
        if "home" not in body and status not in (200, 302):
            raise ConnectionError("UltimatePOS authentication failed — check credentials")
        if self._looks_like_login_page(self._get("/dashboard")):
            raise ConnectionError("UltimatePOS authentication failed — check credentials")

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        return bool(html) and 'action="/login"' in html and "_token" in html

    def _json_get(self, path: str) -> Any:
        html = self._get(path, {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
        return json.loads(html)

    def _json_list(self, path: str) -> list[dict]:
        """GET a JSON list endpoint, soft-failing to an empty list. Any
        failure (network, auth expiry, malformed JSON) is logged with the
        path only — never with response bodies or credentials — so it stays
        diagnosable without leaking sensitive data.
        """
        try:
            return self._json_get(path).get("data", [])
        except Exception as exc:
            logger.warning("ultimatepos_api_fetch_failed", path=path, error_type=type(exc).__name__)
            return []

    def fetch_products(self) -> list[dict]:
        return self._json_list("/products?per_page=1000")

    def fetch_contacts(self, contact_type: str) -> list[dict]:
        return self._json_list(f"/contacts?type={contact_type}&per_page=500")

    def fetch_business_locations(self) -> list[dict]:
        # Singular path, not "/business-locations" — confirmed against a
        # real instance; the plural form 404s. Rows come back as plain
        # positional arrays (no field names), not keyed objects — see
        # _map_locations() for the confirmed column order.
        return self._json_list("/business-location?per_page=200")

    def fetch_sells(self) -> list[dict]:
        return self._json_list("/sells?per_page=2000")

    def fetch_sell_detail_html(self, sell_id: str | int) -> str:
        """Fetch a sell's receipt HTML, matching pos_migrate.py's behavior of
        re-authenticating once if the session expired mid-pull (detected by
        a redirect back to the login form) rather than silently returning an
        unusable login page as if it were the receipt.
        """
        try:
            html = self._get(f"/sells/{sell_id}")
            if self._looks_like_login_page(html):
                logger.info("ultimatepos_api_session_expired_reauth", sell_id=str(sell_id))
                self.login()
                html = self._get(f"/sells/{sell_id}")
            return html
        except Exception as exc:
            logger.warning(
                "ultimatepos_api_sell_detail_fetch_failed",
                sell_id=str(sell_id),
                error_type=type(exc).__name__,
            )
            return ""

    def fetch_purchases(self) -> list[dict]:
        return self._json_list("/purchases?per_page=2000")

    def fetch_purchase_print_html(self, purchase_id: str | int) -> str:
        """Fetch a purchase's line-item detail via the print/modal endpoint —
        confirmed live: JSON envelope {"receipt": {"html_content": "..."}}.
        """
        try:
            raw = self._get(f"/purchases/print/{purchase_id}")
            if not raw.strip():
                return ""
            data = json.loads(raw)
            return data.get("receipt", {}).get("html_content", "")
        except Exception as exc:
            logger.warning(
                "ultimatepos_api_purchase_print_fetch_failed",
                purchase_id=str(purchase_id),
                error_type=type(exc).__name__,
            )
            return ""

    def fetch_expense_categories(self) -> list[dict]:
        return self._json_list("/expense-categories?per_page=200")

    def fetch_expenses(self) -> list[dict]:
        return self._json_list("/expenses?per_page=2000")

    def fetch_stock_adjustments(self) -> list[dict]:
        return self._json_list("/stock-adjustments?per_page=2000")

    def fetch_sell_returns(self) -> list[dict]:
        # Singular path, not "/sell-returns" — confirmed against a real
        # instance; the plural form 404s, same class of bug as
        # fetch_business_locations()'s singular "/business-location".
        return self._json_list("/sell-return?per_page=2000")

    def fetch_purchase_returns(self) -> list[dict]:
        return self._json_list("/purchase-return?per_page=2000")

    def fetch_stock_adjustment_detail_html(self, adjustment_id: str | int) -> str:
        """Fetch a stock adjustment's line-item detail — confirmed live: the
        list endpoint carries header fields only (adjustment_type,
        additional_notes) with no embedded line items, so each adjustment's
        products/quantities require this separate per-record fetch, same
        shape as fetch_sell_detail_html/fetch_purchase_print_html. Unlike
        /sells/{id} (a plain page), this endpoint only returns the usable
        line-item table when asked for as XHR — a plain GET returns the
        full dashboard shell instead.
        """
        try:
            headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
            html = self._get(f"/stock-adjustments/{adjustment_id}", headers)
            if self._looks_like_login_page(html):
                logger.info(
                    "ultimatepos_api_session_expired_reauth",
                    stock_adjustment_id=str(adjustment_id),
                )
                self.login()
                html = self._get(f"/stock-adjustments/{adjustment_id}", headers)
            return html
        except Exception as exc:
            logger.warning(
                "ultimatepos_api_stock_adjustment_detail_fetch_failed",
                stock_adjustment_id=str(adjustment_id),
                error_type=type(exc).__name__,
            )
            return ""


def _parse_sell_lines_from_html(
    html: str,
    pos_id_to_source: dict[str, str],
    name_to_source: dict[str, str] | None = None,
) -> list[dict]:
    """Extract sell line items from a UltimatePOS receipt HTML page.

    Same column layout as pos_migrate.py's `_parse_sell_lines_from_html`:
    [0] # [1] Product name + pos_product_id [2] Quantity [3] Unit Price
    [4] Discount [5] Tax [6] Price inc. tax [7] Subtotal

    Falls back to a normalised-name lookup when the trailing numeric
    pos_product_id is missing/unparseable, matching the reference script's
    resilience against receipt rows that don't carry the id suffix.
    """
    name_to_source = name_to_source or {}
    lines = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 4:
            continue

        product_cell_text = _strip_html(cells[1]).strip()
        pos_id_m = re.search(r"\s+(\d{4,})\s*$", product_cell_text)
        product_source_id = pos_id_m.group(1) if pos_id_m else None
        if not product_source_id or product_source_id not in pos_id_to_source:
            name_part = product_cell_text if not pos_id_m else product_cell_text[: pos_id_m.start()]
            norm = re.sub(r"\s+", " ", name_part.lower().strip())
            product_source_id = name_to_source.get(norm)
        if not product_source_id:
            continue

        qty_m = re.search(r'data-is_quantity="true"[^>]*>([^<]+)</span>', cells[2], re.IGNORECASE)
        qty_raw = qty_m.group(1).strip() if qty_m else _strip_html(cells[2])
        quantity = _parse_qty(qty_raw)
        if quantity <= 0:
            continue

        up_m = re.search(r'data-currency_symbol="true"[^>]*>([^<]+)</span>', cells[3], re.IGNORECASE)
        unit_price = _parse_price(up_m.group(1)) if up_m else Decimal("0")

        # Subtotal cell (index 7, or the last cell if the row is shorter) —
        # this is UltimatePOS's authoritative post-discount/tax line total.
        # Falls back to unit_price * quantity only when it can't be parsed.
        last_cell = cells[7] if len(cells) > 7 else cells[-1]
        st_m = re.search(r'data-currency_symbol="true"[^>]*>([^<]+)</span>', last_cell, re.IGNORECASE)
        line_total = _parse_price(st_m.group(1)) if st_m else Decimal("0")
        if not line_total:
            line_total = unit_price * Decimal(str(quantity))

        lines.append(
            {
                "product_source_id": product_source_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    return lines


class UltimatePOSAPIExtractor(APIExtractor):
    """Live-pull extractor for UltimatePOS v5 (Laravel), matching the field
    names `etl.transformer.Transformer` reads.
    """

    def __init__(self, base_url: str, credentials: dict[str, str]) -> None:
        if not base_url.lower().startswith("https://"):
            raise ValueError("UltimatePOS API base_url must use HTTPS")
        super().__init__(base_url, credentials)

    def _build_client(self) -> _POSAPIClient:
        missing = [f for f in _REQUIRED_CREDENTIAL_FIELDS if not self._credentials.get(f)]
        if missing:
            raise ValueError(f"Missing required UltimatePOS credential field(s): {', '.join(missing)}")
        return _POSAPIClient(
            self._base_url,
            self._credentials["username"],
            self._credentials["password"],
        )

    async def _login(self, client: _POSAPIClient) -> None:
        await anyio.to_thread.run_sync(client.login)

    # ------------------------------------------------------------------
    # extract()
    # ------------------------------------------------------------------

    async def extract(self) -> ExtractedData:
        logger.info("ultimatepos_api_extraction_started")
        client = self._build_client()
        await self._login(client)

        raw_products, raw_suppliers, raw_customers, raw_locations = await anyio.to_thread.run_sync(
            self._fetch_reference_data, client
        )

        categories, category_name_to_source = self._map_categories(raw_products)
        products, variants, pos_id_to_source, name_to_source = self._map_products(
            raw_products, category_name_to_source
        )
        suppliers = self._map_suppliers(raw_suppliers)
        customers = self._map_customers(raw_customers)
        locations = self._map_locations(raw_locations)
        known_customer_ids = {row["source_id"] for row in customers}

        raw_sells = await anyio.to_thread.run_sync(client.fetch_sells)
        sales = await self._map_sales(
            client, raw_sells, pos_id_to_source, name_to_source, known_customer_ids
        )

        raw_purchases = await anyio.to_thread.run_sync(client.fetch_purchases)
        purchase_orders = await self._map_purchase_orders(
            client, raw_purchases, raw_products, raw_suppliers
        )

        raw_expense_categories = await anyio.to_thread.run_sync(
            client.fetch_expense_categories
        )
        expense_categories, expense_category_id_to_source = self._map_expense_categories(
            raw_expense_categories
        )
        raw_expenses = await anyio.to_thread.run_sync(client.fetch_expenses)
        expenses = self._map_expenses(raw_expenses, expense_category_id_to_source)

        raw_stock_adjustments = await anyio.to_thread.run_sync(
            client.fetch_stock_adjustments
        )
        stock_adjustments = await self._map_stock_adjustments(
            client, raw_stock_adjustments, pos_id_to_source
        )

        raw_sell_returns = await anyio.to_thread.run_sync(client.fetch_sell_returns)
        sell_returns = self._map_sell_returns(raw_sell_returns)
        raw_purchase_returns = await anyio.to_thread.run_sync(
            client.fetch_purchase_returns
        )
        purchase_returns = self._map_purchase_returns(raw_purchase_returns)

        result: ExtractedData = {
            "product_categories": categories,
            "products": products,
            "product_variants": variants,
            "suppliers": suppliers,
            "customers": customers,
            "business_locations": locations,
            "sales": sales,
            "purchase_orders": purchase_orders,
            "expense_categories": expense_categories,
            "expenses": expenses,
            "stock_adjustments": stock_adjustments,
            "sell_returns": sell_returns,
            "purchase_returns": purchase_returns,
        }
        logger.info(
            "ultimatepos_api_extraction_complete",
            **{entity: len(rows) for entity, rows in result.items()},
        )
        return result

    def _fetch_reference_data(self, client: _POSAPIClient) -> tuple[list, list, list, list]:
        products = client.fetch_products()
        suppliers = client.fetch_contacts("supplier")
        customers = client.fetch_contacts("customer")
        locations = client.fetch_business_locations()
        return products, suppliers, customers, locations

    # ------------------------------------------------------------------
    # test_connection()
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict:
        logger.info("ultimatepos_api_test_connection_started")
        client = self._build_client()
        await self._login(client)

        raw_products, raw_suppliers, raw_customers, raw_locations = await anyio.to_thread.run_sync(
            self._fetch_reference_data, client
        )
        raw_sells = await anyio.to_thread.run_sync(client.fetch_sells)

        active_products = [p for p in raw_products if not p.get("is_inactive") and not p.get("not_for_selling")]
        distinct_categories = {
            _strip_html(str(p.get("category") or "")).strip()
            for p in raw_products
            if _strip_html(str(p.get("category") or "")).strip()
        }

        sell_dates = [
            _parse_date(str(s.get("transaction_date") or ""))
            for s in raw_sells
        ]
        sell_dates = [d for d in sell_dates if d is not None]

        counts = {
            "product_categories": len(distinct_categories),
            "products": len(active_products),
            "suppliers": len(raw_suppliers),
            "customers": len(raw_customers),
            "business_locations": len(raw_locations),
            "sales": len(raw_sells),
        }
        date_range = None
        if sell_dates:
            date_range = {
                "earliest": min(sell_dates).isoformat(),
                "latest": max(sell_dates).isoformat(),
            }

        logger.info("ultimatepos_api_test_connection_complete", **counts)
        return {"counts": counts, "date_range": date_range}

    # ------------------------------------------------------------------
    # Row mapping — raw UltimatePOS JSON -> ModishLog target field names
    # ------------------------------------------------------------------

    def _map_categories(
        self, raw_products: list[dict]
    ) -> tuple[list[dict], dict[str, str]]:
        """No standalone categories list endpoint exists on this API version
        (`/categories`, `/category`, `/product-category`, `/taxonomy` all
        404 — confirmed live) — category linkage lives only as a free-text
        `category` name on each product row, with no numeric ID at all.
        Derive the distinct set from products instead, using the
        normalized name itself as both source_id and lookup key.
        """
        out: list[dict] = []
        name_to_source: dict[str, str] = {}
        for p in raw_products:
            name = _strip_html(str(p.get("category") or "")).strip()
            if not name or name in name_to_source:
                continue
            name_to_source[name] = name
            out.append(
                {
                    "source_id": name,
                    "name": name,
                    "description": "",
                    "parent_source_id": "",
                }
            )
        return out, name_to_source

    def _map_products(
        self, raw_products: list[dict], category_name_to_source: dict[str, str]
    ) -> tuple[list[dict], list[dict], dict[str, str], dict[str, str]]:
        products = []
        variants = []
        pos_id_to_source: dict[str, str] = {}
        name_to_source: dict[str, str] = {}

        for p in raw_products:
            if p.get("is_inactive") or p.get("not_for_selling"):
                continue
            pos_id = p.get("id")
            if pos_id is None:
                continue
            source_id = str(pos_id)
            pos_id_to_source[source_id] = source_id

            name = _strip_html(str(p.get("product") or ""))
            if name:
                name_to_source[re.sub(r"\s+", " ", name.lower().strip())] = source_id
            sku = str(p.get("sku") or "").strip()
            barcode = str(p.get("barcode") or "").strip()
            selling_price = _parse_price(p.get("selling_price")) or _parse_price(p.get("max_price"))
            unit_cost = _parse_price(p.get("max_price"))
            category_name = _strip_html(str(p.get("category") or "")).strip()
            category_source_id = category_name_to_source.get(category_name, "")

            products.append(
                {
                    "source_id": source_id,
                    "name": name,
                    "sku": sku,
                    "barcode": barcode,
                    "unit_cost": str(unit_cost),
                    "selling_price": str(selling_price),
                    "currency": "NGN",
                    "category_source_id": category_source_id,
                    "is_active": "true",
                }
            )

            for variation in p.get("variations") or []:
                variation_id = variation.get("id")
                if variation_id is None:
                    continue
                price_override_raw = variation.get("sell_price_inc_tax") or variation.get("default_sell_price")
                cost_override_raw = variation.get("default_purchase_price") or variation.get("purchase_price")
                price_override = _parse_price(price_override_raw) if price_override_raw is not None else None
                cost_override = _parse_price(cost_override_raw) if cost_override_raw is not None else None
                attr_parts = []
                if variation.get("name") and variation["name"] not in ("DUMMY", "Default"):
                    attr_parts.append(f"variation:{variation['name']}")
                variants.append(
                    {
                        "source_id": str(variation_id),
                        "product_source_id": source_id,
                        "name": str(variation.get("name") or "Default"),
                        "sku": str(variation.get("sub_sku") or "").strip(),
                        "barcode": str(variation.get("sub_sku_barcode") or "").strip(),
                        "attributes": ";".join(attr_parts),
                        "price_override": str(price_override) if price_override is not None else "",
                        "cost_price_override": str(cost_override) if cost_override is not None else "",
                    }
                )

        return products, variants, pos_id_to_source, name_to_source

    def _map_suppliers(self, raw_suppliers: list[dict]) -> list[dict]:
        out = []
        for c in raw_suppliers:
            contact_id = _extract_contact_id(c)
            if contact_id is None:
                continue
            name = _strip_html(str(c.get("name") or c.get("supplier") or "")).strip()
            if not name:
                continue
            out.append(
                {
                    "source_id": contact_id,
                    "name": name,
                    "email": str(c.get("email") or "").strip(),
                    "contact_person": str(c.get("contact_person") or "").strip(),
                    "mobile": str(c.get("mobile") or c.get("contact_no") or "").strip(),
                }
            )
        return out

    def _map_customers(self, raw_customers: list[dict]) -> list[dict]:
        out = []
        for c in raw_customers:
            contact_id = _extract_contact_id(c)
            if contact_id is None:
                continue
            name = _strip_html(str(c.get("name") or "")).strip()
            if not name:
                continue
            out.append(
                {
                    "source_id": contact_id,
                    "name": name,
                    "email": str(c.get("email") or "").strip(),
                    "contact_number": str(c.get("mobile") or c.get("contact_no") or "").strip(),
                }
            )
        return out

    def _map_locations(self, raw_locations: list) -> list[dict]:
        """Real rows come back as plain positional arrays, not keyed
        objects — confirmed live column order via the `/business-location`
        page's own `<th>` headers: Name, Location ID, Landmark, City, Zip
        Code, State, Country, Price Group, Invoice scheme, Invoice layout
        (POS), Invoice layout (sale), Action. The numeric location id only
        appears inside the Action cell's edit-link href. Also accepts a
        keyed-object shape (id/name/location_id) for forward-compat with
        any API version that returns one.
        """
        out = []
        for loc in raw_locations:
            if isinstance(loc, dict):
                loc_id = loc.get("id")
                if loc_id is None:
                    continue
                out.append(
                    {
                        "source_id": str(loc_id),
                        "name": _strip_html(str(loc.get("name") or "")).strip(),
                        "location_code": str(
                            loc.get("location_id") or loc.get("location_code") or ""
                        ).strip(),
                    }
                )
                continue

            if not isinstance(loc, list) or len(loc) < 12:
                continue
            name = _strip_html(str(loc[0] or "")).strip()
            location_code = _strip_html(str(loc[1] or "")).strip()
            action_html = str(loc[11] or "")
            m = re.search(r"/business-location/(\d+)/edit", action_html)
            if not m or not name:
                continue
            out.append(
                {
                    "source_id": m.group(1),
                    "name": name,
                    "location_code": location_code,
                }
            )
        return out

    async def _map_sales(
        self,
        client: _POSAPIClient,
        raw_sells: list[dict],
        pos_id_to_source: dict[str, str],
        name_to_source: dict[str, str],
        known_customer_ids: set[str],
    ) -> list[dict]:
        sales: list[dict] = []
        for sell_header in raw_sells:
            sell_id = _extract_pos_id(sell_header, "sells")
            if not sell_id:
                continue

            sale_date = _parse_date(str(sell_header.get("transaction_date") or ""))
            if sale_date is None:
                continue

            html = await anyio.to_thread.run_sync(client.fetch_sell_detail_html, sell_id)
            if not html.strip():
                continue

            lines = _parse_sell_lines_from_html(html, pos_id_to_source, name_to_source)
            if not lines:
                continue

            # Real sells JSON has no numeric location_id field — only
            # `business_location`, a display name. Known limitation: for a
            # multi-location business whose locations happen to share the
            # same display name (confirmed on the live instance this was
            # built against — two branches both named after the business,
            # differentiated only by location_code), this name can't
            # disambiguate which physical location made the sale. Left
            # unresolved rather than guessing; transform_sales() already
            # falls back to a "default location" warning for this case.
            location_name = _strip_html(str(sell_header.get("business_location") or "")).strip()
            # Real contact_id is a display code (e.g. "CO0006"), not the
            # numeric id customers/suppliers are keyed by via
            # _extract_contact_id() — it can't be resolved to a customer
            # source_id from the sell header alone.
            customer_source_id = ""
            payment_method = str(sell_header.get("payment_type") or "").strip().lower() or "other"

            for line in lines:
                sales.append(
                    {
                        # The parent sell's own POS id, not a per-line
                        # identifier — every line of a multi-product sell
                        # shares this value. transform_sales() carries it
                        # through as Sale.pos_id so sell_returns can later
                        # resolve which sell a return applies against (see
                        # _map_sell_returns / load_sell_returns).
                        "source_id": sell_id,
                        "product_source_id": line["product_source_id"],
                        "variant_source_id": "",
                        "customer_source_id": customer_source_id if customer_source_id in known_customer_ids else "",
                        "quantity": str(line["quantity"]),
                        "unit_price": str(line["unit_price"]),
                        "sale_date": sale_date.isoformat(),
                        "currency": "NGN",
                        "channel": _CHANNEL_FALLBACK,
                        "payment_method": payment_method,
                        "location_name": location_name,
                    }
                )
        return sales

    # ------------------------------------------------------------------
    # Purchase orders
    # ------------------------------------------------------------------

    async def _map_purchase_orders(
        self,
        client: _POSAPIClient,
        raw_purchases: list[dict],
        raw_products: list[dict],
        raw_suppliers: list[dict],
    ) -> list[dict]:
        # Built from raw_products (unfiltered), not _map_products()'s
        # active-only output — a historical purchase can reference a
        # since-discontinued (is_inactive/not_for_selling) product, and
        # that line must still resolve instead of silently vanishing.
        sku_to_source = {
            str(p["sku"]).strip(): str(p["id"])
            for p in raw_products
            if p.get("sku") and p.get("id") is not None
        }
        supplier_name_to_source: dict[str, str] = {}
        for s in raw_suppliers:
            sid = _extract_contact_id(s)
            if sid is None:
                continue
            name = _strip_html(str(s.get("name") or s.get("supplier") or "")).strip()
            if name:
                supplier_name_to_source[name.lower()] = sid

        rows: list[dict] = []
        for header in raw_purchases:
            purchase_id = _extract_pos_id(header, "purchases")
            if not purchase_id:
                continue

            ref_no = str(header.get("ref_no") or f"POS-PO-{purchase_id}").strip()
            order_date = _parse_date(str(header.get("transaction_date") or ""))
            supplier_name = _strip_html(str(header.get("name") or "")).strip()
            supplier_source_id = supplier_name_to_source.get(supplier_name.lower(), "")

            html = await anyio.to_thread.run_sync(client.fetch_purchase_print_html, purchase_id)
            if not html.strip():
                continue

            lines = _parse_purchase_lines_from_html(html, sku_to_source)
            if not lines:
                continue

            for line in lines:
                # unit_cost_ngn -> USD: the extractor has no DB session (it
                # only ever sees base_url + credentials), so it can't call
                # src.fx.service.get_live_usdngn_rate() the way
                # pos_migrate.py does. Uses the same fixed fallback rate
                # pos_migrate.py falls back to on a failed live-rate fetch.
                # Known limitation: this approximates every historical
                # purchase at one rate rather than the true rate on each
                # purchase's actual date — landed cost/COGS accuracy for
                # older purchases will drift from reality. Flagged as a
                # follow-up (fetch a dated historical rate) rather than
                # solved here.
                unit_cost_usd = (line["unit_cost_ngn"] / _FALLBACK_NGN_USD_RATE).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )
                rows.append(
                    {
                        "source_id": ref_no,
                        # The purchase's own numeric POS id, distinct from
                        # ref_no (the human-facing reference used above for
                        # line-grouping) — purchase_returns reference the
                        # original purchase by this numeric id, not ref_no,
                        # matching pos_sync's own pos_id convention.
                        "pos_id": purchase_id,
                        "supplier_source_id": supplier_source_id,
                        "supplier_name": supplier_name or "",
                        "product_source_id": line["product_source_id"],
                        "variant_source_id": "",
                        "location_source_id": "",
                        "quantity": str(line["quantity"]),
                        "unit_cost": str(unit_cost_usd),
                        "currency": "USD",
                        "order_date": order_date.isoformat() if order_date else "",
                        "fx_rate": str(_FALLBACK_NGN_USD_RATE),
                    }
                )
        return rows

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------

    def _map_expense_categories(
        self, raw_categories: list[dict]
    ) -> tuple[list[dict], dict[str, str]]:
        out = []
        id_to_source: dict[str, str] = {}
        for c in raw_categories:
            cat_id = c.get("id")
            if cat_id is None:
                continue
            source_id = str(cat_id)
            id_to_source[source_id] = source_id
            out.append(
                {
                    "source_id": source_id,
                    "name": _strip_html(str(c.get("name") or "")).strip(),
                    "description": _strip_html(str(c.get("description") or "")).strip(),
                }
            )
        return out, id_to_source

    def _map_expenses(
        self, raw_expenses: list[dict], category_id_to_source: dict[str, str]
    ) -> list[dict]:
        # Field names ported from pos_migrate.py's proven expense mapping
        # (amount/final_total, expense_date/transaction_date,
        # note/additional_notes fallback pairs) — unconfirmed against this
        # extractor's own live-probe target, whose real business had zero
        # expense records at the time this was built to verify against.
        out = []
        for e in raw_expenses:
            exp_date = _parse_date(
                str(e.get("expense_date") or e.get("transaction_date") or "")
            )
            if exp_date is None:
                continue

            source_id = _extract_pos_id(e, "expenses") or ""
            amount = _parse_price(e.get("amount") or e.get("final_total"))
            cat_id = e.get("expense_category_id")
            category_source_id = (
                category_id_to_source.get(str(cat_id), "") if cat_id is not None else ""
            )

            out.append(
                {
                    "source_id": source_id,
                    "category_source_id": category_source_id,
                    "ref_no": str(e.get("ref_no") or "").strip(),
                    "amount": str(amount),
                    "currency": "NGN",
                    "payment_method": str(e.get("payment_method") or "").strip().lower()
                    or "other",
                    "note": _strip_html(
                        str(e.get("note") or e.get("additional_notes") or "")
                    ).strip(),
                    "expense_date": exp_date.isoformat(),
                    "location_source_id": "",
                }
            )
        return out

    # ------------------------------------------------------------------
    # Stock adjustments
    # ------------------------------------------------------------------

    async def _map_stock_adjustments(
        self,
        client: _POSAPIClient,
        raw_adjustments: list[dict],
        pos_id_to_source: dict[str, str],
    ) -> list[dict]:
        rows: list[dict] = []
        for header in raw_adjustments:
            adj_id = _extract_pos_id(header, "stock-adjustments")
            if not adj_id:
                continue

            adjustment_type = _strip_html(str(header.get("adjustment_type") or "")).strip()
            reason = _strip_html(str(header.get("additional_notes") or "")).strip()
            adjustment_date = _parse_date(str(header.get("transaction_date") or ""))
            source_id = str(header.get("ref_no") or f"POS-ADJ-{adj_id}").strip()

            html = await anyio.to_thread.run_sync(
                client.fetch_stock_adjustment_detail_html, adj_id
            )
            if not html.strip():
                continue

            lines = _parse_stock_adjustment_lines_from_html(html, pos_id_to_source)
            if not lines:
                continue

            # UltimatePOS's Stock Adjustment module is exclusively a
            # loss/write-off tool — "Normal" and "Abnormal" are both
            # deduction categories (breakage, theft, wastage); the only
            # addition case is "Opening Stock" (initial stock seeding). The
            # confirmed live Quantity cell itself carries no sign, so the
            # sign has to be inferred from adjustment_type rather than
            # taken verbatim — passing the raw positive quantity through
            # unconditionally (as pos_migrate.py's reference implementation
            # did) would silently record every real loss as a stock gain.
            is_addition = "open" in adjustment_type.lower()
            for line in lines:
                signed_quantity = line["quantity"] if is_addition else -line["quantity"]
                rows.append(
                    {
                        "source_id": source_id,
                        "product_source_id": line["product_source_id"],
                        "variant_source_id": "",
                        "quantity_change": str(signed_quantity),
                        "adjustment_type": adjustment_type,
                        "reason": reason,
                        "adjustment_date": (
                            adjustment_date.isoformat() if adjustment_date else ""
                        ),
                    }
                )
        return rows

    # ------------------------------------------------------------------
    # Returns
    # ------------------------------------------------------------------
    #
    # Field names below are ported from pos_migrate.py's proven returns
    # mapping (steps 3i/3j) rather than independently confirmed against
    # this extractor's own live-probe target: Modish Standard has zero
    # real sell/purchase returns today (confirmed live), so there was no
    # real record to verify field names or the /sell-return, /purchase-
    # return response shape against — same "ported, unconfirmed" caveat
    # already applied to expenses. Both entities are header-only
    # aggregates (a total, not per-product line items) — matching both
    # pos_migrate.py's own prior handling AND ModishLog's SellReturn/
    # PurchaseReturn models, which have no line-item table of their own.

    def _map_sell_returns(self, raw_returns: list[dict]) -> list[dict]:
        out: list[dict] = []
        for sr in raw_returns:
            sale_source_id = str(
                sr.get("parent_sell_id") or sr.get("invoice_id") or ""
            ).strip()
            if not sale_source_id:
                continue
            return_date = _parse_date(
                str(sr.get("transaction_date") or sr.get("return_date") or "")
            )
            if return_date is None:
                continue
            sr_id = _extract_pos_id(sr, "sell-return")
            ref_no = str(sr.get("ref_no") or "").strip() or (
                f"SR-{sr_id}" if sr_id else ""
            )
            out.append(
                {
                    "sale_source_id": sale_source_id,
                    "return_date": return_date.isoformat(),
                    "total_amount": str(_parse_price(sr.get("final_total"))),
                    "amount_paid": str(_parse_price(sr.get("total_amount_paid"))),
                    "ref_no": ref_no,
                    "notes": "Imported from UltimatePOS",
                }
            )
        return out

    def _map_purchase_returns(self, raw_returns: list[dict]) -> list[dict]:
        out: list[dict] = []
        for pr in raw_returns:
            purchase_source_id = str(pr.get("purchase_id") or "").strip()
            if not purchase_source_id:
                continue
            return_date = _parse_date(str(pr.get("transaction_date") or ""))
            if return_date is None:
                continue
            ref_no = str(pr.get("ref_no") or "").strip()
            total_ngn = _parse_price(pr.get("final_total"))
            paid_ngn = _parse_price(pr.get("total_amount_paid"))
            # Same fixed fallback FX rate used for purchase_orders — see
            # that method's comment for why the extractor can't fetch a
            # live/dated rate here.
            total_usd = (total_ngn / _FALLBACK_NGN_USD_RATE).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            paid_usd = (paid_ngn / _FALLBACK_NGN_USD_RATE).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            out.append(
                {
                    "purchase_source_id": purchase_source_id,
                    "return_date": return_date.isoformat(),
                    "total_amount": str(total_usd),
                    "amount_paid": str(paid_usd),
                    "ref_no": ref_no,
                    "notes": "Imported from UltimatePOS",
                }
            )
        return out


def _parse_purchase_lines_from_html(
    html: str, sku_to_source: dict[str, str]
) -> list[dict]:
    """Extract purchase line items from a UltimatePOS purchase print HTML.

    Confirmed live column order: [#, Product Name, SKU, Purchase Quantity,
    Unit Cost (Before Discount), Discount Percent, Unit Cost (Before Tax),
    Subtotal (Before Tax), Tax, Unit Cost Price (After Tax), Subtotal] —
    matches pos_migrate.py's proven `_parse_purchase_lines_from_html`
    column indices (col[2]=SKU, col[3]=quantity, col[4]=unit cost).
    """
    lines: list[dict] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 5:
            continue

        sku = _strip_html(cells[2]).strip()
        product_source_id = sku_to_source.get(sku)
        if not product_source_id:
            continue

        qty_m = re.search(r'data-is_quantity="true"[^>]*>([^<]+)', cells[3], re.IGNORECASE)
        qty_raw = qty_m.group(1).strip() if qty_m else _strip_html(cells[3])
        quantity = _parse_qty(qty_raw)
        if quantity <= 0:
            continue

        unit_cost_ngn = _parse_price(_strip_html(cells[4]).strip())

        lines.append(
            {
                "product_source_id": product_source_id,
                "quantity": quantity,
                "unit_cost_ngn": unit_cost_ngn,
            }
        )
    return lines


def _parse_stock_adjustment_lines_from_html(
    html: str, pos_id_to_source: dict[str, str]
) -> list[dict]:
    """Extract stock-adjustment line items from a UltimatePOS stock
    adjustment detail HTML fragment.

    Confirmed live column order: [Product, Quantity, Unit Price, Subtotal].
    Unlike the sell/purchase line HTML, these cells are plain text with no
    data-* span wrappers, and the product cell carries the POS numeric
    product id in trailing parentheses (e.g. "Off White MDF UV (301406)")
    rather than a bare trailing number.
    """
    lines: list[dict] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 2:
            continue

        product_text = _strip_html(cells[0]).strip()
        id_m = re.search(r"\((\d+)\)\s*$", product_text)
        if not id_m:
            continue
        product_source_id = pos_id_to_source.get(id_m.group(1))
        if not product_source_id:
            continue

        quantity = _parse_qty(_strip_html(cells[1]).strip())
        if quantity <= 0:
            continue

        lines.append({"product_source_id": product_source_id, "quantity": quantity})
    return lines
