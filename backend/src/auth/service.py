"""Auth business logic -- all async operations."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.auth.schemas import OnboardRequest

import structlog
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.exceptions import (
    AccountLockedError,
    CannotModifySelfError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetTokenError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WeakPasswordError,
)
from src.auth.models import Business, PasswordResetToken, RefreshToken, User, UserRole
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.security import create_access_token, get_password_hash, verify_password

logger = structlog.get_logger()

_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{12,}$"
)

LOCKOUT_THRESHOLD = 3
LOCKOUT_DURATION_MINUTES = 15


def validate_password(password: str) -> None:
    """Enforce password complexity: 12+ chars, upper, lower, digit, special."""
    if not _PASSWORD_PATTERN.match(password):
        raise WeakPasswordError(
            "Password must be at least 12 characters with uppercase, "
            "lowercase, digit, and special character."
        )


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.SALES_MANAGER,
) -> User:
    """Register a new user account."""
    validate_password(password)

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise UserAlreadyExistsError(f"Email {email} is already registered")

    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        is_active=True,
        role=role,
        failed_login_attempts=0,
    )
    db.add(user)
    await db.flush()
    await logger.ainfo("user_registered", user_id=str(user.id), email=email)
    return user


async def create_business_and_owner(
    db: AsyncSession, data: "OnboardRequest"
) -> tuple["Business", User, str, str]:
    """Create a Business + owner User atomically."""
    business = Business(
        name=data.business_name,
        currency=data.currency,
        country=data.country,
        state=data.state,
        city=data.city,
        phone=data.phone,
        timezone=data.timezone,
        tax_number=data.tax_number,
        fiscal_year_start_month=data.fiscal_year_start_month,
    )
    db.add(business)
    await db.flush()  # materialise business.id

    # create_user() validates password + checks email uniqueness
    user = await create_user(db, data.email, data.password, data.full_name, role=UserRole.OWNER)
    user.business_id = business.id
    user.ndpr_consent_given = True
    user.ndpr_consent_at = datetime.now(timezone.utc)
    await db.flush()

    raw_refresh = await create_refresh_token(db, user)
    access_token = build_token(user)
    # Do NOT call db.commit() here — get_db handles the final commit after the handler
    # returns successfully. Logging here is pre-commit; on a commit failure the event
    # is emitted but no data persists. This is acceptable (extremely rare, idempotent retry).
    await logger.ainfo("business_onboarding_pending", business_id=str(business.id), user_id=str(user.id))
    return business, user, access_token, raw_refresh


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User:
    """Verify credentials with failed-login lockout logic."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise InvalidCredentialsError()

    # Check lockout — use naive UTC throughout to match the DB column (TIMESTAMP WITHOUT TIME ZONE)
    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        await logger.awarn(
            "login_locked", email=email, locked_until=str(user.locked_until)
        )
        raise AccountLockedError(user.locked_until)

    if not verify_password(password, user.hashed_password):
        new_attempts = (user.failed_login_attempts or 0) + 1
        locked_until = (
            now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            if new_attempts >= LOCKOUT_THRESHOLD
            else user.locked_until
        )
        if new_attempts >= LOCKOUT_THRESHOLD:
            await logger.awarn("account_locked", email=email)
        # Use a separate session so this write is committed independently of the
        # request session — get_db rolls back the request session on any exception.
        async with async_session_factory() as lockout_db:
            await lockout_db.execute(
                update(User)
                .where(User.id == user.id)
                .values(failed_login_attempts=new_attempts, locked_until=locked_until)
            )
            await lockout_db.commit()
        raise InvalidCredentialsError()

    # Successful login — reset counters
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.flush()
    await logger.ainfo("login_success", email=email)
    return user


def build_token(user: User) -> str:
    """Create JWT access token for authenticated user."""
    return create_access_token(data={"sub": str(user.id)})


RESET_TOKEN_EXPIRE_HOURS = 1


async def generate_password_reset_token(
    db: AsyncSession,
    email: str,
) -> str | None:
    """Create a password-reset token for the given email.

    Returns the raw token string, or *None* if the email is not found
    (silently -- never reveal whether the email exists).
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        await logger.ainfo("password_reset_requested_unknown_email", email=email)
        return None

    raw_token = secrets.token_urlsafe(32)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS),
        used=False,
    )
    db.add(reset_token)
    await db.flush()
    await logger.ainfo("password_reset_token_created", user_id=str(user.id))
    return raw_token


async def reset_password(
    db: AsyncSession,
    token: str,
    new_password: str,
) -> None:
    """Validate a password-reset token and update the user's password.

    Raises ``InvalidResetTokenError`` if the token is missing, expired,
    or already used.  Raises ``WeakPasswordError`` if the new password
    doesn't meet complexity requirements.
    """
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == _hash_token(token))
    )
    token_obj = result.scalar_one_or_none()

    if token_obj is None:
        raise InvalidResetTokenError("Invalid or expired reset token.")

    now = datetime.now(timezone.utc)
    if token_obj.used or token_obj.expires_at < now:
        raise InvalidResetTokenError("Invalid or expired reset token.")

    # Validate new password strength before touching user record
    validate_password(new_password)

    # Fetch user and update password
    user = await db.get(User, token_obj.user_id)
    user.hashed_password = get_password_hash(new_password)

    # Mark token as consumed
    token_obj.used = True
    await db.flush()
    await logger.ainfo("password_reset_success", user_id=str(user.id))


# ---------------------------------------------------------------------------
# Refresh token helpers
# ---------------------------------------------------------------------------


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw token string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_refresh_token(db: AsyncSession, user: User) -> str:
    """Generate a new opaque refresh token, persist its hash, and return the raw value.

    The raw value is returned to the caller once (to be sent to the client).
    Only the hash is stored in the database.
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked_at=None,
    )
    db.add(refresh_token)
    await db.flush()
    await logger.ainfo("refresh_token_created", user_id=str(user.id))
    return raw_token


