"""Billing API routes (task #238) -- checkout initiation only."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_business_id, require_admin
from src.billing.exceptions import (
    BillingNotConfiguredError,
    BusinessNotFoundError,
    BusinessOwnerNotFoundError,
    InvalidTierError,
    PaystackAPIError,
)
from src.billing.schemas import CheckoutRequest, CheckoutResponse
from src.billing.service import initiate_checkout
from src.core.database import get_db

router = APIRouter(dependencies=[Depends(require_admin)])


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
