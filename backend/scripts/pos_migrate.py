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
import os
import re
import sys
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
from src.sales.models import Sale, SaleAuditEntry, SaleBulkUploadJob, SellReturn
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
        with self._opener.open(req) as resp:
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

    def fetch_contacts(self, contact_type: str = "supplier") -> list[dict]:
        try:
            data = self._json_get(f"/contacts?type={contact_type}&per_page=500")
            return data.get("data", [])
        except Exception as exc:
            log.warning("pos_contacts_fetch_failed", type=contact_type, error=str(exc))
            return []


# ── Helpers ──────────────────────────────────────────────────────────────────


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
    log.info("pos_fetch_products_start")
    client = POSClient()
    client.login()

    pos_products = client.fetch_products()
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
    pos_suppliers = client.fetch_contacts("supplier")
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

    # ── 3g. Sales — skipped: POS /sells returns invoice totals only, not
    #    per-product line items. Importing header-level sales would pin every
    #    transaction to an arbitrary product, producing misleading analytics.
    #    TODO: implement a per-line-item fetch once the POS API endpoint is mapped.
    pos_sell_count = len(client.fetch_sells())
    log.warning(
        "sales_import_skipped",
        reason="no per-line-item product mapping available",
        pos_sell_rows=pos_sell_count,
    )

    # ── Final commit ─────────────────────────────────────────────────────────
    await session.commit()

    log.info(
        "migration_complete",
        products=len(product_map),
        suppliers=len(supplier_map),
        sales=0,
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
