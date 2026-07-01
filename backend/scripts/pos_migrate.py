#!/usr/bin/env python3
"""
POS → ModishLog local dev DB migration script.

Pulls live data from https://pos.virtualrx.com.ng (UltimatePOS/Laravel) and
populates the local Docker Postgres database.

Usage (inside docker compose exec backend):
  python scripts/pos_migrate.py --step=verify   # check POS connectivity + counts
  python scripts/pos_migrate.py --step=wipe     # clear all local data, keep schema
  python scripts/pos_migrate.py --step=migrate  # pull POS data → local DB
  python scripts/pos_migrate.py                 # run all 3 steps in sequence
"""

import argparse
import asyncio
import math
import os
import re
import sys
import threading
import uuid
from datetime import date, datetime
from decimal import Decimal
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import urlencode
from urllib.request import (
    HTTPCookieProcessor,
    Request,
    build_opener,
)

# Allow importing src.* when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json

import structlog
from passlib.context import CryptContext
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.ai_engine.models import (
    AIRecommendation,
    ReorderConfig,
    ReorderSuggestion,
    USDPurchaseSchedule,
    USDStrategyConfig,
)
from src.auth.models import PasswordResetToken, RefreshToken, User, UserRole
from src.cashflow.models import (
    CashflowProjection,
    DSCRRecord,
    LoanObligation,
    LoanPaymentSchedule,
    OperatingCost,
    ProjectionAssumptions,
    StressScenario,
    TriageRecord,
)
from src.customers.models import Customer
from src.fx.models import (
    FXAlert,
    FXExposure,
    FXExposureConfig,
    FXForecast,
    FXRate,
    FXSimulationRun,
)
from src.inventory.models import (
    InventoryBatch,
    InventoryLevel,
    LowStockAlert,
    MovementType,
    StockMovement,
)
from src.invoice_schemes.models import InvoiceScheme
from src.locations.models import BusinessLocation
from src.orders.models import (
    OrderLineItem,
    OrderPayment,
    OrderPaymentStatus,
    OrderStatus,
    OrderStatusHistory,
    PurchaseOrder,
    PurchaseReturn,
)
from src.pricing.models import (
    CrossSubsidyAnalysis,
    DemandElasticity,
    MarginTarget,
    PriceSuggestion,
    PricingRecommendation,
    PricingScenario,
    ProductMixTarget,
)
from src.products.models import PriceHistory, Product, ProductCategory
from src.sales.models import Sale, SaleAuditEntry, SaleBulkUploadJob, SaleChannel, SaleStatus, SellReturn
from src.settings.models import UserApiKey, UserPreferences
from src.stockcount.models import StockCount, StockCountItem
from src.suppliers.models import Supplier, SupplierProduct

log = structlog.get_logger()


def _require_env(name: str) -> str:
    raise RuntimeError(
        f"Required environment variable {name!r} is not set. "
        f"Set it before running this script, e.g.:\n"
        f"  export {name}=<value>"
    )


# ── POS connection config ────────────────────────────────────────────────────

POS_URL = os.environ.get("POS_URL", "https://pos.virtualrx.com.ng")
POS_USER: str | None = os.environ.get("POS_USERNAME")
POS_PASS: str | None = os.environ.get("POS_PASSWORD")

# ── Local DB (set by Docker Compose) ────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://modishlog:modishlog_dev@db/modishlog",
)

# ── Seed user ────────────────────────────────────────────────────────────────

ADMIN_EMAIL = "soji.soyoye@gmail.com"
ADMIN_FULL_NAME = "Soji Soyoye"
ADMIN_PASSWORD = "ModishLog2026!"  # local dev only — change on first login

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── POS auth client (sync http — runs before asyncio) ────────────────────────


