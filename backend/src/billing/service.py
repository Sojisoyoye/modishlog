"""Billing domain business logic -- checkout initiation (task #238) and
idempotent webhook handling (task #239).

initiate_checkout() deliberately does not touch subscription_status/
subscription_tier/paystack_subscription_code -- initiating a checkout
doesn't guarantee the user completes payment. Those only get set once
process_webhook_event() confirms a real payment/subscription event.
"""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.service import record_audit_event
from src.auth.models import Business, SubscriptionStatus, User, UserRole
from src.billing.exceptions import (
    BillingNotConfiguredError,
    BusinessNotFoundError,
    BusinessOwnerNotFoundError,
    InvalidTierError,
)
from src.billing.models import WebhookEvent
from src.billing.paystack_client import create_customer, initialize_transaction
from src.core.config import settings

logger = structlog.get_logger()

_GRACE_PERIOD_DAYS = 3

_TIER_PLAN_CODES = {
    "basic": lambda: settings.PAYSTACK_BASIC_PLAN_CODE,
    "pro": lambda: settings.PAYSTACK_PRO_PLAN_CODE,
}


async def initiate_checkout(db: AsyncSession, business_id: uuid.UUID, tier: str) -> dict:
    """Start a Paystack hosted-checkout for the given business/tier.

    Returns {authorization_url, access_code, reference} for the frontend
    to redirect the browser to Paystack's checkout page.
    """
    if tier not in _TIER_PLAN_CODES:
        raise InvalidTierError(tier)

    plan_code = _TIER_PLAN_CODES[tier]()
    if not plan_code:
        raise BillingNotConfiguredError(
            f"No Paystack Plan code configured for tier '{tier}' -- "
            "set PAYSTACK_BASIC_PLAN_CODE/PAYSTACK_PRO_PLAN_CODE."
        )

    business_result = await db.execute(select(Business).where(Business.id == business_id))
    business = business_result.scalar_one_or_none()
    if business is None:
        raise BusinessNotFoundError(business_id)

    owner_result = await db.execute(
        select(User).where(User.business_id == business_id, User.role == UserRole.OWNER)
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        raise BusinessOwnerNotFoundError(business_id)

    if business.paystack_customer_code is None:
        customer_code = await create_customer(owner.email)
        business.paystack_customer_code = customer_code
        await db.flush()
        await logger.ainfo(
            "paystack_customer_created", business_id=str(business_id), customer_code=customer_code
        )

    callback_url = f"{settings.FRONTEND_URL}/settings/billing"
    checkout = await initialize_transaction(owner.email, plan_code, callback_url)
    await logger.ainfo(
        "billing_checkout_initiated",
        business_id=str(business_id),
        tier=tier,
        reference=checkout["reference"],
    )
    return checkout


# ---------------------------------------------------------------------------
# Webhook handling (task #239)
# ---------------------------------------------------------------------------


def _handle_charge_success(business: Business, data: dict) -> None:
    business.subscription_status = SubscriptionStatus.ACTIVE
    business.past_due_since = None


def _handle_subscription_create(business: Business, data: dict) -> None:
    business.paystack_subscription_code = data.get("subscription_code")
    business.subscription_status = SubscriptionStatus.ACTIVE
    next_payment_date = data.get("next_payment_date")
    if next_payment_date:
        try:
            business.current_period_end = datetime.fromisoformat(
                str(next_payment_date).replace("Z", "+00:00")
            )
        except ValueError:
            pass  # Malformed date from the gateway -- don't crash the webhook over a display field.


def _handle_payment_failed(business: Business, data: dict) -> None:
    business.subscription_status = SubscriptionStatus.PAST_DUE
    # Only set on the FIRST failure -- a second consecutive notification
    # must not push the 3-day grace-period deadline back out.
    if business.past_due_since is None:
        business.past_due_since = datetime.now(timezone.utc)


def _handle_subscription_disable(business: Business, data: dict) -> None:
    business.subscription_status = SubscriptionStatus.CANCELED


# Deliberately isolated as a small, flat mapping -- exact Paystack event
# names/payload shapes here are drawn from documented API knowledge, not
# verified against a live sandbox (no account exists yet). Cheap to correct
# once real webhook payloads are available (Paystack's dashboard logs
# every delivery).
_EVENT_HANDLERS = {
    "charge.success": _handle_charge_success,
    "subscription.create": _handle_subscription_create,
    "invoice.payment_failed": _handle_payment_failed,
    "subscription.disable": _handle_subscription_disable,
}


def _idempotency_key(event_type: str, data: dict) -> str:
    identifier = data.get("id") or data.get("reference") or data.get("subscription_code") or "unknown"
    return f"{event_type}:{identifier}"


async def process_webhook_event(
    db: AsyncSession, event_type: str, data: dict, raw_body: bytes
) -> None:
    """Process one verified Paystack webhook event. Caller (the router)
    is responsible for signature verification before this is ever called
    -- this function trusts its input completely.

    Idempotent: a WebhookEvent row already existing for this event's key
    means it was already fully processed, so redelivery is a safe no-op.
    """
    idempotency_key = _idempotency_key(event_type, data)

    existing_result = await db.execute(
        select(WebhookEvent).where(WebhookEvent.idempotency_key == idempotency_key)
    )
    if existing_result.scalar_one_or_none() is not None:
        await logger.ainfo(
            "billing_webhook_skipped_duplicate", event_type=event_type, idempotency_key=idempotency_key
        )
        return

    # `or {}` (not just .get(..., {})) -- some Paystack event types send an
    # explicit "customer": null rather than omitting the key, which would
    # otherwise crash this on an event type we don't even handle.
    customer_code = (data.get("customer") or {}).get("customer_code")
    business_result = await db.execute(
        select(Business).where(Business.paystack_customer_code == customer_code)
    )
    business = business_result.scalar_one_or_none()
    if business is None:
        await logger.awarning(
            "billing_webhook_unknown_customer", event_type=event_type, customer_code=customer_code
        )
        return

    handler = _EVENT_HANDLERS.get(event_type)
    if handler is not None:
        handler(business, data)

    db.add(
        WebhookEvent(event_type=event_type, idempotency_key=idempotency_key, raw_payload=data)
    )
    await db.flush()

    owner_result = await db.execute(
        select(User).where(User.business_id == business.id, User.role == UserRole.OWNER)
    )
    owner = owner_result.scalar_one_or_none()
    if owner is not None:
        await record_audit_event(
            db,
            business_id=business.id,
            actor_user_id=owner.id,
            action=f"billing_{event_type.replace('.', '_')}",
            entity_type="business",
            entity_id=business.id,
            details={"subscription_status": business.subscription_status.value},
        )

    await logger.ainfo(
        "billing_webhook_processed",
        event_type=event_type,
        business_id=str(business.id),
        new_status=business.subscription_status.value,
    )


async def check_expired_grace_periods(db: AsyncSession) -> list[uuid.UUID]:
    """Move any business whose 3-day grace period has expired from
    PAST_DUE to READ_ONLY. Paystack doesn't send a "N days elapsed"
    webhook, so this is a scheduled job (see
    backend/scripts/check_billing_grace_periods.py), not webhook-driven.
    Safe to re-run -- already-READ_ONLY businesses aren't matched.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_GRACE_PERIOD_DAYS)
    result = await db.execute(
        select(Business).where(
            Business.subscription_status == SubscriptionStatus.PAST_DUE,
            Business.past_due_since.is_not(None),
            Business.past_due_since <= cutoff,
        )
    )
    businesses = result.scalars().all()

    expired_ids: list[uuid.UUID] = []
    for business in businesses:
        business.subscription_status = SubscriptionStatus.READ_ONLY
        expired_ids.append(business.id)
        await logger.ainfo("billing_grace_period_expired", business_id=str(business.id))

    if expired_ids:
        await db.flush()
    return expired_ids
