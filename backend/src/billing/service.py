"""Billing domain business logic (task #238) -- checkout initiation only.

Deliberately does not touch subscription_status/subscription_tier/
paystack_subscription_code -- initiating a checkout doesn't guarantee the
user completes payment. Those only get set once task #239's webhook
confirms a successful charge.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import Business, User, UserRole
from src.billing.exceptions import (
    BillingNotConfiguredError,
    BusinessNotFoundError,
    BusinessOwnerNotFoundError,
    InvalidTierError,
)
from src.billing.paystack_client import create_customer, initialize_transaction
from src.core.config import settings

logger = structlog.get_logger()

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
