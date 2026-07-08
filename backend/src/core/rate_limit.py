"""Application-level rate limiter using slowapi.

In development (no REDIS_URL): in-memory per-worker counters (not shared).
In production (REDIS_URL set): Redis-backed counters shared across all workers,
preventing the 2× bypass that occurs with independent per-worker state.
"""

import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings
from src.core.logging import sanitize_url

logger = structlog.get_logger()

_storage_uri: str | None = None
if settings.REDIS_URL:
    _storage_uri = settings.REDIS_URL
    logger.info("rate_limiter_backend", backend="redis", url=sanitize_url(settings.REDIS_URL))
else:
    logger.info(
        "rate_limiter_backend",
        backend="in_memory",
        note="Set REDIS_URL to enable shared rate limiting across workers",
    )

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri=_storage_uri,
)
