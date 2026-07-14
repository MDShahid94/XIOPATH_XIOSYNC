"""
XIOPATH — Prometheus Metrics Collector Middleware
=====================================================
Starlette middleware that records per-request metrics and exposes
shared metric objects for other subsystems to instrument.
"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from prometheus_client import Counter, Gauge, Histogram

# ── Request-level metrics ──────────────────────────────────────────
REQUEST_COUNT = Counter(
    "xiopath_api_requests_total",
    "Total API requests",
    ["method", "path", "status_code"],
)

REQUEST_DURATION = Histogram(
    "xiopath_api_request_duration_seconds",
    "API request duration",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

RATE_LIMIT_HITS = Counter(
    "xiopath_rate_limit_hits_total",
    "Rate limit hits",
    ["path"],
)

# ── LLM metrics ───────────────────────────────────────────────────
LLM_REQUEST_COUNT = Counter(
    "xiopath_llm_requests_total",
    "Total LLM provider requests",
    ["provider", "model", "status"],
)

LLM_LATENCY = Histogram(
    "xiopath_llm_latency_seconds",
    "LLM request latency",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# ── Infrastructure gauges ─────────────────────────────────────────
WORKER_CONNECTED = Gauge(
    "xiopath_workers_connected",
    "Number of connected worker WebSocket clients",
)

MEMORY_NODES_TOTAL = Gauge(
    "xiopath_memory_nodes_total",
    "Total nodes in the memory graph",
)

CIRCUIT_BREAKER_STATE = Gauge(
    "xiopath_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["provider"],
)


# ── Middleware ─────────────────────────────────────────────────────
class MetricsMiddleware(BaseHTTPMiddleware):
    """Records method, path, status_code and latency for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start

        status_code = str(response.status_code)

        REQUEST_COUNT.labels(method=method, path=path, status_code=status_code).inc()
        REQUEST_DURATION.labels(method=method, path=path).observe(elapsed)

        return response
