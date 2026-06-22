"""Auth API routes -- thin layer, all logic in service.py."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings

from src.auth.dependencies import get_current_active_user, require_admin
from src.auth.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidResetTokenError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WeakPasswordError,
)
from src.auth.models import User
from src.auth.schemas import (
    ForgotPasswordRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UnlockUserRequest,
    UserLogin,
    UserProfile,
    UserRegister,
)
from src.auth.service import (
    authenticate_user,
    build_token,
    create_refresh_token,
    create_user,
    generate_password_reset_token,
    refresh_access_token,
    reset_password,
    revoke_refresh_token,
    unlock_user,
)
from src.core.database import get_db

router = APIRouter()


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
async def login(
    body: UserLogin, response: Response, db: AsyncSession = Depends(get_db)
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
                "locked_until": e.locked_until.isoformat(),
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
async def forgot_password(
    body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
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
async def do_reset_password(
    body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
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
