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
from decimal import Decimal
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


_CHANNEL_FALLBACK = "retail"


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

    def fetch_categories(self) -> list[dict]:
        return self._json_list("/categories?per_page=500")

    def fetch_contacts(self, contact_type: str) -> list[dict]:
        return self._json_list(f"/contacts?type={contact_type}&per_page=500")

    def fetch_business_locations(self) -> list[dict]:
        return self._json_list("/business-locations?per_page=200")

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

        raw_products, raw_categories, raw_suppliers, raw_customers, raw_locations = await anyio.to_thread.run_sync(
            self._fetch_reference_data, client
        )

        categories = self._map_categories(raw_categories)
        products, variants, pos_id_to_source, name_to_source = self._map_products(raw_products)
        suppliers = self._map_suppliers(raw_suppliers)
        customers = self._map_customers(raw_customers)
        locations = self._map_locations(raw_locations)
        known_location_ids = {row["source_id"] for row in locations}
        known_customer_ids = {row["source_id"] for row in customers}

        raw_sells = await anyio.to_thread.run_sync(client.fetch_sells)
        sales = await self._map_sales(
            client, raw_sells, pos_id_to_source, name_to_source, known_location_ids, known_customer_ids
        )

        result: ExtractedData = {
            "product_categories": categories,
            "products": products,
            "product_variants": variants,
            "suppliers": suppliers,
            "customers": customers,
            "business_locations": locations,
            "sales": sales,
        }
        logger.info(
            "ultimatepos_api_extraction_complete",
            **{entity: len(rows) for entity, rows in result.items()},
        )
        return result

    def _fetch_reference_data(self, client: _POSAPIClient) -> tuple[list, list, list, list, list]:
        products = client.fetch_products()
        categories = client.fetch_categories()
        suppliers = client.fetch_contacts("supplier")
        customers = client.fetch_contacts("customer")
        locations = client.fetch_business_locations()
        return products, categories, suppliers, customers, locations

    # ------------------------------------------------------------------
    # test_connection()
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict:
        logger.info("ultimatepos_api_test_connection_started")
        client = self._build_client()
        await self._login(client)

        raw_products, raw_categories, raw_suppliers, raw_customers, raw_locations = await anyio.to_thread.run_sync(
            self._fetch_reference_data, client
        )
        raw_sells = await anyio.to_thread.run_sync(client.fetch_sells)

        active_products = [p for p in raw_products if not p.get("is_inactive") and not p.get("not_for_selling")]

        sell_dates = [
            _parse_date(str(s.get("transaction_date") or ""))
            for s in raw_sells
        ]
        sell_dates = [d for d in sell_dates if d is not None]

        counts = {
            "product_categories": len(raw_categories),
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

    def _map_categories(self, raw_categories: list[dict]) -> list[dict]:
        out = []
        for c in raw_categories:
            cat_id = c.get("id")
            if cat_id is None:
                continue
            parent_id = c.get("parent_id")
            out.append(
                {
                    "source_id": str(cat_id),
                    "name": _strip_html(str(c.get("name") or "")).strip(),
                    "description": _strip_html(str(c.get("description") or "")).strip() or "",
                    "parent_source_id": str(parent_id) if parent_id is not None else "",
                }
            )
        return out

    def _map_products(
        self, raw_products: list[dict]
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
            category_id = p.get("category_id")

            products.append(
                {
                    "source_id": source_id,
                    "name": name,
                    "sku": sku,
                    "barcode": barcode,
                    "unit_cost": str(unit_cost),
                    "selling_price": str(selling_price),
                    "currency": "NGN",
                    "category_source_id": str(category_id) if category_id is not None else "",
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
            contact_id = c.get("id")
            if contact_id is None:
                continue
            name = _strip_html(str(c.get("name") or c.get("supplier") or "")).strip()
            if not name:
                continue
            out.append(
                {
                    "source_id": str(contact_id),
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
            contact_id = c.get("id")
            if contact_id is None:
                continue
            name = _strip_html(str(c.get("name") or "")).strip()
            if not name:
                continue
            out.append(
                {
                    "source_id": str(contact_id),
                    "name": name,
                    "email": str(c.get("email") or "").strip(),
                    "contact_number": str(c.get("mobile") or c.get("contact_no") or "").strip(),
                }
            )
        return out

    def _map_locations(self, raw_locations: list[dict]) -> list[dict]:
        out = []
        for loc in raw_locations:
            loc_id = loc.get("id")
            if loc_id is None:
                continue
            out.append(
                {
                    "source_id": str(loc_id),
                    "name": _strip_html(str(loc.get("name") or "")).strip(),
                    "location_code": str(loc.get("location_id") or loc.get("location_code") or "").strip(),
                }
            )
        return out

    async def _map_sales(
        self,
        client: _POSAPIClient,
        raw_sells: list[dict],
        pos_id_to_source: dict[str, str],
        name_to_source: dict[str, str],
        known_location_ids: set[str],
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

            raw_location_id = sell_header.get("location_id")
            location_source_id = str(raw_location_id) if raw_location_id is not None else ""
            raw_contact_id = sell_header.get("contact_id")
            customer_source_id = str(raw_contact_id) if raw_contact_id is not None else ""
            payment_method = str(sell_header.get("payment_type") or "").strip().lower() or "other"

            for line in lines:
                sales.append(
                    {
                        "product_source_id": line["product_source_id"],
                        "variant_source_id": "",
                        "customer_source_id": customer_source_id if customer_source_id in known_customer_ids else "",
                        "quantity": str(line["quantity"]),
                        "unit_price": str(line["unit_price"]),
                        "sale_date": sale_date.isoformat(),
                        "currency": "NGN",
                        "channel": _CHANNEL_FALLBACK,
                        "payment_method": payment_method,
                        "location_name": location_source_id if location_source_id in known_location_ids else "",
                    }
                )
        return sales
