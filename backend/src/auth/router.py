"""Auth API routes -- thin layer, all logic in service.py."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidResetTokenError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from src.auth.models import User
from src.auth.schemas import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserLogin,
    UserProfile,
    UserRegister,
)
from src.auth.service import (
    authenticate_user,
    build_token,
    create_user,
    generate_password_reset_token,
    reset_password,
)
from src.core.database import get_db

router = APIRouter()


@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    """Create a new user account."""
    try:
        user = await create_user(db, body.email, body.password, body.full_name)
    except WeakPasswordError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and return a JWT access token."""
    try:
        user = await authenticate_user(db, body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except AccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked until {e.locked_until.isoformat()}",
        )
    token = build_token(user)
    return TokenResponse(access_token=token)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Request a password-reset token.

    Always returns 200 regardless of whether the email exists --
    we never reveal account existence.
    """
    await generate_password_reset_token(db, body.email)
    return MessageResponse(message="If an account with that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def do_reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset a user's password using a valid reset token."""
    try:
        await reset_password(db, body.token, body.new_password)
    except InvalidResetTokenError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except WeakPasswordError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MessageResponse(message="Password has been reset successfully.")


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Return the authenticated user's profile."""
    return current_user
