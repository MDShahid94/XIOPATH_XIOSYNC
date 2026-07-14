"""
Enterprise Rate Limiter Middleware
===================================
In-memory token-bucket per client IP with configurable thresholds.

Thresholds are stored as class-level defaults but can be updated at runtime
via the admin config API (/api/v1/admin/config).

For multi-instance deployments, swap the _buckets dict for a Redis backend.
"""

import time
import logging
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter with per-path and per-IP granularity."""

    # These are the runtime-configurable defaults.
    # Updated via SecurityConfig.update() from the admin panel.
    _config = {
        "general_rpm": 60,
        "auth_rpm": 10,
        "agent_rpm": 5,
        "sync_rpm": 30,
    }

    def __init__(self, app, **kwargs):
        super().__init__(app)
        # Override defaults with any init kwargs
        for k, v in kwargs.items():
            if k in self._config:
                self._config[k] = v
        self._buckets = defaultdict(lambda: {"tokens": 0.0, "last_refill": 0.0})
        logger.info(f"RateLimiter initialized: {self._config}")

    @classmethod
    def update_config(cls, **kwargs):
        """Update rate limits at runtime (called from admin API)."""
        for k, v in kwargs.items():
            if k in cls._config and isinstance(v, (int, float)):
                cls._config[k] = int(v)
                logger.info(f"RateLimiter config updated: {k}={v}")

    def _get_rpm_for_path(self, path: str) -> int:
        """Determine the rate limit based on the request path."""
        if "/auth/" in path:
            return self._config["auth_rpm"]
        if "/agent/execute" in path or "/agent/infer" in path:
            return self._config["agent_rpm"]
        if "/sync/" in path:
            return self._config["sync_rpm"]
        return self._config["general_rpm"]

    async def dispatch(self, request: Request, call_next):
        # Skip healthcheck and docs
        path = request.url.path
        if path in ("/", "/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        rpm = self._get_rpm_for_path(path)

        # Token bucket logic
        bucket_key = f"{client_ip}:{path.split('/')[3] if len(path.split('/')) > 3 else 'root'}"
        bucket = self._buckets[bucket_key]
        now = time.time()
        elapsed = now - bucket["last_refill"]

        # Refill tokens proportionally
        bucket["tokens"] = min(float(rpm), bucket["tokens"] + elapsed * (rpm / 60.0))
        bucket["last_refill"] = now

        if bucket["tokens"] < 1.0:
            retry_after = int(60 / max(rpm, 1))
            logger.warning(f"Rate limit exceeded for {client_ip} on {path} ({rpm} RPM)")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        bucket["tokens"] -= 1.0
        response = await call_next(request)
        return response
