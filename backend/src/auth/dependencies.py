"""Auth dependencies for FastAPI Depends injection."""

import uuid

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import SubscriptionStatus, User, UserRole
from src.core.database import get_db
from src.core.security import decode_access_token
from src.core.token_revocation import is_jti_revoked

logger = structlog.get_logger()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT from HttpOnly cookie or Authorization header.

    Cookie takes precedence; falls back to Bearer token for clients that
    cannot set cookies (e.g., server-to-server or legacy clients).
    """
    token = request.cookies.get("access_token") or bearer_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise ValueError("Missing sub claim")
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # task #226: reject before the DB round-trip -- cheaper to check a
    # revoked jti here than to look the user up first. Same generic
    # message as the block above, not a distinct one, so a client can't
    # use the response to tell "revoked" apart from "malformed"/"expired".
    jti = payload.get("jti")
    if jti and await is_jti_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, user_uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user's account is active.

    Also cuts off an already-issued access token mid-session for a
    business pending self-service deletion (task #252) -- revoking
    refresh tokens alone only stops renewal, and an access token can stay
    validly signed for up to ACCESS_TOKEN_EXPIRE_MINUTES (24h in prod)
    after deletion is scheduled. OWNER is exempted so they can still reach
    the cancel-deletion endpoint (itself gated on this same dependency)
    during the grace period; every other role in the business is cut off
    immediately, matching what login-time blocking already does for new
    sessions.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    if (
        current_user.role != UserRole.OWNER
        and current_user.business is not None
        and current_user.business.deletion_requested_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is scheduled for deletion.",
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user has admin-equivalent access.

    OWNER (assigned to every self-serve business owner by /auth/onboard) is
    treated as admin-equivalent within their own business — every endpoint
    gated on this dependency scopes its data access by business_id, so this
    never grants cross-tenant reach (task 177).
    """
    if current_user.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


async def require_owner(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user is the business OWNER specifically --
    stricter than require_admin. Used for actions that affect the whole
    business (e.g. scheduling account deletion, task #252) where even an
    ADMIN teammate shouldn't be able to act unilaterally.
    """
    if current_user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required",
        )
    return current_user


async def require_any_role(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Allow any authenticated and active user regardless of role."""
    return current_user


async def require_active_subscription(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Block writes for read_only businesses (task #240) -- the billing
    spec's 3-day-grace-period lapse behavior. GET/HEAD/OPTIONS always pass
    (data stays visible/exportable even when read_only); only
    state-changing methods are gated. No hard lockout, ever -- read_only
    is the only status this blocks; trialing/active/past_due keep full
    write access (past_due is the grace period itself).
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if (
        current_user.business is not None
        and current_user.business.subscription_status == SubscriptionStatus.READ_ONLY
    ):
        await logger.awarning(
            "subscription_gate_blocked_write",
            business_id=str(current_user.business_id),
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your subscription is read-only. Renew to restore write access.",
        )


async def get_current_business_id(
    current_user: User = Depends(get_current_active_user),
) -> uuid.UUID:
    """Extract business_id from the authenticated user. Raises 400 if not set."""
    if current_user.business_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a business",
        )
    return current_user.business_id