class POSClient:
    """Cookie-based POS client using urllib (no extra deps)."""

    def __init__(self) -> None:
        self._jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._jar))

    def _get(self, path: str, headers: dict[str, str] | None = None) -> str:
        req = Request(f"{POS_URL}{path}", headers=headers or {})
        with self._opener.open(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _post(self, path: str, data: dict[str, str], headers: dict[str, str] | None = None) -> tuple[int, str]:
        body = urlencode(data).encode()
        req = Request(
            f"{POS_URL}{path}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
        )
        req.get_method = lambda: "POST"  # type: ignore[method-assign]
        try:
            with self._opener.open(req, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            # urllib raises on non-2xx — read the redirect location from the jar
            return 302, str(exc)

    def _csrf(self, path: str) -> str:
        html = self._get(path)
        m = re.search(r'name="_token"\s+value="([^"]+)"', html)
        if not m:
            m = re.search(r'content="([^"]+)"\s+name="csrf-token"', html)
        if not m:
            raise RuntimeError(f"CSRF token not found at {path}")
        return m.group(1)

    def login(self) -> None:
        if not POS_USER or not POS_PASS:
            _require_env("POS_USERNAME" if not POS_USER else "POS_PASSWORD")
        csrf = self._csrf("/login")
        status, body = self._post("/login", {"_token": csrf, "username": POS_USER, "password": POS_PASS})
        if "home" not in body and status not in (200, 302):
            raise RuntimeError(f"POS login failed — status {status}")
        log.info("pos_login_ok", url=POS_URL, user=POS_USER)

    def _json_get(self, path: str) -> Any:
        html = self._get(path, {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
        return json.loads(html)

    def fetch_products(self) -> list[dict]:
        data = self._json_get("/products?per_page=1000")
        return data.get("data", [])

    def fetch_sells(self) -> list[dict]:
        """Fetch sales from POS. UltimatePOS v5 uses /sells endpoint."""
        try:
            data = self._json_get("/sells?per_page=2000")
            return data.get("data", [])
        except Exception as exc:
            log.warning("pos_sells_fetch_failed", error=str(exc))
            return []

    def fetch_purchases(self) -> list[dict]:
        try:
            data = self._json_get("/purchases?per_page=2000")
            return data.get("data", [])
        except Exception as exc:
            log.warning("pos_purchases_fetch_failed", error=str(exc))
            return []

    def fetch_sell_detail_html(self, sell_id: str | int) -> str:
        """Fetch sell receipt as raw HTML (blocking; caller wraps with asyncio.wait_for)."""
        try:
            html = self._get(f"/sells/{sell_id}")
            if html and 'action="/login"' in html and '_token' in html:
                log.info("pos_session_expired_reauth", sell_id=sell_id)
                self.login()
                html = self._get(f"/sells/{sell_id}")
            return html
        except Exception as exc:
            log.warning("pos_sell_html_failed", sell_id=sell_id, error=str(exc))
            return ""

    def fetch_purchase_detail(self, purchase_id: str | int) -> dict:
        try:
            return self._json_get(f"/purchases/{purchase_id}")
        except Exception as exc:
            log.warning("pos_purchase_detail_fetch_failed", purchase_id=purchase_id, error=str(exc))
            return {}

    def fetch_contacts(self, contact_type: str = "supplier") -> list[dict]:
        try:
            data = self._json_get(f"/contacts?type={contact_type}&per_page=500")
            return data.get("data", [])
        except Exception as exc:
            log.warning("pos_contacts_fetch_failed", type=contact_type, error=str(exc))
            return []


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_sell_date_from_html(html: str) -> date | None:
    """Extract first date from UltimatePOS receipt HTML."""
    for pattern in (
        r"(\d{2}/\d{2}/\d{4})",   # 07/01/2026
        r"(\d{4}-\d{2}-\d{2})",   # 2026-01-07
        r"(\d{2}-\d{2}-\d{4})",   # 07-01-2026
    ):
        m = re.search(pattern, html)
        if m:
            raw = m.group(1)
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
    return None


def _parse_sell_lines_from_html(
    html: str,
    pos_id_to_product: dict[str, uuid.UUID],
    name_to_product: dict[str, uuid.UUID],
) -> list[dict]:
    """
    Extract sell line items from a UltimatePOS receipt HTML page.

    UltimatePOS receipt table columns (8 <td>s per data row):
      [0] #  [1] Product name + pos_product_id  [2] Quantity  [3] Unit Price
      [4] Discount  [5] Tax  [6] Price inc. tax  [7] Subtotal

    Product cell: "Product Name\\n\\n273939\\n" — the pos product ID is the trailing number.
    Quantity: <span data-is_quantity="true">N.N</span>
    Currency values: <span data-currency_symbol="true">NNNN.NNNN</span>

    Returns list of dicts: product_id, quantity, unit_price, line_total.
    """
    lines = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 4:
            continue

        # ── Product cell (index 1) ─────────────────────────────────────────
        product_cell_text = _strip_html(cells[1]).strip()
        # POS product_id is an integer on its own line after the product name
        pos_id_m = re.search(r"\s+(\d{4,})\s*$", product_cell_text)
        product_id: uuid.UUID | None = None
        if pos_id_m:
            product_id = pos_id_to_product.get(pos_id_m.group(1))
        if not product_id:
            # Name-based fallback: strip the trailing number and normalise
            name_part = product_cell_text if not pos_id_m else product_cell_text[: pos_id_m.start()]
            norm = re.sub(r"\s+", " ", name_part.lower().strip())
            product_id = name_to_product.get(norm)
        if not product_id:
            continue

        # ── Quantity cell (index 2) ────────────────────────────────────────
        qty_m = re.search(
            r'data-is_quantity="true"[^>]*>([^<]+)</span>', cells[2], re.IGNORECASE
        )
        if qty_m:
            qty_float = float(qty_m.group(1).strip())
        else:
            raw_qty = re.search(r"([\d.]+)", _strip_html(cells[2]))
            qty_float = float(raw_qty.group(1)) if raw_qty else 0.0
        qty = max(1, math.ceil(qty_float)) if qty_float > 0 else 0
        if qty <= 0:
            continue

        # ── Unit price cell (index 3) ──────────────────────────────────────
        up_m = re.search(
            r'data-currency_symbol="true"[^>]*>([^<]+)</span>', cells[3], re.IGNORECASE
        )
        unit_price = _parse_price(up_m.group(1).strip()) if up_m else Decimal("0")

        # ── Subtotal cell (last cell — always index 7, but accept shorter) ─
        last_cell = cells[7] if len(cells) > 7 else cells[-1]
        st_m = re.search(
            r'data-currency_symbol="true"[^>]*>([^<]+)</span>', last_cell, re.IGNORECASE
        )
        line_total = (
            _parse_price(st_m.group(1).strip()) if st_m else unit_price * Decimal(str(qty))
        )

        lines.append({
            "product_id": product_id,
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": line_total or unit_price * Decimal(str(qty)),
        })

    return lines


def _extract_pos_id(item: dict, path_prefix: str) -> str | None:
    """Extract numeric ID from a DataTables row (direct id, DT_RowAttr href, or DT_RowId)."""
    if direct_id := item.get("id"):
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


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def _parse_price(raw: str) -> Decimal:
    digits = re.sub(r"[^\d.]", "", _strip_html(raw))
    if not digits:
        return Decimal("0")
    try:
        return Decimal(digits)
    except Exception:
        return Decimal("0")


def _parse_qty(raw: str) -> int:
    m = re.match(r"^([\d.]+)", str(raw))
    return int(float(m.group(1))) if m else 0


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _unique_slug(base: str, existing: set[str]) -> str:
    slug = _slugify(base)
    if slug not in existing:
        return slug
    counter = 2
    while f"{slug}-{counter}" in existing:
        counter += 1
    return f"{slug}-{counter}"


def _infer_category(name: str, pos_category: str) -> str:
    n = name.upper()
    cat = pos_category.upper()
    if re.search(r" BB($| )", n) or n.endswith("BB"):
        return "Block Boards"
    if "MDF UV" in n or "HDF UV" in n:
        return "UV Gloss Boards"
    if "EDGE TAPE" in cat or re.search(r"\d+\s*(MM|mm)", name):
        return "Edge Tapes"
    if "MARINE" in n:
        return "Marine Boards"
    if "HDF" in n:
        return "HDF Boards"
    if "MDF" in n:
        return "MDF Boards"
    if "DOOR" in n:
        return "Doors"
    if "PU" in n or "STONE" in n:
        return "PU Stone Panels"
    return "Accessories"


CATEGORY_DESCRIPTIONS = {
    "MDF Boards": "Medium-density fiberboard for furniture, cabinetry, and interior panelling.",
    "HDF Boards": "High-density fiberboard — ultra-smooth and strong for premium furniture.",
    "UV Gloss Boards": "UV-coated high-gloss boards for kitchens, wardrobes, and feature walls.",
    "Marine Boards": "Moisture-resistant boards for wet areas and outdoor applications.",
    "Edge Tapes": "Professional edge banding tapes — 21mm and 48mm, matt and gloss.",
    "Doors": "Interior and exterior doors in standard Nigerian sizes.",
    "PU Stone Panels": "Lightweight polyurethane stone-effect wall panels.",
    "Block Boards": "Solid block boards with timber core and veneer facing.",
    "Accessories": "Fittings, hardware and complementary products.",
}


# ── Step 1: VERIFY ───────────────────────────────────────────────────────────


def step_verify() -> None:
    log.info("pos_verify_start", pos_url=POS_URL)
    client = POSClient()
    client.login()

    products = client.fetch_products()
    log.info("pos_products_fetched", count=len(products))

    sells = client.fetch_sells()
    log.info("pos_sells_fetched", count=len(sells))

    purchases = client.fetch_purchases()
    log.info("pos_purchases_fetched", count=len(purchases))

    suppliers = client.fetch_contacts("supplier")
    log.info("pos_suppliers_fetched", count=len(suppliers))

    log.info(
        "pos_verify_complete",
        products=len(products),
        sells=len(sells),
        purchases=len(purchases),
        suppliers=len(suppliers),
    )


# ── Step 2: WIPE ─────────────────────────────────────────────────────────────

# Tables deleted leaf-first so FK constraints are not violated.
# Users are wiped last and recreated in migrate step.
# Topological delete order derived from pg_constraint FK graph.
# Every child table appears before the parent table(s) it references.
WIPE_ORDER = [
    # ── AI ──────────────────────────────────────────────────────────────────
    USDPurchaseSchedule,    # → usd_strategy_configs
    ReorderSuggestion,      # → purchase_orders, products
    AIRecommendation,       # → users
    ReorderConfig,          # → users
    USDStrategyConfig,      # → users
    # ── Pricing ─────────────────────────────────────────────────────────────
    CrossSubsidyAnalysis,
    DemandElasticity,       # → products
    PriceSuggestion,        # → products
    PricingRecommendation,  # → products, users
    PricingScenario,        # → products, users
    MarginTarget,           # → products, product_categories, users
    ProductMixTarget,       # → product_categories
    # ── Cashflow ─────────────────────────────────────────────────────────────
    StressScenario,         # → cashflow_projections, users
    TriageRecord,
    DSCRRecord,
    LoanPaymentSchedule,    # → loan_obligations
    LoanObligation,
    OperatingCost,
    ProjectionAssumptions,
    CashflowProjection,     # → users
    # ── FX ──────────────────────────────────────────────────────────────────
    FXAlert,
    FXExposure,
    FXExposureConfig,
    FXForecast,
    FXRate,
    FXSimulationRun,
    # ── Stock counts ─────────────────────────────────────────────────────────
    StockCountItem,         # → order_line_items, stock_counts, products
    StockCount,             # → users
    # ── Sales ────────────────────────────────────────────────────────────────
    SaleAuditEntry,         # → sales, users
    SellReturn,             # → sales, users
    SaleBulkUploadJob,      # → users
    Sale,                   # → products, customers, business_locations, users
    # ── Orders + inventory (all reference purchase_orders) ───────────────────
    OrderPayment,           # → purchase_orders, users
    OrderStatusHistory,     # → purchase_orders, users
    InventoryBatch,         # → purchase_orders, products
    OrderLineItem,          # → purchase_orders, products
    PurchaseReturn,         # → purchase_orders, users
    PurchaseOrder,          # → business_locations, suppliers, users
    # ── Inventory ────────────────────────────────────────────────────────────
    LowStockAlert,          # → products
    StockMovement,          # → products, users
    InventoryLevel,         # → products
    # ── Product relations ────────────────────────────────────────────────────
    PriceHistory,           # → products, users
    SupplierProduct,        # → products, suppliers
    # ── Entities ─────────────────────────────────────────────────────────────
    Customer,               # → users
    Supplier,               # → users
    Product,                # → product_categories
    ProductCategory,        # self-ref; safe once products are gone
    BusinessLocation,       # → users; referenced by sales/orders already deleted
    # ── Settings / auth ──────────────────────────────────────────────────────
    InvoiceScheme,
    UserApiKey,
    UserPreferences,
    PasswordResetToken,
    RefreshToken,
    User,
]


async def step_wipe(session: AsyncSession) -> None:
    log.info("db_wipe_start")
    for model in WIPE_ORDER:
        result = await session.execute(delete(model))
        if result.rowcount > 0:
            log.info("table_cleared", table=model.__tablename__, rows=result.rowcount)
    await session.commit()
    log.info("db_wipe_complete")


# ── Step 3: MIGRATE ──────────────────────────────────────────────────────────


async def step_migrate(session: AsyncSession) -> None:
    log.info("migration_start")
    today = date.today()

    # ── 3a. Admin user ───────────────────────────────────────────────────────
    admin_id = uuid.uuid4()
    admin = User(
        id=admin_id,
        email=ADMIN_EMAIL,
        full_name=ADMIN_FULL_NAME,
        hashed_password=pwd_ctx.hash(ADMIN_PASSWORD),
        is_active=True,
        role=UserRole.ADMIN,
    )
    session.add(admin)
    await session.flush()
    log.info("admin_user_created", email=ADMIN_EMAIL)

    # ── 3b. Business location ────────────────────────────────────────────────
    location = BusinessLocation(
        id=uuid.uuid4(),
        name="Modish Standard — Lagos",
        location_code="LGA001",
        mobile="2347080227780",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        is_active=True,
        created_by=admin_id,
    )
    session.add(location)
    await session.flush()
    log.info("business_location_created", name=location.name)

    # ── 3c. Product categories ───────────────────────────────────────────────
    cat_map: dict[str, uuid.UUID] = {}
    for cat_name, cat_desc in CATEGORY_DESCRIPTIONS.items():
        cat_id = uuid.uuid4()
        cat = ProductCategory(
            id=cat_id,
            name=cat_name,
            description=cat_desc,
        )
        session.add(cat)
        cat_map[cat_name] = cat_id
    await session.flush()
    log.info("categories_created", count=len(cat_map))

    # ── 3d. Fetch POS products and insert ────────────────────────────────────
    # asyncio.wait_for + to_thread in Python 3.11 doesn't truly timeout blocking
    # C-extension code (SSL handshake) because wait_for waits for thread
    # cancellation. Use threading.Event.wait(timeout=N) which is guaranteed to
    # return after N seconds regardless of what the background thread is doing.
    def _pos(func, *args, timeout: int = 60):
        """Run a blocking POS HTTP call with a hard daemon-thread wall-clock timeout."""
        result_holder: list = [None]
        exc_holder: list = [None]
        done = threading.Event()

        def _worker():
            try:
                result_holder[0] = func(*args)
            except Exception as exc:
                exc_holder[0] = exc
            finally:
                done.set()

        threading.Thread(target=_worker, daemon=True).start()
        if not done.wait(timeout=timeout):
            raise TimeoutError(f"POS call {func.__name__} timed out after {timeout}s")
        if exc_holder[0]:
            raise exc_holder[0]
        return result_holder[0]

    log.info("pos_fetch_products_start")
    client = POSClient()
    try:
        _pos(client.login, timeout=300)  # allow up to 5 min for first SSL handshake
    except TimeoutError:
        raise RuntimeError("POS login timed out — is the server reachable?")

    pos_products: list[dict] = _pos(client.fetch_products, timeout=120)
    active_products = [p for p in pos_products if not p.get("is_inactive") and not p.get("not_for_selling")]
    log.info("pos_products_active", count=len(active_products))

    slug_set: set[str] = set()
    product_map: dict[str, uuid.UUID] = {}  # sku → modishlog product_id
    sku_to_pos: dict[str, dict] = {}

    for p in active_products:
        raw_name = p.get("product", "")
        name = _strip_html(raw_name)
        sku = str(p.get("sku", "")).strip()
        pos_category = str(p.get("category", ""))

        selling_price_raw = str(p.get("selling_price", "0"))
        max_price_raw = str(p.get("max_price", "0"))

        selling_price = _parse_price(selling_price_raw) or _parse_price(max_price_raw)
        unit_cost = _parse_price(max_price_raw)  # best proxy; POS hides supplier cost

        stock = _parse_qty(str(p.get("current_stock", "0")))
        cat_name = _infer_category(name, pos_category)
        cat_id = cat_map.get(cat_name, cat_map["Accessories"])

        slug = _unique_slug(name, slug_set)
        slug_set.add(slug)

        if not sku:
            sku = f"AUTO-{slug[:40]}"

        product_id = uuid.uuid4()
        product = Product(
            id=product_id,
            name=name,
            sku=sku,
            slug=slug,
            category_id=cat_id,
            unit_cost=unit_cost,
            selling_price=selling_price,
            currency="NGN",
            is_active=True,
        )
        session.add(product)
        product_map[sku] = product_id
        sku_to_pos[sku] = {"stock": stock, "pos_id": p.get("id"), "name": name}

        # Price history entry
        ph = PriceHistory(
            id=uuid.uuid4(),
            product_id=product_id,
            old_unit_cost=Decimal("0"),
            new_unit_cost=unit_cost,
            old_selling_price=Decimal("0"),
            new_selling_price=selling_price,
            reason="POS migration",
            effective_date=today,
            changed_by=admin_id,
        )
        session.add(ph)

    await session.flush()
    log.info("products_inserted", count=len(product_map))

    # ── 3e. Inventory levels ─────────────────────────────────────────────────
    for sku, product_id in product_map.items():
        stock = sku_to_pos[sku]["stock"]
        inv = InventoryLevel(
            id=uuid.uuid4(),
            product_id=product_id,
            quantity_on_hand=stock,
            quantity_reserved=0,
            low_stock_threshold=10,
        )
        session.add(inv)

        if stock > 0:
            mv = StockMovement(
                id=uuid.uuid4(),
                product_id=product_id,
                movement_type=MovementType.MANUAL_ADD,
                quantity_change=stock,
                quantity_before=0,
                quantity_after=stock,
                reason="POS migration — opening stock",
                performed_by=admin_id,
            )
            session.add(mv)

    await session.flush()
    log.info("inventory_levels_created", count=len(product_map))

    # ── 3f. Suppliers ────────────────────────────────────────────────────────
    pos_suppliers: list[dict] = _pos(client.fetch_contacts, "supplier", timeout=120)
    supplier_map: dict[str, uuid.UUID] = {}  # POS contact_id → modishlog supplier_id

    for contact in pos_suppliers:
        contact_id = str(contact.get("id", ""))
        sup_name = _strip_html(str(contact.get("name") or contact.get("supplier") or "Unknown"))
        email = contact.get("email") or None
        mobile = contact.get("mobile") or contact.get("contact_no") or None
        city = contact.get("city") or None
        state = contact.get("state") or None
        country = contact.get("country") or "Nigeria"
        address = contact.get("address_line_1") or contact.get("landmark") or None

        if not sup_name or sup_name == "Unknown":
            continue

        sup_id = uuid.uuid4()
        supplier = Supplier(
            id=sup_id,
            name=sup_name,
            email=email,
            mobile=mobile,
            city=city,
            state=state,
            country=country,
            address_line_1=address,
            is_active=True,
            created_by=admin_id,
        )
        session.add(supplier)
        supplier_map[contact_id] = sup_id

    await session.flush()
    log.info("suppliers_inserted", count=len(supplier_map))

    # ── 3g. Sales ────────────────────────────────────────────────────────────
    # Build lookup maps for product matching during sell-line parsing
    pos_id_to_product: dict[str, uuid.UUID] = {}
    name_to_product: dict[str, uuid.UUID] = {}
    for sku, pos_data in sku_to_pos.items():
        pos_id = pos_data.get("pos_id")
        if pos_id is not None:
            pos_id_to_product[str(pos_id)] = product_map[sku]
        name_norm = re.sub(r"\s+", " ", pos_data["name"].lower().strip())
        name_to_product[name_norm] = product_map[sku]

    pos_sells: list[dict] = _pos(client.fetch_sells, timeout=120)
    log.info("pos_sells_fetched", count=len(pos_sells))

    sales_created = 0
    sells_with_lines = 0
    for idx, sell_header in enumerate(pos_sells):
        sell_id = _extract_pos_id(sell_header, "sells")
        if not sell_id:
            log.warning("pos_sell_id_missing", row=sell_header)
            continue

        # Date comes from the list header (transaction_date field)
        date_raw = str(sell_header.get("transaction_date") or "")
        sale_date = _parse_date(date_raw) or today

        try:
            html = _pos(client.fetch_sell_detail_html, sell_id, timeout=30)
        except TimeoutError:
            log.warning("pos_sell_total_timeout", sell_id=sell_id)
            html = ""
        except Exception as exc:
            log.warning("pos_sell_html_failed", sell_id=sell_id, error=str(exc))
            html = ""
        if not html.strip():
            log.warning("pos_sell_html_empty", sell_id=sell_id)
            continue

        sell_lines = _parse_sell_lines_from_html(html, pos_id_to_product, name_to_product)
        if not sell_lines:
            log.warning("pos_sell_no_lines_parsed", sell_id=sell_id)
            continue

        sells_with_lines += 1
        transaction_uuid = uuid.uuid4()  # shared across line items of this sell

        for line in sell_lines:
            product_id = line["product_id"]
            quantity = line["quantity"]
            unit_price = line["unit_price"]
            line_total = line["line_total"]

            sale_id = uuid.uuid4()
            sale = Sale(
                id=sale_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                total_amount=line_total,
                currency="NGN",
                sale_date=sale_date,
                channel=SaleChannel.RETAIL,
                status=SaleStatus.COMPLETED,
                transaction_id=transaction_uuid,
                recorded_by=admin_id,
                location_id=location.id,
                notes="Imported from POS",
            )
            session.add(sale)

            mv = StockMovement(
                id=uuid.uuid4(),
                product_id=product_id,
                movement_type=MovementType.SALE_DEPLETION,
                quantity_change=-quantity,
                quantity_before=0,
                quantity_after=0,
                reference_id=sale_id,
                reference_type="sale",
                reason="POS migration — historical sale",
                performed_by=admin_id,
            )
            session.add(mv)
            sales_created += 1

        if (idx + 1) % 50 == 0:
            await session.flush()
            log.info(
                "sales_progress",
                processed=idx + 1,
                total=len(pos_sells),
                sells_with_lines=sells_with_lines,
                sales_created=sales_created,
            )

    await session.flush()
    log.info("sales_inserted", count=sales_created, sells_parsed=sells_with_lines)

    # ── 3h. Purchases ────────────────────────────────────────────────────────
    pos_purchases: list[dict] = _pos(client.fetch_purchases, timeout=120)
    log.info("pos_purchases_fetched", count=len(pos_purchases))

    orders_created = 0
    purchase_lines_created = 0

    for purchase_header in pos_purchases:
        purchase_id = _extract_pos_id(purchase_header, "purchases")
        if not purchase_id:
            log.warning("pos_purchase_id_missing", row=purchase_header)
            continue

        try:
            detail: dict = _pos(client.fetch_purchase_detail, purchase_id, timeout=60)
        except TimeoutError:
            log.warning("pos_purchase_total_timeout", purchase_id=purchase_id)
            continue
        except Exception as exc:
            log.warning("pos_purchase_detail_failed", purchase_id=purchase_id, error=str(exc))
            continue
        if not detail:
            continue

        purchase_data = detail.get("purchase") or detail
        purchase_lines = purchase_data.get("purchase_lines") or detail.get("purchase_lines") or []

        transaction_date_raw = str(
            purchase_data.get("transaction_date") or detail.get("transaction_date") or ""
        )
        order_date = _parse_date(transaction_date_raw) or today
        ref_no = str(
            purchase_data.get("ref_no") or purchase_data.get("invoice_no") or f"POS-PO-{purchase_id}"
        )

        pos_contact_id = str(purchase_data.get("contact_id") or "")
        supplier_id = supplier_map.get(pos_contact_id)
        supplier_name = "Unknown Supplier"
        for contact in pos_suppliers:
            if str(contact.get("id", "")) == pos_contact_id:
                supplier_name = _strip_html(str(contact.get("name") or "Unknown Supplier"))
                break

        final_total = _parse_price(str(purchase_data.get("final_total") or "0"))

        po = PurchaseOrder(
            id=uuid.uuid4(),
            order_number=ref_no,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            status=OrderStatus.DELIVERED,
            total_amount=final_total,
            currency="NGN",
            order_date=order_date,
            actual_delivery_date=order_date,
            payment_status=OrderPaymentStatus.PAID,
            created_by=admin_id,
            location_id=location.id,
            notes="Imported from POS",
        )
        session.add(po)
        await session.flush()  # need po.id for line items + stock movements

        for line in purchase_lines:
            pos_product_id = str(line.get("product_id", ""))
            product_id = pos_id_to_product.get(pos_product_id)
            if not product_id:
                log.warning(
                    "pos_purchase_line_product_not_found",
                    purchase_id=purchase_id,
                    pos_product_id=pos_product_id,
                )
                continue

            quantity = int(float(line.get("quantity") or 1))
            unit_cost = _parse_price(
                str(line.get("purchase_price") or line.get("unit_cost") or "0")
            )
            line_total = _parse_price(str(line.get("line_total") or "0")) or (
                unit_cost * Decimal(str(quantity))
            )
            if quantity <= 0:
                continue

            oli = OrderLineItem(
                id=uuid.uuid4(),
                order_id=po.id,
                product_id=product_id,
                quantity=quantity,
                unit_cost=unit_cost,
                unit_cost_ngn=unit_cost,
                line_total=line_total,
            )
            session.add(oli)

            mv = StockMovement(
                id=uuid.uuid4(),
                product_id=product_id,
                movement_type=MovementType.ORDER_RECEIVED,
                quantity_change=quantity,
                quantity_before=0,
                quantity_after=0,
                reference_id=po.id,
                reference_type="purchase_order",
                reason="POS migration — historical purchase",
                performed_by=admin_id,
            )
            session.add(mv)
            purchase_lines_created += 1

        orders_created += 1
        log.info("purchase_migrated", ref_no=ref_no, lines=purchase_lines_created)

    await session.flush()
    log.info("purchases_inserted", orders=orders_created, line_items=purchase_lines_created)

    # ── Final commit ─────────────────────────────────────────────────────────
    await session.commit()

    log.info(
        "migration_complete",
        products=len(product_map),
        suppliers=len(supplier_map),
        sales=sales_created,
        purchase_orders=orders_created,
        admin_email=ADMIN_EMAIL,
    )


def _parse_date(raw: str) -> date | None:
    """Try common POS date formats."""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


# ── Engine + runner ──────────────────────────────────────────────────────────


async def _run(step: str) -> None:
    # Structlog basic setup for script mode
    import logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )

    if step in ("verify", "all"):
        step_verify()

    if step in ("wipe", "all", "migrate"):
        engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            if step in ("wipe", "all"):
                await step_wipe(session)
            if step in ("migrate", "all"):
                await step_migrate(session)

        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="POS → ModishLog migration script")
    parser.add_argument(
        "--step",
        choices=["verify", "wipe", "migrate", "all"],
        default="all",
        help="Which step to run (default: all)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.step))


if __name__ == "__main__":
    main()
