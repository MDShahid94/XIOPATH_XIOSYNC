"""
XIOPATH — Tenant Scope Middleware (Phase M.6)
================================================
Injects TenantContext into request.state based on the authenticated user.
Downstream handlers use this to scope database queries and vault access.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.tenant_context import TenantContext

logger = logging.getLogger(__name__)

# Routes that don't require tenant context (public endpoints)
PUBLIC_PATHS = {
    "/", "/docs", "/redoc", "/openapi.json",
    "/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready",
    "/api/v1/auth/login", "/api/v1/auth/signup",
    "/api/v1/marketplace/browse", "/api/v1/marketplace/search",
    "/metrics",
}


class TenantScopeMiddleware(BaseHTTPMiddleware):
    """
    Injects TenantContext into request.state for multi-tenancy.
    
    For authenticated routes, extracts user info from the JWT-decoded
    user state (set by the auth dependency) and creates a TenantContext.
    
    For public routes, sets a default anonymous context.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip tenant scoping for public paths
        is_public = path in PUBLIC_PATHS or path.startswith("/api/v1/marketplace/browse") or path.startswith("/api/v1/marketplace/search")

        if is_public:
            request.state.tenant = TenantContext(
                user_id="anonymous",
                role="user",
            )
        else:
            # Try to extract user from auth state
            # Note: The actual JWT validation happens in the auth dependency
            # This middleware just sets up the tenant context for convenience
            user = getattr(request.state, "user", None)
            if user and isinstance(user, dict):
                request.state.tenant = TenantContext(
                    user_id=user.get("sub", "unknown"),
                    role=user.get("role", "user"),
                    session_id=user.get("session_id"),
                )
            else:
                # Auth not yet resolved — set a placeholder
                # The actual auth check happens in route dependencies
                request.state.tenant = TenantContext(
                    user_id="pending",
                    role="user",
                )

        response = await call_next(request)
        return response
