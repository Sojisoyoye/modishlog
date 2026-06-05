"""Auth business logic -- all async operations."""

import hashlib
import re
import secrets
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetTokenError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from src.auth.models import PasswordResetToken, RefreshToken, User, UserRole
from src.core.config import settings
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
        role=UserRole.ADMIN,
        failed_login_attempts=0,
    )
    db.add(user)
    await db.flush()
    await logger.ainfo("user_registered", user_id=str(user.id), email=email)
    return user


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

    # Check lockout
    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        await logger.awarn("login_locked", email=email, locked_until=str(user.locked_until))
        raise AccountLockedError(user.locked_until)

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            await logger.awarn("account_locked", email=email)
        await db.flush()
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

    token_str = _uuid.uuid4().hex  # 32-char hex string
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token_str,
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS),
        used=False,
    )
    db.add(reset_token)
    await db.flush()
    await logger.ainfo("password_reset_token_created", user_id=str(user.id))
    return token_str


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
        select(PasswordResetToken).where(PasswordResetToken.token == token)
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
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

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


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    """Revoke a refresh token by recording the revocation timestamp.

    This is a no-op if the token does not exist (idempotent logout).
    """
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
