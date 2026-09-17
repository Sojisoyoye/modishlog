#!/usr/bin/env python3
"""
Move businesses past their billing grace period from past_due to
read_only (task #239).

Paystack's webhooks report a failed charge, but never send a "N days
have now elapsed" event -- so the 3-day grace-period deadline (billing
spec) has to be enforced by a scheduled job checking Business.past_due_since,
not a webhook handler. Run on a schedule -- see
.github/workflows/check-billing-grace-periods.yml.

Usage (inside docker compose exec backend):
  python scripts/check_billing_grace_periods.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog

from src.billing.service import check_expired_grace_periods
from src.core.database import async_session_factory

log = structlog.get_logger()


async def main() -> None:
    async with async_session_factory() as db:
        expired_ids = await check_expired_grace_periods(db)
        await db.commit()

    if expired_ids:
        log.info("billing_grace_periods_expired", expired_count=len(expired_ids))
        print(f"Moved {len(expired_ids)} business(es) to read_only: {expired_ids}")
    else:
        print("No businesses past their grace period. Nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
