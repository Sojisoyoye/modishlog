"""ModishLog FastAPI application entry point."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    setup_logging()
    yield


app = FastAPI(
    title="ModishLog API",
    description="Smart business management platform for everyday traders and SMB owners",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    await logger.aerror(
        "unhandled_exception",
        method=request.method,
        path=str(request.url.path),
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files as static assets
os.makedirs(os.path.join(settings.UPLOAD_DIR, "products"), exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

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


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
