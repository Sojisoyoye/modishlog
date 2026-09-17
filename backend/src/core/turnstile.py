"""Cloudflare Turnstile CAPTCHA verification (task #250).

Guards POST /auth/onboard -- public, unauthenticated, and previously only
IP-rate-limited (easily beaten with rotating IPs/proxies). Now that real
billing/trials are attached to signup, scripted fake-account creation is
a fraud vector, not just a nuisance. This IS the primary defense against
that abuse (the rate limit is the weaker, already-beatable control), so
verify_turnstile_token() fails CLOSED on a genuine API error -- the
inverse of core/token_revocation.py's fail-open reasoning, which is
defense-in-depth on top of an already-real primary boundary.
"""

import httpx
import structlog

from src.core.config import settings

logger = structlog.get_logger()

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile_token(token: str, remote_ip: str | None = None) -> bool:
    """Verify a Turnstile challenge token against Cloudflare's API.

    Returns True without any HTTP call if TURNSTILE_SECRET_KEY isn't
    configured (dev/CI/E2E default). Otherwise returns Cloudflare's
    reported `success`, failing closed (False) on any network/timeout
    error -- a hung/unreachable Cloudflare call must reject the signup,
    not silently disable abuse protection.
    """
    if not settings.TURNSTILE_SECRET_KEY:
        return True

    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(_VERIFY_URL, data=data)
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        # Distinct from a rejected token below -- keeps a real Cloudflare
        # outage diagnosable as exactly that, not confused with "under
        # attack" in the logs.
        await logger.aerror("turnstile_verify_network_error", error=str(exc))
        return False

    if not result.get("success"):
        await logger.awarning(
            "turnstile_verify_rejected", error_codes=result.get("error-codes")
        )
        return False
    return True
