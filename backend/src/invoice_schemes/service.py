"""Invoice schemes domain business logic."""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.invoice_schemes.exceptions import SchemeNotFoundError
from src.invoice_schemes.models import InvoiceScheme, SchemeType
from src.invoice_schemes.schemas import SchemeCreate, SchemeUpdate

logger = structlog.get_logger()


async def create_scheme(
    db: AsyncSession,
    data: SchemeCreate,
    user_id: uuid.UUID,
) -> InvoiceScheme:
    """Create a new invoice numbering scheme."""
    scheme = InvoiceScheme(
        name=data.name,
        scheme_type=data.scheme_type,
        prefix=data.prefix,
        start_number=data.start_number,
        total_digits=data.total_digits,
        next_number=data.start_number,
        created_by=user_id,
    )
    db.add(scheme)
    await db.flush()
    await logger.ainfo("invoice_scheme_created", scheme_id=str(scheme.id), name=scheme.name)
    return scheme


async def get_scheme(
    db: AsyncSession,
    scheme_id: uuid.UUID,
) -> InvoiceScheme:
    """Fetch a single invoice scheme by ID."""
    result = await db.execute(
        select(InvoiceScheme).where(InvoiceScheme.id == scheme_id)
    )
    scheme = result.scalar_one_or_none()
    if not scheme:
        raise SchemeNotFoundError(scheme_id)
    return scheme


async def list_schemes(db: AsyncSession) -> list[InvoiceScheme]:
    """List all invoice numbering schemes."""
    result = await db.execute(
        select(InvoiceScheme).order_by(InvoiceScheme.name.asc())
    )
    return list(result.scalars().all())


async def update_scheme(
    db: AsyncSession,
    scheme_id: uuid.UUID,
    data: SchemeUpdate,
) -> InvoiceScheme:
    """Update an invoice scheme."""
    scheme = await get_scheme(db, scheme_id)
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(scheme, field, value)
    await db.flush()
    await logger.ainfo("invoice_scheme_updated", scheme_id=str(scheme_id))
    return scheme


def generate_preview(scheme: InvoiceScheme) -> str:
    """Generate a preview of the next invoice number for this scheme.

    Pure synchronous function — no DB access, no async.
    """
    year = datetime.now(timezone.utc).year
    n = scheme.next_number
    padded = str(n).zfill(scheme.total_digits)
    if scheme.scheme_type == SchemeType.YEAR:
        return f"{scheme.prefix}{year}-{padded}"
    return f"{scheme.prefix}{padded}"
