"""ModishLog FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logging import setup_logging


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include domain routers
from src.auth.router import router as auth_router  # noqa: E402

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])

from src.inventory.router import router as inventory_router  # noqa: E402
from src.products.router import router as products_router  # noqa: E402

app.include_router(products_router, prefix="/api/v1/products", tags=["products"])
app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])

# TODO: Include remaining domain routers as they are implemented
# from src.sales.router import router as sales_router
# from src.orders.router import router as orders_router
# from src.fx.router import router as fx_router
# from src.cashflow.router import router as cashflow_router
# from src.pricing.router import router as pricing_router
# from src.ai_engine.router import router as ai_engine_router


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
