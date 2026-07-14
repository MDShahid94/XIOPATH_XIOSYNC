"""
XIOPATH — Worker Boot Integration (Phase O.6)
================================================
Ontology-aware lifecycle hooks for colab workers.

This module provides functions that the colab_worker.py calls at each boot
stage. It communicates with the central API server (v2) to:
  1. Self-register as an actor on first boot
  2. Restore profile & Tailscale config from ontology records
  3. Record lifecycle operations (boot, connect, disconnect, shutdown)
  4. Send keepalive heartbeats
  5. Snapshot versions on config changes

All functions are resilient — they log warnings and continue if the API is
unreachable, since the worker must still function standalone.
"""

import os
import sys
import time
import json
import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger("WorkerBoot")


class WorkerBootIntegration:
    """
    Ontology lifecycle hooks for a Colab worker.

    Usage:
        boot = WorkerBootIntegration(
            server_base_url="http://100.x.x.x:8000",
            worker_id="colab_worker_1",
            worker_secret="...",
        )
        agent_id = boot.self_register(exit_node_ip="100.98.229.77")
        boot.restore_profiles()
        boot.restore_tailscale_config()
        boot.start_keepalive()
        ...
        boot.record_shutdown()
    """

    def __init__(
        self,
        server_base_url: str,
        worker_id: str,
        worker_secret: str = "",
        profile_id: str = "",
    ):
        self.server_base_url = server_base_url.rstrip("/")
        self.api_base = f"{self.server_base_url}/api/v2/actors"
        self.worker_id = worker_id
        self.worker_secret = worker_secret or os.environ.get("WORKER_SECRET", "")
        self.profile_id = profile_id or worker_id
        self.actor_id: Optional[str] = None
        self._keepalive_thread: Optional[threading.Thread] = None
        self._keepalive_running = False

        # Auth headers for API calls
        self._headers = self._build_auth_headers()

    def _build_auth_headers(self) -> Dict[str, str]:
        """Build JWT auth headers for v2 API calls."""
        headers = {"Content-Type": "application/json"}
        # Worker authenticates using JWT from the central server
        # In production, this would be a proper JWT exchange
        # For now, use the worker secret to get a JWT
        try:
            import jwt as pyjwt
            token = pyjwt.encode(
                {
                    "sub": self.worker_id,
                    "role": "worker",             # Dedicated worker role (not admin)
                    "token_type": "worker_service", # Distinguishes from user tokens
                    "type": "worker",
                },
                self.worker_secret or os.environ.get("XIOPATH_JWT_SECRET", "xiopath-dev-secret-change-in-production"),
                algorithm="HS256",
            )
            headers["Authorization"] = f"Bearer {token}"
        except ImportError:
            logger.warning("PyJWT not available, API calls will be unauthenticated")
        return headers

    def _api_call(self, method: str, path: str, json_data: dict = None) -> Optional[dict]:
        """Make a resilient API call. Returns response JSON or None on failure."""
        import requests
        url = f"{self.api_base}{path}"
        try:
            resp = requests.request(
                method, url,
                json=json_data,
                headers=self._headers,
                timeout=10,
            )
            if resp.status_code < 400:
                return resp.json()
            else:
                logger.warning(f"API {method} {path} returned {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"API {method} {path} failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # 1. SELF-REGISTRATION
    # ═══════════════════════════════════════════════════════════════════════

    def self_register(
        self,
        exit_node_ip: str = "",
        tailscale_ip: str = "",
        capabilities: list = None,
    ) -> Optional[str]:
        """
        Register this worker as an actor in the ontology.

        First checks if an actor with this worker_id alias already exists.
        If so, updates its state to 'active'. Otherwise creates a new actor.

        Returns the actor_id.
        """
        logger.info(f"🔗 Self-registering worker '{self.worker_id}' in ontology...")

        # Check if already registered
        result = self._api_call("GET", f"?actor_type=compute")
        if result:
            for actor in result.get("actors", []):
                if actor.get("alias") == self.worker_id or actor.get("id") == self.worker_id:
                    self.actor_id = actor["id"]
                    logger.info(f"✅ Worker already registered: {self.actor_id}")
                    # Update state to active
                    self._api_call("PATCH", f"/{self.actor_id}", {
                        "state": "active",
                        "health_status": "healthy",
                        "runtime_args": {
                            "exit_node_ip": exit_node_ip,
                            "tailscale_ip": tailscale_ip,
                            "boot_time": datetime.now(timezone.utc).isoformat(),
                            "capabilities": capabilities or ["browser", "inference"],
                        },
                    })
                    # Record boot operation
                    self._api_call("POST", f"/{self.actor_id}/operations", {
                        "operation": "initiation",
                        "to_state": "active",
                        "trigger": "worker_boot",
                        "rationale": f"Worker {self.worker_id} re-booted",
                        "outcome": "success",
                    })
                    return self.actor_id

        # Register as new actor
        result = self._api_call("POST", "", {
            "actor_type": "compute",
            "actor_subtype": "colab_runtime",
            "alias": self.worker_id,
            "role": "worker",
            "config": {
                "exit_node_ip": exit_node_ip,
                "tailscale_ip": tailscale_ip,
                "capabilities": capabilities or ["browser", "inference"],
                "profile_id": self.profile_id,
            },
            "metadata": {
                "boot_time": datetime.now(timezone.utc).isoformat(),
                "platform": "google_colab",
            },
        })

        if result and result.get("id"):
            self.actor_id = result["id"]
            logger.info(f"✅ Worker registered: {self.actor_id}")

            # Record initiation operation
            self._api_call("POST", f"/{self.actor_id}/operations", {
                "operation": "initiation",
                "from_state": "designed",
                "to_state": "active",
                "trigger": "worker_boot",
                "rationale": f"Initial boot of worker {self.worker_id}",
                "outcome": "success",
            })

            return self.actor_id
        else:
            logger.warning("⚠️ Self-registration failed. Worker will continue standalone.")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # 2. PROFILE RESTORE
    # ═══════════════════════════════════════════════════════════════════════

    def restore_profiles(self) -> list:
        """
        Query the ontology for profiles associated with this worker.
        Returns list of profile records for the caller to act on.
        """
        if not self.actor_id:
            return []

        result = self._api_call("GET", f"/{self.actor_id}/profiles")
        if not result:
            return []

        profiles = result.get("profiles", [])
        logger.info(f"📋 Found {len(profiles)} profile(s) in ontology for {self.worker_id}")

        for p in profiles:
            logger.info(
                f"  └─ {p.get('profile_type')}: {p.get('storage_path')} "
                f"(state={p.get('state')}, mode={p.get('persistence_mode')})"
            )

        return profiles

    def register_profile(
        self,
        profile_type: str,
        storage_path: str,
        persistence_mode: str = "periodic",
        save_interval: int = 600,
        account_identity: str = "",
    ) -> Optional[str]:
        """Register a new profile in the ontology."""
        if not self.actor_id:
            return None

        result = self._api_call("POST", "/profiles", {
            "actor_id": self.actor_id,
            "profile_type": profile_type,
            "storage_backend": "google_drive",
            "storage_path": storage_path,
            "persistence_mode": persistence_mode,
            "save_interval_seconds": save_interval,
            "account_identity": account_identity,
        })

        if result and result.get("profile_id"):
            logger.info(f"✅ Profile registered: {result['profile_id']} ({profile_type})")
            return result["profile_id"]
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # 3. TAILSCALE CONFIG RESTORE
    # ═══════════════════════════════════════════════════════════════════════

    def restore_tailscale_config(self) -> Optional[Dict]:
        """
        Query the ontology for runtime connections involving this worker.
        Returns the connection config for the caller to apply.
        """
        if not self.actor_id:
            return None

        result = self._api_call("GET", "/connections")
        if not result:
            return None

        connections = result.get("connections", [])
        # Find connections involving this worker
        worker_conns = [
            c for c in connections
            if c.get("source_actor_id") == self.actor_id
            or c.get("target_actor_id") == self.actor_id
        ]

        if not worker_conns:
            logger.info("No existing runtime connections found. Will use config defaults.")
            return None

        # Return the most recent connection config
        conn = worker_conns[0]
        logger.info(
            f"🔗 Found runtime connection: {conn.get('transport')} "
            f"(exit_node={conn.get('current_exit_node_ip')}, "
            f"routing={conn.get('routing_rule')})"
        )
        return conn

    def register_connection(
        self,
        target_actor_id: str,
        exit_node_ip: str,
        tailscale_ip: str,
        routing_rule: str = "worker_via_client_ip",
    ) -> Optional[str]:
        """Register a runtime connection from this worker to the central server."""
        if not self.actor_id:
            return None

        result = self._api_call("POST", "/connections", {
            "source_actor_id": self.actor_id,
            "target_actor_id": target_actor_id,
            "protocol": "tailnet_ws",
            "transport": "tailscale",
            "source_endpoint": tailscale_ip,
            "routing_rule": routing_rule,
            "proxy_config": {"socks5": "localhost:1055", "exit_node": exit_node_ip},
        })

        if result and result.get("connection_id"):
            logger.info(f"✅ Connection registered: {result['connection_id']}")
            return result["connection_id"]
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # 4. KEEPALIVE HEARTBEAT
    # ═══════════════════════════════════════════════════════════════════════

    def start_keepalive(self, interval_seconds: int = 30):
        """Start a background thread that sends heartbeats to the ontology."""
        if self._keepalive_running:
            return
        if not self.actor_id:
            logger.warning("Cannot start keepalive: no actor_id")
            return

        self._keepalive_running = True

        def heartbeat_loop():
            while self._keepalive_running:
                time.sleep(interval_seconds)
                try:
                    self._api_call("PATCH", f"/{self.actor_id}", {
                        "health_status": "healthy",
                        "runtime_args": {
                            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                        },
                    })
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")

        self._keepalive_thread = threading.Thread(
            target=heartbeat_loop, daemon=True, name="ontology-keepalive"
        )
        self._keepalive_thread.start()
        logger.info(f"💓 Keepalive started (every {interval_seconds}s)")

    def stop_keepalive(self):
        """Stop the keepalive thread."""
        self._keepalive_running = False

    # ═══════════════════════════════════════════════════════════════════════
    # 5. VERSION SNAPSHOT
    # ═══════════════════════════════════════════════════════════════════════

    def snapshot_version(
        self,
        change_summary: str,
        change_type: str = "patch",
        config_snapshot: dict = None,
    ) -> Optional[str]:
        """
        Create a version snapshot of the current worker configuration.

        Supports the human-gated approval model:
        - If the worker has a human collaborator, the version is created with
          requires_human_approval=True and approval_status='pending'
        - If no human collaborator, it's auto-approved
        """
        if not self.actor_id:
            return None

        # Build the config snapshot
        snapshot = config_snapshot or {}
        snapshot_json = json.dumps(snapshot, sort_keys=True, default=str)
        version_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()

        # Check if this agent has a human collaborator (via edges)
        edges_result = self._api_call("GET", f"/{self.actor_id}/edges?direction=incoming")
        has_human_collab = False
        if edges_result:
            for edge in edges_result.get("edges", []):
                if edge.get("edge_type") in ("manages", "collaborates_with"):
                    # Check if source is human type
                    source = self._api_call("GET", f"/{edge['source_id']}")
                    if source and source.get("agent", {}).get("agent_type") == "human":
                        has_human_collab = True
                        break

        # Determine approval model
        if has_human_collab:
            requires_approval = True
            approval_status = "pending"
        else:
            requires_approval = False
            approval_status = "auto_approved"

        # Create the version via direct DB (since we may not have a version API POST)
        # For now, record as an operation with the version metadata
        self._api_call("POST", f"/{self.actor_id}/operations", {
            "operation": "upgradation",
            "trigger": "config_change",
            "rationale": change_summary,
            "outcome": "success" if not requires_approval else "pending",
            "artifacts": {
                "version_hash": version_hash,
                "change_type": change_type,
                "requires_human_approval": requires_approval,
                "approval_status": approval_status,
                "config_snapshot_keys": list(snapshot.keys()),
            },
        })

        logger.info(
            f"🔖 Version snapshot: {change_type} ({approval_status}) — {change_summary}"
        )
        return version_hash

    # ═══════════════════════════════════════════════════════════════════════
    # LIFECYCLE EVENTS
    # ═══════════════════════════════════════════════════════════════════════

    def record_connected(self):
        """Record a successful connection to the central server."""
        if not self.actor_id:
            return
        self._api_call("POST", f"/{self.actor_id}/operations", {
            "operation": "initiation",
            "to_state": "active",
            "trigger": "ws_connected",
            "rationale": "WebSocket connection established to central server",
            "outcome": "success",
        })

    def record_disconnected(self, reason: str = "unknown"):
        """Record a disconnection event."""
        if not self.actor_id:
            return
        self._api_call("PATCH", f"/{self.actor_id}", {
            "health_status": "degraded",
        })
        self._api_call("POST", f"/{self.actor_id}/operations", {
            "operation": "degradation",
            "to_state": "degraded",
            "trigger": "ws_disconnected",
            "rationale": f"Disconnected: {reason}",
            "outcome": "acknowledged",
        })

    def record_shutdown(self):
        """Record worker shutdown. Stops keepalive and marks agent as terminated."""
        self.stop_keepalive()

        if not self.actor_id:
            return

        self._api_call("PATCH", f"/{self.actor_id}", {
            "state": "terminated",
            "health_status": "offline",
        })
        self._api_call("POST", f"/{self.actor_id}/operations", {
            "operation": "termination",
            "to_state": "terminated",
            "trigger": "worker_shutdown",
            "rationale": "Worker shutting down gracefully",
            "outcome": "success",
        })
        logger.info(f"🛑 Worker {self.worker_id} marked as terminated in ontology")

    def record_profile_backup(self, profile_type: str, success: bool, size_bytes: int = 0):
        """Record a profile backup event."""
        if not self.actor_id:
            return
        self._api_call("POST", f"/{self.actor_id}/operations", {
            "operation": "updation",
            "trigger": "periodic_backup",
            "rationale": f"Profile backup ({profile_type}): {'success' if success else 'failed'}",
            "outcome": "success" if success else "failed",
            "artifacts": {"profile_type": profile_type, "size_bytes": size_bytes},
        })
