"""Access-token revocation denylist (task #226).

Access tokens are stateless JWTs with no server-side state otherwise --
ACCESS_TOKEN_EXPIRE_MINUTES=1440 (24h) in production is a deliberate UX
tradeoff for SMB users on shared/kiosk-style devices, kept as-is rather
than shortened. This denylist is a defense-in-depth layer on top of that
existing 24h expiry (and the already-real is_active check on every
request) for the one remediation action a user can take themselves:
logout. It is NOT the primary security boundary, which is why
is_jti_revoked() fails open on a Redis error rather than denying every
authenticated request app-wide during a transient outage.
"""

import redis.asyncio as aioredis
import structlog

from src.core.config import settings

logger = structlog.get_logger()

_redis_client: aioredis.Redis | None = None


def _get_redis_client() -> aioredis.Redis:
    """Lazy singleton -- created on first use, not at import time, so
    importing this module stays side-effect-free when REDIS_URL is empty
    (tests/CI). Reused across calls, unlike health/router.py's check_redis()
    (a rarely-called probe that opens a throwaway client per call) --
    this runs on every authenticated request, so connection reuse matters.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    return _redis_client


def _key(jti: str) -> str:
    return f"revoked_jti:{jti}"


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Add a token's jti to the denylist for ttl_seconds -- the entry
    self-expires exactly when the token itself would have anyway, so it
    never needs manual cleanup. No-ops if REDIS_URL isn't configured.
    """
    if not settings.REDIS_URL:
        await logger.adebug("jti_revocation_skipped", reason="REDIS_URL not configured")
        return
    client = _get_redis_client()
    await client.setex(_key(jti), max(1, ttl_seconds), "1")


async def is_jti_revoked(jti: str) -> bool:
    """Check the denylist. Fails OPEN (returns False) if REDIS_URL isn't
    configured or the Redis call itself raises -- see module docstring for
    why. Logs loudly on a genuine Redis error so a sustained outage
    degrading this check is visible in monitoring, not silent.
    """
    if not settings.REDIS_URL:
        return False
    try:
        client = _get_redis_client()
        return bool(await client.exists(_key(jti)))
    except Exception as exc:
        await logger.awarning("jti_revocation_check_failed", error=str(exc), exc_info=True)
        return False
