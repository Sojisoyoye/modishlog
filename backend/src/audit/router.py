"""Audit trail API routes -- read-only. There is deliberately no POST/PATCH/
DELETE route in this router: writes only happen internally via
audit.service.record_audit_event(), called directly from the domains that
perform a sensitive action, never from a public request body."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_business_id, require_admin
from src.audit.schemas import AuditLogListResponse
from src.audit.service import list_audit_events
from src.core.database import get_db

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_events_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """List audit events for the current business, newest first. Admin/owner only."""
    items, total = await list_audit_events(
        db, business_id, page=page, page_size=page_size
    )
    return AuditLogListResponse(
        items=items, total=total, page=page, page_size=page_size
    )
