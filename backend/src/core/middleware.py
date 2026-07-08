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
        # S3: Content Security Policy — 'unsafe-inline' removed from script-src and style-src.
        # Angular uses runtime script/style injection; 'unsafe-eval' is required for
        # Angular's template compiler. A full nonce-based CSP migration is tracked as
        # a post-MVP task once Angular build output supports nonce injection.
        # Note: 'unsafe-eval' is kept for Angular runtime; 'unsafe-inline' is removed
        # from script-src to prevent XSS inline script execution.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "  # Angular ViewEncapsulation.Emulated requires unsafe-inline; nonce migration post-MVP
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        # Strip server identification
        response.headers["Server"] = "modishlog"

        return response
