"""
XIOPATH — Security Headers Middleware (Phase S.2)
====================================================
Adds CSP, X-Content-Type-Options, X-Frame-Options, and other
security headers to every HTTP response.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds industry-standard security headers to all responses.

    Headers set:
        - Content-Security-Policy (CSP)
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY
        - Referrer-Policy: strict-origin-when-cross-origin
        - X-XSS-Protection: 0 (modern browsers use CSP instead)
        - Strict-Transport-Security (production only)
        - Permissions-Policy (restrict browser features)
    """

    # CSP directives — restrictive but functional for API + WebSocket use
    CSP_POLICY = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws://localhost:* wss://localhost:* ws://100.*:* wss://100.*:*; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Core security headers
        response.headers["Content-Security-Policy"] = self.CSP_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable legacy XSS filter (CSP is the modern replacement)
        response.headers["X-XSS-Protection"] = "0"

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # HSTS in production only
        if os.environ.get("XIOPATH_ENV") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
