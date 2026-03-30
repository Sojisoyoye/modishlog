"""Auth business logic -- all async operations."""

import re
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from src.auth.models import User
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
