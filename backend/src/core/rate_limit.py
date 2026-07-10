"""Application-level rate limiter using slowapi.

In development (no REDIS_URL): in-memory per-worker counters (not shared).
In production (REDIS_URL set): Redis-backed counters shared across all workers,
preventing the 2× bypass that occurs with independent per-worker state.
"""

import uuid as _uuid

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


def _key_func(request):
    """Return a unique key per request in test mode so rate limits are never hit.

    In test (ENVIRONMENT=test) Playwright workers all share the same IP, causing
    the 10/minute login cap to trigger before the suite completes.  A UUID per
    request gives each call its own counter, making limits effectively unlimited
    while leaving the real limiter code active (so security tests still work in
    development mode where ENVIRONMENT defaults to 'development').
    """
    if settings.ENVIRONMENT == "test":
        return str(_uuid.uuid4())
    return get_remote_address(request)


limiter = Limiter(
    key_func=_key_func,
    default_limits=["200/minute"],
    storage_uri=_storage_uri,
)
