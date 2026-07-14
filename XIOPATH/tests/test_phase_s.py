"""
Tests for Phase S — Security & Observability
===============================================
Tests security headers, request size limits, structured logging,
metrics endpoint, circuit breaker, and resilience registry.
"""
import pytest
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════════
# S.2: Security Headers
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """Verify security headers are present on all responses."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from api.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_csp_header_present(self):
        res = self.client.get("/")
        assert "content-security-policy" in res.headers
        csp = res.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_x_content_type_options(self):
        res = self.client.get("/")
        assert res.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self):
        res = self.client.get("/")
        assert res.headers.get("x-frame-options") == "DENY"

    def test_referrer_policy(self):
        res = self.client.get("/")
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_request_id_generated(self):
        res = self.client.get("/")
        assert "x-request-id" in res.headers
        # Should be a valid UUID
        req_id = res.headers["x-request-id"]
        assert len(req_id) == 36  # UUID format

    def test_request_id_propagated(self):
        custom_id = "test-correlation-123"
        res = self.client.get("/", headers={"X-Request-ID": custom_id})
        assert res.headers.get("x-request-id") == custom_id


# ═══════════════════════════════════════════════════════════════════════════
# S.4: Metrics Endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestMetricsEndpoint:
    """Verify Prometheus metrics are exposed."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from api.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_metrics_endpoint_returns_prometheus_format(self):
        res = self.client.get("/metrics")
        assert res.status_code == 200
        # Prometheus text format contains '# HELP' and '# TYPE' lines
        body = res.text
        assert "# HELP" in body or "# TYPE" in body or "xiopath" in body

    def test_metrics_tracks_requests(self):
        # Make a request to generate metrics
        self.client.get("/")
        res = self.client.get("/metrics")
        assert res.status_code == 200
        assert "xiopath_api_requests_total" in res.text


# ═══════════════════════════════════════════════════════════════════════════
# S.5: Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """Test three-state circuit breaker transitions."""

    def test_initial_state_closed(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_init", failure_threshold=3, recovery_timeout=60)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_closed_to_open_on_failures(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_open", failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # 1 failure, threshold is 2
        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # 2 failures = threshold

    def test_open_blocks_requests(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_block", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_open_to_half_open_after_timeout(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_half", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)  # Wait for recovery timeout
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_to_closed_on_success(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_recover", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_reopen", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        from core.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_reset", failure_threshold=3, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Reset counter
        cb.record_failure()
        # Should still be CLOSED (only 1 failure since reset)
        assert cb.state == CircuitState.CLOSED

    def test_to_dict(self):
        from core.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker("test_dict", failure_threshold=3, recovery_timeout=60)
        d = cb.to_dict()
        assert d["name"] == "test_dict"
        assert d["state"] == "closed"
        assert d["failure_count"] == 0


class TestResilienceRegistry:
    """Test the resilience registry singleton."""

    def test_default_breakers_registered(self):
        from core.resilience import registry
        states = registry.get_all_states()
        assert "llm_default" in states
        assert "browser_default" in states
        assert "database" in states
        assert "ws_default" in states

    def test_get_or_create(self):
        from core.resilience import ResilienceRegistry
        r = ResilienceRegistry()
        # First call creates
        cb1 = r.get_or_create("test_goc", failure_threshold=5, recovery_timeout=30)
        # Second call returns same instance
        cb2 = r.get_or_create("test_goc", failure_threshold=99, recovery_timeout=99)
        assert cb1 is cb2  # Same object

    def test_degradation_modes(self):
        from core.resilience import DegradationMode
        modes = DegradationMode.all_modes()
        assert "llm_down" in modes
        assert "db_down" in modes
        assert "worker_disconnected" in modes
        assert "chromadb_down" in modes


# ═══════════════════════════════════════════════════════════════════════════
# S.3: Structured Logging
# ═══════════════════════════════════════════════════════════════════════════

class TestStructuredLogging:
    """Test structured logging configuration."""

    def test_configure_logging_no_crash(self):
        from core.structured_logging import configure_logging
        # Should not raise
        configure_logging(json_output=False)

    def test_get_logger_returns_bound_logger(self):
        from core.structured_logging import get_logger
        logger = get_logger("TestModule")
        assert logger is not None
        # Should be callable
        logger.info("test_message", key="value")

    def test_bind_and_clear_context(self):
        from core.structured_logging import bind_context, clear_context
        bind_context(request_id="test-123", agent_id="agent-1")
        clear_context()  # Should not raise
