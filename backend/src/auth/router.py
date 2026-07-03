"""Auth API routes -- thin layer, all logic in service.py."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.rate_limit import limiter

from src.auth.dependencies import get_current_active_user, require_admin
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
from src.auth.models import User, UserRole
from src.auth.schemas import (
    AdminResetPasswordResponse,
    ForgotPasswordRequest,
    LogoutRequest,
    MessageResponse,
    OnboardRequest,
    OnboardResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UnlockUserRequest,
    UserInvite,
    UserListResponse,
    UserLogin,
    UserProfile,
    UserRegister,
    UserUpdate,
)
from src.auth.service import (
    activate_user,
    admin_reset_user_password,
    authenticate_user,
    build_token,
    create_business_and_owner,
    create_refresh_token,
    create_user,
    deactivate_user,
    generate_password_reset_token,
    get_user_by_id,
    list_users,
    refresh_access_token,
    reset_password,
    revoke_refresh_token,
    unlock_user,
    update_user,
)
from src.core.database import get_db

router = APIRouter()


@router.post("/onboard", response_model=OnboardResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def onboard_business(
    request: Request, data: OnboardRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    """Public endpoint — creates a Business and its owner User atomically."""
    try:
        business, user, access_token, refresh_token = await create_business_and_owner(db, data)
    except WeakPasswordError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT != "development",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return OnboardResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        business_id=str(business.id),
    )


@router.post(
    "/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED
)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a new user account. Requires an existing admin to be authenticated."""
    try:
        user = await create_user(db, body.email, body.password, body.full_name)
    except WeakPasswordError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request, body: UserLogin, response: Response, db: AsyncSession = Depends(get_db)
):
    """Authenticate and return a JWT access token and refresh token.

    The access token is also set as an HttpOnly cookie so that XSS cannot
    read it from JavaScript.  The JSON body is kept for backwards-compat
    with in-memory token handling on the frontend.
    """
    try:
        user = await authenticate_user(db, body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except AccountLockedError as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Account locked",
                "locked_until": e.locked_until.isoformat() + "Z",
            },
        )
    access_token = build_token(user)
    raw_refresh_token = await create_refresh_token(db, user)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT != "development",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Issue a new access token given a valid refresh token."""
    try:
        new_access_token = await refresh_access_token(db, body.refresh_token)
    except InvalidRefreshTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    return TokenResponse(access_token=new_access_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    """Revoke the refresh token (logout).

    Always returns 200 -- never reveals whether the token existed.
    Clears the access_token HttpOnly cookie.
    """
    await revoke_refresh_token(db, body.refresh_token)
    response.delete_cookie(key="access_token", path="/")
    return MessageResponse(message="Logged out successfully.")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """Request a password-reset token.

    Always returns 200 regardless of whether the email exists --
    we never reveal account existence.
    """
    await generate_password_reset_token(db, body.email)
    return MessageResponse(
        message="If an account with that email exists, a reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def do_reset_password(
    request: Request, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """Reset a user's password using a valid reset token."""
    try:
        await reset_password(db, body.token, body.new_password)
    except InvalidResetTokenError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except WeakPasswordError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MessageResponse(message="Password has been reset successfully.")


@router.patch("/admin/unlock", response_model=UserProfile)
async def admin_unlock_user(
    body: UnlockUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Reset account lockout for a given email. Admin only."""
    try:
        user = await unlock_user(db, body.email)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return user


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Return the authenticated user's profile."""
    return current_user


# ---------------------------------------------------------------------------
# Admin user management endpoints
# Static routes (/admin/users, /admin/users/invite) BEFORE parameterized
# ---------------------------------------------------------------------------


@router.get("/admin/users", response_model=UserListResponse)
async def admin_list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all users with pagination and optional search. Admin only."""
    items, total = await list_users(db, page=page, page_size=page_size, search=search)
    return UserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/admin/users/invite", response_model=UserProfile, status_code=status.HTTP_201_CREATED
)
async def admin_invite_user(
    body: UserInvite,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a new user account (admin invite). Admin only."""
    try:
        user = await create_user(db, body.email, body.password, body.full_name, role=UserRole(body.role))
    except WeakPasswordError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.get("/admin/users/{user_id}", response_model=UserProfile)
async def admin_get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get a single user by ID. Admin only."""
    try:
        user = await get_user_by_id(db, user_id)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return user


@router.patch("/admin/users/{user_id}", response_model=UserProfile)
async def admin_update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update a user's full_name, role, or is_active status. Admin only."""
    data = body.model_dump(exclude_none=True)
    try:
        user = await update_user(db, user_id, data, admin.id)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CannotModifySelfError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return user


@router.post("/admin/users/{user_id}/deactivate", response_model=MessageResponse)
async def admin_deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Deactivate a user account and revoke their tokens. Admin only."""
    try:
        await deactivate_user(db, user_id, admin.id)
    except CannotModifySelfError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MessageResponse(message="User deactivated successfully.")


@router.post("/admin/users/{user_id}/activate", response_model=MessageResponse)
async def admin_activate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Reactivate a deactivated user account. Admin only."""
    try:
        await activate_user(db, user_id)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MessageResponse(message="User activated successfully.")


@router.post("/admin/users/{user_id}/reset-password", response_model=AdminResetPasswordResponse)
async def admin_reset_password(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Generate a password-reset token for a user (admin-initiated). Admin only."""
    try:
        raw_token = await admin_reset_user_password(db, user_id)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate reset token — user email lookup failed",
        )
    return AdminResetPasswordResponse(
        message="Password reset token generated. Share this token with the user securely.",
        token=raw_token,
    )
