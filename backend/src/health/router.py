"""Health check endpoint — no auth required, used by monitoring and deploy pipelines."""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.config import settings
from src.core.database import async_session_factory

logger = structlog.get_logger()
router = APIRouter()


async def check_db() -> str:
    """Ping the database. Returns 'ok' or raises on failure."""
    async with async_session_factory() as session:
        await session.execute(text("SELECT 1"))
    return "ok"


@router.get("/health")
async def health() -> JSONResponse:
    """Structured health check: verifies DB connectivity and returns version."""
    db_status = "ok"
    http_status = 200

    try:
        await check_db()
    except Exception:
        logger.error("health_check_db_failed", exc_info=True)
        db_status = "error"
        http_status = 503

    payload = {
        "status": "healthy" if http_status == 200 else "degraded",
        "version": settings.APP_VERSION,
        "db": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(content=payload, status_code=http_status)


# Alias router for /api/health — separate instance to avoid duplicate registration
api_router = APIRouter()
api_router.add_api_route("/health", health, methods=["GET"], include_in_schema=False)
