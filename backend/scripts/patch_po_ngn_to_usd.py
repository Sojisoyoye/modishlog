#!/usr/bin/env python3
"""
One-off patch: convert migrated NGN purchase orders to USD.

The POS migration stored total_amount in NGN but the orders system expects USD.
This script fetches the live USD/NGN rate, divides all NGN amounts to USD,
and sets fx_rate_at_creation so the FX exposure panel works correctly.

Usage (inside docker compose exec backend):
  python scripts/patch_po_ngn_to_usd.py --dry-run   # preview without writing
  python scripts/patch_po_ngn_to_usd.py              # apply
"""

import argparse
import asyncio
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# All models must be imported so SQLAlchemy can resolve FK relationships.
from src.ai_engine.models import (  # noqa: F401
    AIRecommendation,
    ReorderConfig,
    ReorderSuggestion,
    USDPurchaseSchedule,
    USDStrategyConfig,
)
from src.auth.models import PasswordResetToken, RefreshToken, User, UserRole  # noqa: F401
from src.cashflow.models import (  # noqa: F401
    CashflowProjection,
    DSCRRecord,
    LoanObligation,
    LoanPaymentSchedule,
    OperatingCost,
    ProjectionAssumptions,
    StressScenario,
    TriageRecord,
)
from src.customers.models import Customer  # noqa: F401
from src.fx.models import (  # noqa: F401
    FXAlert,
    FXExposure,
    FXExposureConfig,
    FXForecast,
    FXRate,
    FXSimulationRun,
)
from src.fx.service import get_live_usdngn_rate
from src.inventory.models import (  # noqa: F401
    InventoryBatch,
    InventoryLevel,
    LowStockAlert,
    MovementType,
    StockMovement,
)
from src.invoice_schemes.models import InvoiceScheme  # noqa: F401
from src.locations.models import BusinessLocation  # noqa: F401
from src.orders.models import (
    OrderLineItem,
    OrderPayment,  # noqa: F401
    OrderPaymentStatus,  # noqa: F401
    OrderStatus,  # noqa: F401
    OrderStatusHistory,  # noqa: F401
    PurchaseOrder,
    PurchaseReturn,  # noqa: F401
)
from src.pricing.models import (  # noqa: F401
    CrossSubsidyAnalysis,
    DemandElasticity,
    MarginTarget,
    PriceSuggestion,
    PricingRecommendation,
    PricingScenario,
    ProductMixTarget,
)
from src.products.models import PriceHistory, Product, ProductCategory  # noqa: F401
from src.sales.models import (  # noqa: F401
    Sale,
    SaleAuditEntry,
    SaleBulkUploadJob,
    SaleChannel,
    SaleStatus,
    SellReturn,
)
from src.settings.models import UserApiKey, UserPreferences  # noqa: F401
from src.suppliers.models import Supplier, SupplierProduct  # noqa: F401

log = structlog.get_logger()

_SIX = Decimal("0.000001")


def _to_usd(ngn_amount: Decimal, rate: Decimal) -> Decimal:
    return (ngn_amount / rate).quantize(_SIX, rounding=ROUND_HALF_UP)


async def run(dry_run: bool, rate: Decimal | None = None) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        if rate is not None:
            usdngn_rate = rate
            log.info("fx_rate_from_cli", rate=str(usdngn_rate))
        else:
            try:
                usdngn_rate, fetched_at, cached = await get_live_usdngn_rate(session)
                log.info("fx_rate_obtained", rate=str(usdngn_rate), cached=cached)
            except Exception:
                usdngn_rate = Decimal("1600")
                log.warning("fx_rate_fallback", rate=str(usdngn_rate), reason="FX fetch failed")

        result = await session.execute(
            select(PurchaseOrder).where(PurchaseOrder.currency == "NGN")
        )
        orders = result.scalars().all()

        if not orders:
            log.info("no_ngn_orders_found — nothing to do")
            return

        log.info("ngn_orders_found", count=len(orders), dry_run=dry_run)

        total_items_patched = 0

        for po in orders:
            total_usd = _to_usd(po.total_amount, usdngn_rate)
            log.info(
                "order",
                order_number=po.order_number,
                total_ngn=str(po.total_amount),
                total_usd=str(total_usd),
                rate=str(usdngn_rate),
            )

            items_result = await session.execute(
                select(OrderLineItem).where(OrderLineItem.order_id == po.id)
            )
            items = items_result.scalars().all()

            for item in items:
                unit_cost_usd = _to_usd(item.unit_cost, usdngn_rate)
                line_total_usd = _to_usd(item.line_total, usdngn_rate)
                log.info(
                    "line_item",
                    product_id=str(item.product_id),
                    unit_cost_ngn=str(item.unit_cost),
                    unit_cost_usd=str(unit_cost_usd),
                    line_total_usd=str(line_total_usd),
                )
                if not dry_run:
                    # unit_cost_ngn already holds the original NGN value — keep it
                    item.unit_cost = unit_cost_usd
                    item.line_total = line_total_usd
                total_items_patched += 1

            if not dry_run:
                po.total_amount = total_usd
                po.currency = "USD"
                po.fx_rate_at_creation = usdngn_rate

        if not dry_run:
            await session.commit()
            log.info("patch_complete", orders=len(orders), line_items=total_items_patched)
        else:
            log.info(
                "dry_run_complete",
                orders=len(orders),
                line_items=total_items_patched,
                rate=str(usdngn_rate),
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Patch NGN purchase orders → USD")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--rate", type=Decimal, default=None, help="Manual USD/NGN rate override")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, rate=args.rate))
