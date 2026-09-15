"""Audit trail service (task #246) -- write path is internal-only (called
from other domains' service layers, never exposed as a public POST
endpoint), so nothing outside the app itself can create a falsified entry.
The only public surface is the read path (router.py's GET list, admin-only).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditLog


async def record_audit_event(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    details: dict | None = None,
) -> AuditLog:
    """Append a single immutable audit event. Never update or delete a row
    once written -- callers needing to correct a mistake should write a new
    corrective event, not edit history."""
    entry = AuditLog(
        business_id=business_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_audit_events(
    db: AsyncSession,
    business_id: uuid.UUID,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[AuditLog], int]:
    """List audit events for a business, newest first."""
    count_q = select(func.count(AuditLog.id)).where(AuditLog.business_id == business_id)
    total = (await db.execute(count_q)).scalar_one()

    list_q = (
        select(AuditLog)
        .where(AuditLog.business_id == business_id)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(list_q)).scalars().all()
    return list(items), total
