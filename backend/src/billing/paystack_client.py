"""Thin async wrapper over Paystack's REST API (tasks #238/#239)."""

import hashlib
import hmac

import httpx
import structlog

from src.billing.exceptions import PaystackAPIError
from src.core.config import settings

logger = structlog.get_logger()

_BASE_URL = "https://api.paystack.co"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


async def create_customer(email: str) -> str:
    """Create a Paystack customer. Returns the gateway's customer_code."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{_BASE_URL}/customer", headers=_headers(), json={"email": email}
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            await logger.aerror("paystack_create_customer_failed", status=exc.response.status_code)
            raise PaystackAPIError(f"Paystack create_customer failed: {exc}") from exc
        except httpx.RequestError as exc:
            await logger.aerror("paystack_create_customer_network_error", error=str(exc))
            raise PaystackAPIError(f"Paystack create_customer network error: {exc}") from exc

    return response.json()["data"]["customer_code"]


async def initialize_transaction(email: str, plan_code: str, callback_url: str) -> dict:
    """Initialize a Plan-code-driven checkout transaction. The charge amount
    is inherited from the Plan itself (set in the Paystack dashboard) --
    never sent by this app. Returns {authorization_url, access_code, reference}."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{_BASE_URL}/transaction/initialize",
                headers=_headers(),
                json={"email": email, "plan": plan_code, "callback_url": callback_url},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            await logger.aerror(
                "paystack_initialize_transaction_failed", status=exc.response.status_code
            )
            raise PaystackAPIError(f"Paystack initialize_transaction failed: {exc}") from exc
        except httpx.RequestError as exc:
            await logger.aerror("paystack_initialize_transaction_network_error", error=str(exc))
            raise PaystackAPIError(f"Paystack initialize_transaction network error: {exc}") from exc

    return response.json()["data"]


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    """Verify a Paystack webhook's HMAC-SHA512 signature (task #239).

    Paystack signs the raw request body with the secret key; comparing
    against a freshly-parsed-and-reserialized JSON body would not
    reproduce the exact bytes signed, so the caller must pass the raw
    body read straight off the request, before any JSON parsing.
    hmac.compare_digest avoids a timing side-channel on the comparison.
    """
    if not signature or not settings.PAYSTACK_SECRET_KEY:
        return False
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
