"""Invoice schemes API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.invoice_schemes.exceptions import SchemeNotFoundError
from src.invoice_schemes.schemas import (
    SchemeCreate,
    SchemeListResponse,
    SchemePreview,
    SchemeRead,
    SchemeUpdate,
)
from src.invoice_schemes.service import (
    create_scheme,
    generate_preview,
    get_scheme,
    list_schemes,
    update_scheme,
)

router = APIRouter()


@router.post("", response_model=SchemeRead, status_code=status.HTTP_201_CREATED)
async def create_scheme_endpoint(
    body: SchemeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new invoice numbering scheme."""
    return await create_scheme(db, body, current_user.id)


@router.get("", response_model=SchemeListResponse)
async def list_schemes_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all invoice numbering schemes."""
    items = await list_schemes(db)
    return SchemeListResponse(items=items, total=len(items))


@router.get("/{scheme_id}", response_model=SchemeRead)
async def get_scheme_endpoint(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single invoice scheme by ID."""
    try:
        return await get_scheme(db, scheme_id)
    except SchemeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{scheme_id}", response_model=SchemeRead)
async def update_scheme_endpoint(
    scheme_id: uuid.UUID,
    body: SchemeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update an invoice numbering scheme."""
    try:
        return await update_scheme(db, scheme_id, body)
    except SchemeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{scheme_id}/preview", response_model=SchemePreview)
async def preview_scheme_endpoint(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate a preview of the next invoice number (no DB increment)."""
    try:
        scheme = await get_scheme(db, scheme_id)
    except SchemeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return SchemePreview(preview=generate_preview(scheme))
