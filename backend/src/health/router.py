"""Health check endpoint — no auth required, used by monitoring and deploy pipelines."""

from datetime import datetime, timezone

import httpx
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


async def check_fx_api() -> str:
    """Check ExchangeRate-API reachability with a GET request (2 s timeout).

    Uses GET rather than HEAD because ExchangeRate-API returns 405 on HEAD,
    which would mark the API as permanently down even when it is healthy.
    Any response with status < 500 is treated as reachable (the API is up
    even if it returns 4xx for a missing API key). Only network errors or
    5xx responses are treated as failures.

    Returns 'ok' or raises on failure.
    """
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.get(settings.FX_LIVE_API_URL)
        if response.status_code >= 500:
            response.raise_for_status()
    return "ok"


async def check_anthropic() -> str:
    """Verify the Anthropic API key is configured and looks valid.

    Returns 'ok' if the key starts with 'sk-ant-' and is non-empty,
    'not_configured' if missing, or raises on invalid format.
    """
    key = settings.ANTHROPIC_API_KEY
    if not key:
        return "not_configured"
    if not key.startswith("sk-ant-"):
        raise ValueError("ANTHROPIC_API_KEY does not start with 'sk-ant-'")
    return "ok"


async def check_redis() -> str:
    """Check Redis connectivity if REDIS_URL is configured.

    Returns 'ok', 'not_configured', or raises on failure.
    """
    if not settings.REDIS_URL:
        return "not_configured"
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    try:
        await client.ping()
        return "ok"
    finally:
        await client.aclose()


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


@router.get("/health/deep")
async def health_deep() -> JSONResponse:
    """Deep health check: verifies DB, FX API, Anthropic key, and Redis (if configured).

    Returns:
    - 200 with status=healthy when all critical checks pass.
    - 200 with status=degraded when non-critical checks fail (FX API, Anthropic, Redis).
    - 503 with status=unhealthy when a critical check fails (DB).

    Used by production monitoring to distinguish DB outage from external API unavailability.
    """
    checks: dict[str, str] = {}
    critical_failed = False

    # DB — CRITICAL: if this fails, the application cannot serve requests
    try:
        checks["db"] = await check_db()
    except Exception:
        logger.error("deep_health_db_failed", exc_info=True)
        checks["db"] = "error"
        critical_failed = True

    # FX API — NON-CRITICAL: degraded mode uses cached rates
    try:
        checks["fx_api"] = await check_fx_api()
    except Exception as exc:
        logger.warning("deep_health_fx_api_failed", error=str(exc))
        checks["fx_api"] = "error"

    # Anthropic — NON-CRITICAL: AI features degrade gracefully
    try:
        checks["anthropic"] = await check_anthropic()
    except Exception as exc:
        logger.warning("deep_health_anthropic_failed", error=str(exc))
        checks["anthropic"] = "error"

    # Redis — NON-CRITICAL: falls back to in-memory rate limiting
    try:
        checks["redis"] = await check_redis()
    except Exception as exc:
        logger.warning("deep_health_redis_failed", error=str(exc))
        checks["redis"] = "error"

    if critical_failed:
        overall_status = "unhealthy"
        http_status = 503
    elif any(v == "error" for v in checks.values()):
        overall_status = "degraded"
        http_status = 200
    else:
        overall_status = "healthy"
        http_status = 200

    payload = {
        "status": overall_status,
        "version": settings.APP_VERSION,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(content=payload, status_code=http_status)


# Alias router for /api/health — separate instance to avoid duplicate registration
api_router = APIRouter()
api_router.add_api_route("/health", health, methods=["GET"], include_in_schema=False)
