"""Production security middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers on every response and strip the Server header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Legacy XSS filter (IE/Edge)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Disable browser features not needed by the app
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # HSTS — Nginx enforces this in production; middleware adds it for defence-in-depth
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Content Security Policy — tightened per domain in Nginx for production
        # 'unsafe-inline' required by Angular's runtime inline styles/scripts.
        # Switch to nonce-based CSP after Angular build is configured with nonces (post-MVP).
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        # Strip server identification
        response.headers["Server"] = "modishlog"

        return response
