"""
circuit_breaker.py – Generic, thread-safe three-state circuit breaker.

States
------
CLOSED     – Normal operation; requests pass through.
OPEN       – Failing fast; requests are rejected immediately.
HALF_OPEN  – Probing recovery; a single request is allowed to test the service.

Transitions
-----------
CLOSED  → OPEN      : After `failure_threshold` consecutive failures.
OPEN    → HALF_OPEN : After `recovery_timeout` seconds have elapsed.
HALF_OPEN → CLOSED  : On a successful probe.
HALF_OPEN → OPEN    : On a failed probe (resets the timeout window).
"""

import logging
import threading
import time
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    """Possible states for a circuit breaker."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Circuit breaker implementation
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """A generic, thread-safe three-state circuit breaker.

    Parameters
    ----------
    name : str
        Human-readable identifier used in log messages.
    failure_threshold : int
        Number of consecutive failures required to trip the breaker
        (CLOSED → OPEN).  Defaults to ``3``.
    recovery_timeout : float
        Seconds to wait in the OPEN state before transitioning to
        HALF_OPEN.  Defaults to ``60``.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._lock = threading.Lock()
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None

    # -- properties ---------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Return the current state (may trigger OPEN → HALF_OPEN check)."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    # -- public API ---------------------------------------------------------

    def allow_request(self) -> bool:
        """Return ``True`` if a request may proceed under the current state.

        * CLOSED     → always allowed
        * OPEN       → allowed only when the recovery timeout has expired
                        (auto-transitions to HALF_OPEN)
        * HALF_OPEN  → allowed (one probe request)
        """
        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                return True
            # OPEN
            return False

    def record_success(self) -> None:
        """Record a successful call and reset the breaker if probing."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.CLOSED)
            # In CLOSED state, just reset the failure counter.
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call and potentially trip the breaker."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed – reopen.
                self._transition(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._opened_at = None
            if old_state != CircuitState.CLOSED:
                logger.info(
                    "[CircuitBreaker:%s] Manually reset from %s → CLOSED",
                    self.name,
                    old_state.value,
                )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of the breaker's state."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self._last_failure_time,
                "opened_at": self._opened_at,
            }

    # -- internals ----------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """Transition OPEN → HALF_OPEN if the recovery timeout has elapsed.

        Must be called while holding ``self._lock``.
        """
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        """Perform a state transition and log it.

        Must be called while holding ``self._lock``.
        """
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._opened_at = None

        logger.info(
            "[CircuitBreaker:%s] %s → %s  (failures=%d/%d)",
            self.name,
            old_state.value,
            new_state.value,
            self._failure_count,
            self.failure_threshold,
        )

    # -- dunder -------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self._state.value!r}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )
