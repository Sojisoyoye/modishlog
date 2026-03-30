"""Auth API routes -- thin layer, all logic in service.py."""

from fastapi import APIRouter

router = APIRouter()


# TODO: POST /login -- authenticate user and return JWT tokens
# TODO: POST /refresh -- refresh an expired access token
# TODO: POST /logout -- revoke current session token
# TODO: POST /register -- create a new user account
# TODO: POST /forgot-password -- send password reset email
