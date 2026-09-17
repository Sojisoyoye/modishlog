"""Billing API routes -- checkout initiation (task #238, admin-only) and
the Paystack webhook (task #239, unauthenticated -- signature-verified
instead, since Paystack is not a logged-in user)."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_business_id, require_admin
from src.billing.exceptions import (
    BillingNotConfiguredError,
    BusinessNotFoundError,
    BusinessOwnerNotFoundError,
    InvalidTierError,
    PaystackAPIError,
)
from src.billing.paystack_client import verify_signature
from src.billing.schemas import CheckoutRequest, CheckoutResponse
from src.billing.service import initiate_checkout, process_webhook_event
from src.core.database import get_db

logger = structlog.get_logger()

router = APIRouter(dependencies=[Depends(require_admin)])
webhook_router = APIRouter()


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout_endpoint(
    body: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Initiate a Paystack hosted checkout for the given tier. Admin/owner only."""
    try:
        return await initiate_checkout(db, business_id, tier=body.tier)
    except InvalidTierError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except BillingNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except BusinessNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BusinessOwnerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PaystackAPIError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@webhook_router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive a Paystack webhook event. No auth dependency -- Paystack is
    not a logged-in user, so the HMAC signature IS the authentication.
    Raw body must be read before any JSON parsing (verify_signature checks
    the exact bytes Paystack signed)."""
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not verify_signature(raw_body, signature):
        await logger.awarning("billing_webhook_invalid_signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event", "")
    data = payload.get("data", {})

    await process_webhook_event(db, event_type, data, raw_body)
    await db.commit()
    return {"status": "ok"}
