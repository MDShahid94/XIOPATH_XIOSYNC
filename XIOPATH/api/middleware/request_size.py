"""
XIOPATH — Request Size Limit Middleware (Phase S.1)
=====================================================
Rejects oversized request payloads before they reach endpoint handlers.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# 5 MB default — configurable via env
MAX_REQUEST_SIZE = int(__import__("os").environ.get("XIOPATH_MAX_REQUEST_SIZE", 5 * 1024 * 1024))


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests whose Content-Length exceeds MAX_REQUEST_SIZE.

    Returns 413 Payload Too Large for oversized requests.
    Requests without Content-Length are allowed through (streaming).
    """

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")

        if content_length and int(content_length) > MAX_REQUEST_SIZE:
            logger.warning(
                f"Request too large: {content_length} bytes from {request.client.host} "
                f"to {request.url.path} (limit: {MAX_REQUEST_SIZE})"
            )
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"Request body too large. Maximum size is {MAX_REQUEST_SIZE // (1024*1024)} MB.",
                },
            )

        return await call_next(request)
