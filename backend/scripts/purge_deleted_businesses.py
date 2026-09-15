#!/usr/bin/env python3
"""
Purge businesses whose self-service deletion grace period has expired
(task #260).

Task #252 shipped the user-facing half of self-service business deletion
(OWNER-initiated close, 30-day grace period). This script is the other
half: anonymizes any business whose purge_at has passed and that hasn't
already been purged. Run on a schedule -- see
.github/workflows/purge-deleted-businesses.yml.

Usage (inside docker compose exec backend):
  python scripts/purge_deleted_businesses.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog

from src.auth.service import purge_expired_business_deletions
from src.core.database import async_session_factory

log = structlog.get_logger()


async def main() -> None:
    async with async_session_factory() as db:
        purged_ids = await purge_expired_business_deletions(db)
        await db.commit()

    if purged_ids:
        log.info("purge_deleted_businesses_complete", purged_count=len(purged_ids))
        print(f"Purged {len(purged_ids)} business(es): {purged_ids}")
    else:
        print("No businesses past their purge date. Nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
