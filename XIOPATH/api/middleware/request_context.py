"""
XIOPATH — Request Context Middleware (Phase S.3)
==================================================
Generates/propagates X-Request-ID for every request, stores it in
contextvars for structured logging, and logs request start/end.
"""

import time
import uuid
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.structured_logging import get_logger, bind_context, clear_context

logger = get_logger("RequestContext")

# Context variable for the current request ID — accessible from any code
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


def get_request_id() -> str:
    """Get the current request's correlation ID."""
    return request_id_var.get("")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Generates a unique X-Request-ID (or uses the one provided by the client)
    2. Stores it in contextvars for downstream structured logging
    3. Adds X-Request-ID to the response headers
    4. Logs request start and end with method, path, status, and duration
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or propagate request ID
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(req_id)

        # Bind to structlog context so all logs include it
        clear_context()
        bind_context(request_id=req_id)

        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        logger.info(
            "request_started",
            method=method,
            path=path,
            client_ip=client_ip,
        )

        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "request_failed",
                method=method,
                path=path,
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # Add request ID to response
        response.headers["X-Request-ID"] = req_id

        logger.info(
            "request_completed",
            method=method,
            path=path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