async def refresh_access_token(db: AsyncSession, raw_token: str) -> str:
    """Validate a refresh token and issue a new access token.

    Raises ``InvalidRefreshTokenError`` if the token is not found,
    expired, or revoked.
    """
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_obj = result.scalar_one_or_none()

    if token_obj is None:
        raise InvalidRefreshTokenError("Invalid refresh token.")

    now = datetime.now(timezone.utc)

    if token_obj.revoked_at is not None:
        await logger.awarn("refresh_token_revoked_reuse", token_hash=token_hash[:16])
        raise InvalidRefreshTokenError("Refresh token has been revoked.")

    if token_obj.expires_at < now:
        await logger.awarn("refresh_token_expired", token_hash=token_hash[:16])
        raise InvalidRefreshTokenError("Refresh token has expired.")

    new_access_token = create_access_token(data={"sub": str(token_obj.user.id)})
    await logger.ainfo("access_token_refreshed", user_id=str(token_obj.user.id))
    return new_access_token


async def unlock_user(db: AsyncSession, email: str) -> User:
    """Reset failed_login_attempts and locked_until for a user (admin action)."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError(f"User {email} not found")
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.flush()
    await logger.ainfo("account_unlocked", email=email)
    return user


async def revoke_refresh_token(db: AsyncSession, raw_token: str | None) -> None:
    """Revoke a refresh token by recording the revocation timestamp.

    This is a no-op if the token does not exist or is None (idempotent logout).
    """
    if not raw_token:
        return
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_obj = result.scalar_one_or_none()

    if token_obj is None:
        await logger.ainfo("refresh_token_revoke_noop", reason="not_found")
        return

    token_obj.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    await logger.ainfo("refresh_token_revoked", user_id=str(token_obj.user_id))


# ---------------------------------------------------------------------------
# Admin user management
# ---------------------------------------------------------------------------


async def list_users(
    db: AsyncSession,
    business_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> tuple[list[User], int]:
    """Return a paginated list of users scoped to the given business.

    S4: business_id filter is mandatory to prevent cross-tenant user enumeration.
    An admin from Business A must never see users belonging to Business B.
    """
    # S4: Always filter by business_id — cross-tenant user enumeration is an NDPR violation.
    query = select(User).where(User.business_id == business_id)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(User.email.ilike(term), User.full_name.ilike(term))
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Fetch a single user by ID; raise UserNotFoundError if absent."""
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")
    return user


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: dict,
    requesting_user_id: uuid.UUID,
) -> User:
    """Update full_name, role, or is_active for a user.

    Raises CannotModifySelfError if the admin attempts to deactivate or
    demote their own account.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")

    if user_id == requesting_user_id:
        if data.get("is_active") is False:
            raise CannotModifySelfError("Cannot deactivate your own account")
        if "role" in data and data["role"] != user.role:
            raise CannotModifySelfError("Cannot change your own role")

    if "full_name" in data and data["full_name"] is not None:
        user.full_name = data["full_name"]
    if "role" in data and data["role"] is not None:
        user.role = UserRole(data["role"]) if isinstance(data["role"], str) else data["role"]
    if "is_active" in data and data["is_active"] is not None:
        user.is_active = data["is_active"]

    await db.flush()
    await logger.ainfo("user_updated", user_id=str(user_id), fields=list(data.keys()))
    return user


async def deactivate_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    requesting_user_id: uuid.UUID,
) -> None:
    """Set is_active=False and delete all refresh tokens for the user."""
    if user_id == requesting_user_id:
        raise CannotModifySelfError("Cannot deactivate your own account")

    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")

    user.is_active = False
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.flush()
    await logger.ainfo("user_deactivated", user_id=str(user_id))


async def activate_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Set is_active=True for a user."""
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")

    user.is_active = True
    await db.flush()
    await logger.ainfo("user_activated", user_id=str(user_id))


async def admin_reset_user_password(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Generate a password-reset token for a user (admin-initiated).

    Returns the raw reset token string, or None on unexpected lookup failure.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")

    raw_token = await generate_password_reset_token(db, user.email)
    await logger.ainfo("admin_password_reset_initiated", user_id=str(user_id))
    return raw_token
