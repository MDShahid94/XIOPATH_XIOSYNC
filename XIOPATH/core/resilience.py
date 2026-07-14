"""
resilience.py – Circuit breaker registry and degradation mode definitions.

Provides:
* ``ResilienceRegistry`` – Thread-safe registry of named
  :class:`~core.circuit_breaker.CircuitBreaker` instances with sensible
  defaults for the XIOPATH subsystems.
* ``DegradationMode`` – Static catalogue of graceful-degradation behaviours
  that the system can fall back on when a subsystem is down.
* Module-level singleton ``registry`` – Ready-to-import shared instance.
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default circuit-breaker presets
# ---------------------------------------------------------------------------

DEFAULT_BREAKERS: Dict[str, Dict[str, Any]] = {
    "llm_default": {
        "failure_threshold": 3,
        "recovery_timeout": 60,
    },
    "browser_default": {
        "failure_threshold": 5,
        "recovery_timeout": 120,
    },
    "database": {
        "failure_threshold": 3,
        "recovery_timeout": 30,
    },
    "ws_default": {
        "failure_threshold": 5,
        "recovery_timeout": 60,
    },
}


# ---------------------------------------------------------------------------
# Resilience registry
# ---------------------------------------------------------------------------

class ResilienceRegistry:
    """A thread-safe registry of named :class:`CircuitBreaker` instances.

    On first creation the registry is pre-populated with the breakers defined
    in :data:`DEFAULT_BREAKERS`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._initialise_defaults()

    # -- public API ---------------------------------------------------------

    def register(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        *,
        overwrite: bool = False,
    ) -> CircuitBreaker:
        """Register (or replace) a named circuit breaker.

        Parameters
        ----------
        name:
            Unique identifier for the breaker.
        failure_threshold:
            Consecutive failures before tripping.
        recovery_timeout:
            Seconds in OPEN before transitioning to HALF_OPEN.
        overwrite:
            If ``True``, silently replace an existing breaker with the same
            *name*.  Otherwise raise ``ValueError``.

        Returns
        -------
        CircuitBreaker
            The newly registered breaker instance.
        """
        with self._lock:
            if name in self._breakers and not overwrite:
                raise ValueError(
                    f"Circuit breaker '{name}' is already registered. "
                    "Pass overwrite=True to replace it."
                )
            breaker = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            self._breakers[name] = breaker
            logger.info(
                "[ResilienceRegistry] Registered breaker '%s' "
                "(threshold=%d, timeout=%.1fs)",
                name,
                failure_threshold,
                recovery_timeout,
            )
            return breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Return the breaker registered under *name*, or ``None``."""
        with self._lock:
            return self._breakers.get(name)

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> CircuitBreaker:
        """Return an existing breaker or create a new one with the given settings."""
        with self._lock:
            if name in self._breakers:
                return self._breakers[name]
        # Release the lock before calling register (which acquires it).
        return self.register(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Return a ``{name: breaker.to_dict()}`` snapshot for every breaker."""
        with self._lock:
            return {name: cb.to_dict() for name, cb in self._breakers.items()}

    # -- internals ----------------------------------------------------------

    def _initialise_defaults(self) -> None:
        """Pre-register the default breakers defined in :data:`DEFAULT_BREAKERS`."""
        for name, params in DEFAULT_BREAKERS.items():
            self.register(name, **params)

    # -- dunder -------------------------------------------------------------

    def __repr__(self) -> str:
        names = list(self._breakers.keys())
        return f"ResilienceRegistry(breakers={names})"


# ---------------------------------------------------------------------------
# Degradation modes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DegradationEntry:
    """Describes how the system should behave when a subsystem is down."""
    description: str
    fallback: str
    affects: str


class DegradationMode:
    """Static catalogue of graceful-degradation behaviours.

    Access individual modes via :pyattr:`DegradationMode.MODES` or the
    convenience class method :meth:`describe`.
    """

    MODES: Dict[str, _DegradationEntry] = {
        "llm_down": _DegradationEntry(
            description="The LLM provider is unreachable or returning errors.",
            fallback=(
                "Use cached responses where available. "
                "Queue new requests for retry when the circuit closes. "
                "Return a user-friendly error for interactive queries."
            ),
            affects="Agent loop, smart_llm, chat_loop",
        ),
        "db_down": _DegradationEntry(
            description="The local SQLite / ChromaDB database is unavailable.",
            fallback=(
                "Switch to in-memory buffering for new nodes. "
                "Persist buffered nodes once the database recovers. "
                "Disable features that require historical lookups."
            ),
            affects="database, memory_manager, ontology_ops",
        ),
        "worker_disconnected": _DegradationEntry(
            description=(
                "The background sync worker cannot reach the global server."
            ),
            fallback=(
                "Continue local-only operation. "
                "Queue outgoing sync payloads in the push deque. "
                "Alert the user that federated features are degraded."
            ),
            affects="sync_worker, worker_boot_integration",
        ),
        "chromadb_down": _DegradationEntry(
            description="ChromaDB vector store is unreachable.",
            fallback=(
                "Fall back to keyword / FTS-based retrieval. "
                "Skip embedding writes and queue them for later. "
                "Log a warning so operators can investigate."
            ),
            affects="memory_manager (vector layer)",
        ),
    }

    @classmethod
    def describe(cls, mode_key: str) -> Optional[Dict[str, str]]:
        """Return a plain-dict description for *mode_key*, or ``None``."""
        entry = cls.MODES.get(mode_key)
        if entry is None:
            return None
        return {
            "mode": mode_key,
            "description": entry.description,
            "fallback": entry.fallback,
            "affects": entry.affects,
        }

    @classmethod
    def all_modes(cls) -> Dict[str, Dict[str, str]]:
        """Return descriptions for every registered degradation mode."""
        return {k: cls.describe(k) for k in cls.MODES}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

registry = ResilienceRegistry()
