"""ModishLog FastAPI application entry point."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
# _rate_limit_exceeded_handler: private symbol used per slowapi docs — pin slowapi==0.1.9 to guard against breakage
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.core.config import settings
from src.core.logging import setup_logging
from src.core.middleware import SecurityHeadersMiddleware
from src.core.rate_limit import limiter

logger = structlog.get_logger()


async def _pos_sync_loop(interval_seconds: int = 600) -> None:
    """Background task: run incremental POS sync every N seconds."""
    import uuid as _uuid

    pos_user = os.environ.get("POS_USERNAME")
    pos_pass = os.environ.get("POS_PASSWORD")
    if not pos_user or not pos_pass:
        logger.info("pos_sync_disabled", reason="POS_USERNAME/POS_PASSWORD not set")
        return

    # POS_BUSINESS_ID must be set to the UUID of the business that owns the POS
    # data. Without it, synced records cannot be scoped to a tenant.
    pos_business_id_raw = os.environ.get("POS_BUSINESS_ID")
    if not pos_business_id_raw:
        logger.info("pos_sync_disabled", reason="POS_BUSINESS_ID not set")
        return
    try:
        pos_business_id = _uuid.UUID(pos_business_id_raw)
    except ValueError:
        await logger.aerror("pos_sync_invalid_business_id", raw=pos_business_id_raw)
        return

    from scripts.pos_migrate import POSClient
    from src.core.database import async_session_factory
    from src.pos_sync.service import POSSyncService

    await asyncio.sleep(30)  # give the app time to finish starting
    while True:
        try:
            client = POSClient()
            client.login()
            async with async_session_factory() as db:
                service = POSSyncService(db=db, pos_client=client, business_id=pos_business_id)
                result = await service.run_incremental_sync()
                await db.commit()
                await logger.ainfo(
                    "pos_sync_cycle_complete",
                    **{
                        k: {
                            "inserted": v.inserted,
                            "skipped": v.skipped,
                            "watermark": v.new_watermark,
                        }
                        for k, v in result.items()
                    },
                )
        except Exception:
            await logger.aexception("pos_sync_cycle_failed")
        await asyncio.sleep(interval_seconds)


def _init_sentry() -> None:
    """Initialise Sentry if DSN is configured. No-op when DSN is empty."""
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.1,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        before_send=_scrub_pii,
    )


_PII_FIELDS = frozenset(
    {
        "password",
        "hashed_password",
        "email",
        "phone",
        "token",
        "refresh_token",
        "api_key",
        "secret",
        "encrypted_value",
        "DATABASE_URL",
        "SECRET_KEY",
        "ANTHROPIC_API_KEY",
    }
)


def _scrub_pii(event: dict, hint: dict) -> dict:
    """Strip PII fields from Sentry events before they leave the process.

    Removes:
    - All fields in _PII_FIELDS from event["extra"]
    - The entire request body (event["request"]["data"]) which may contain
      credentials, personal data, or financial details
    - Sensitive fields from event["user"]
    """
    if "request" in event:
        # Remove the full request body to avoid capturing POST payloads with PII
        event["request"].pop("data", None)

    if "extra" in event:
        for field in _PII_FIELDS:
            event["extra"].pop(field, None)

    if "user" in event and isinstance(event["user"], dict):
        for field in _PII_FIELDS:
            event["user"].pop(field, None)

    return event


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    setup_logging()
    _init_sentry()
    task = asyncio.create_task(_pos_sync_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="ModishLog API",
    description="Smart business management platform for everyday traders and SMB owners",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    await logger.aerror(
        "unhandled_exception",
        method=request.method,
        path=str(request.url.path),
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# Serve uploaded files as static assets
# Guard: Docker named volumes are root-owned on first run; skip gracefully if
# the container user lacks write permission (e.g. CI without volume init).
try:
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "products"), exist_ok=True)
    app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")
except (PermissionError, RuntimeError):
    pass

# Include domain routers
from src.auth.router import router as auth_router  # noqa: E402

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])

from src.suppliers.router import router as suppliers_router  # noqa: E402

app.include_router(suppliers_router, prefix="/api/v1/suppliers", tags=["suppliers"])

from src.customers.router import router as customers_router  # noqa: E402

app.include_router(customers_router, prefix="/api/v1/customers", tags=["customers"])

from src.fx.router import router as fx_router  # noqa: E402
from src.inventory.router import router as inventory_router  # noqa: E402
from src.orders.router import router as orders_router  # noqa: E402
from src.products.router import router as products_router  # noqa: E402
from src.sales.router import router as sales_router  # noqa: E402

app.include_router(products_router, prefix="/api/v1/products", tags=["products"])
app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])
app.include_router(sales_router, prefix="/api/v1/sales", tags=["sales"])
app.include_router(orders_router, prefix="/api/v1/orders", tags=["orders"])
app.include_router(fx_router, prefix="/api/v1/fx", tags=["fx"])

from src.pricing.router import router as pricing_router  # noqa: E402

app.include_router(pricing_router, prefix="/api/v1/pricing", tags=["pricing"])

from src.cashflow.router import router as cashflow_router  # noqa: E402

app.include_router(cashflow_router, prefix="/api/v1/cashflow", tags=["cashflow"])

from src.ai_engine.router import router as ai_engine_router  # noqa: E402

app.include_router(ai_engine_router, prefix="/api/v1/ai", tags=["ai"])

from src.reports.router import router as reports_router  # noqa: E402

app.include_router(reports_router, prefix="/api/v1/reports", tags=["reports"])

from src.invoice_schemes.router import router as invoice_schemes_router  # noqa: E402

app.include_router(
    invoice_schemes_router, prefix="/api/v1/invoice-schemes", tags=["invoice-schemes"]
)

from src.locations.router import router as locations_router  # noqa: E402

app.include_router(locations_router, prefix="/api/v1/locations", tags=["locations"])

from src.stockcount.router import router as stockcount_router  # noqa: E402

app.include_router(stockcount_router, prefix="/api/v1/stockcount", tags=["stockcount"])

from src.settings.router import router as settings_router  # noqa: E402

app.include_router(settings_router, prefix="/api/v1", tags=["settings"])

from src.dashboard.router import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])

from src.expenses.router import categories_router as expense_categories_router  # noqa: E402
from src.expenses.router import expenses_router  # noqa: E402

app.include_router(
    expense_categories_router, prefix="/api/v1/expense-categories", tags=["expenses"]
)
app.include_router(expenses_router, prefix="/api/v1/expenses", tags=["expenses"])

from src.health.router import api_router as health_api_router, router as health_router  # noqa: E402

# Mount at both /health (used by docker-compose healthcheck) and /api/health (convention)
app.include_router(health_router, tags=["health"])
app.include_router(health_api_router, prefix="/api", tags=["health"])
