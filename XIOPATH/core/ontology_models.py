"""
XIOPATH — Ontology Models (v5.0)
==================================
Python dataclasses for the Universal Actor Ontology schema.
These provide type-safe interfaces over the raw SQLAlchemy text queries
in DatabaseManager, enabling IDE support and validation.

Design principles:
  - Three Primitives: Identity (actors), Knowledge (memory), Action (capabilities)
  - Dataclasses over ORMs — keep it lightweight, serialization-friendly
  - JSON fields stored as dicts in Python, serialized to TEXT in SQLite
  - UUIDv7 IDs generated via uuid7() for time-sortable uniqueness
  - All timestamps are UTC datetime objects
"""

import json
import uuid
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


# ─── UUIDv7 Generator ────────────────────────────────────────────────────────
def uuid7() -> str:
    """Generate a UUIDv7 (time-ordered) as a string.
    RFC 9562 compliant: 48-bit timestamp + 4-bit version + 12-bit rand_a
    + 2-bit variant + 62-bit rand_b.
    """
    import os
    timestamp_ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)  # 80 bits of randomness

    # High 48 bits: millisecond timestamp
    uuid_int = (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    # Next 4 bits: version 7
    uuid_int |= 0x7 << 76
    # Next 12 bits: rand_a (from first 2 random bytes, masked to 12 bits)
    uuid_int |= (int.from_bytes(rand_bytes[0:2], 'big') & 0x0FFF) << 64
    # Next 2 bits: variant 10
    uuid_int |= 0b10 << 62
    # Remaining 62 bits: rand_b (from remaining 8 random bytes, masked to 62 bits)
    uuid_int |= int.from_bytes(rand_bytes[2:10], 'big') & 0x3FFFFFFFFFFFFFFF

    return str(uuid.UUID(int=uuid_int))


def utcnow() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


# ─── Lifecycle Constants ─────────────────────────────────────────────────────
# NOTE: These serve as FALLBACK defaults. In v5.0, the type_registry table
# is the authoritative source. These constants remain for backward compatibility
# and are used when the type_registry is not yet initialized.

LIFECYCLE_STATES = {
    # Pre-birth
    "proposed", "designing", "implementing", "validating",
    # Birth
    "initializing",
    # Operational
    "active", "updating", "suspended", "migrating",
    # End-of-life
    "terminating", "terminated", "archived",
}

LIFECYCLE_PHASES = {"pre_birth", "birth", "operational", "end_of_life"}

ACTOR_TYPES = {"human", "ai", "compute"}

# ─── Actor Subtypes (per actor_type) ─────────────────────────────────────────
# Official built-in subtypes. Creators extend via type_registry API.
ACTOR_SUBTYPES = {
    "human":     {"admin", "member", "creator"},
    "ai":        {"llm_engine", "embedding_engine"},
    "compute":   {"api_server", "worker_node"},
}

OPERATION_TYPES = {
    "proposition", "design", "implementation",
    "validation", "initiation", "updation",
    "suspension", "migration", "termination",
    "archival", "rollback",
}

EDGE_TYPES = {
    "manages", "delegates_to", "collaborates_with",
    "provides", "owns",
}

EVENT_TYPES = {
    "action_executed", "error", "state_change", "heartbeat",
    "tool_invoked", "auth_event", "metric",
}

SEVERITY_LEVELS = {"debug", "info", "warn", "error", "critical"}

# Backward-compatible aliases (will be removed in v6.0)
AGENT_TYPES = ACTOR_TYPES
AGENT_SUBTYPES = ACTOR_SUBTYPES


# ─── Helper: JSON serialization ─────────────────────────────────────────────

def _to_json(val: Any) -> Optional[str]:
    """Serialize a Python object to JSON string, or None."""
    if val is None:
        return None
    return json.dumps(val, default=str)


def _from_json(val: Optional[str]) -> Any:
    """Deserialize a JSON string to Python object, or None."""
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# ═════════════════════════════════════════════════════════════════════════════
# MODELS
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Actor:
    """Universal autonomous entity: human, AI, or compute."""
    id: str = field(default_factory=uuid7)
    actor_type: str = "ai"              # human | ai | compute (extensible via type_registry)
    actor_subtype: Optional[str] = None # admin | llm_engine | worker_node | ...
    role: Optional[str] = None          # orchestrator | worker | gateway
    alias: Optional[str] = None         # Human-readable: "Colab Worker Alpha"
    parent_id: Optional[str] = None     # → actors.id

    state: str = "proposed"             # Current lifecycle state
    lifecycle_phase: str = "pre_birth"  # Coarse phase

    config: Optional[Dict] = None       # Immutable init args
    runtime_state: Optional[Dict] = None  # Mutable live state

    trust_tier: str = "newcomer"        # newcomer | contributor | trusted | core | admin
    last_heartbeat: Optional[datetime] = None
    health_status: str = "unknown"      # healthy | degraded | offline | unknown

    created_at: datetime = field(default_factory=utcnow)
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None    # → actors.id
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        """Convert to a dict suitable for SQL INSERT."""
        return {
            "id": self.id,
            "actor_type": self.actor_type,
            "actor_subtype": self.actor_subtype,
            "role": self.role,
            "alias": self.alias,
            "parent_id": self.parent_id,
            "state": self.state,
            "lifecycle_phase": self.lifecycle_phase,
            "config": _to_json(self.config),
            "runtime_state": _to_json(self.runtime_state),
            "trust_tier": self.trust_tier,
            "last_heartbeat": self.last_heartbeat,
            "health_status": self.health_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "metadata": _to_json(self.metadata),
        }

# Backward-compatible alias
Agent = Actor


@dataclass
class Operation:
    """Lifecycle operation record with collaborative tracking."""
    id: str = field(default_factory=uuid7)
    actor_id: str = ""
    operation: str = ""                 # proposition | design | implementation | ...
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    trigger: Optional[str] = None       # user_command | schedule | auto | error | system

    initiated_by: str = ""              # → actors.id
    collaborators: Optional[List[Dict]] = None  # [{actor_id, role_in_operation}]

    scope: Optional[str] = None         # actor | component | organization
    depth_level: int = 0
    parent_operation_id: Optional[str] = None

    artifacts: Optional[Dict] = None
    rationale: Optional[str] = None
    outcome: Optional[str] = None       # success | partial | failed | pending

    metadata: Optional[Dict] = None
    started_at: datetime = field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor_id": self.actor_id,
            "operation": self.operation,
            "from_state": self.from_state, "to_state": self.to_state,
            "trigger": self.trigger, "initiated_by": self.initiated_by,
            "collaborators": _to_json(self.collaborators),
            "scope": self.scope, "depth_level": self.depth_level,
            "parent_operation_id": self.parent_operation_id,
            "artifacts": _to_json(self.artifacts),
            "rationale": self.rationale, "outcome": self.outcome,
            "metadata": _to_json(self.metadata),
            "started_at": self.started_at, "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }

# Backward-compatible alias
AgentOperation = Operation


@dataclass
class ActorEdge:
    """Typed directed relationship between two actors."""
    id: str = field(default_factory=uuid7)
    source_id: str = ""
    target_id: str = ""
    edge_type: str = ""                 # manages | delegates_to | collaborates_with | ...
    config: Optional[Dict] = None
    weight: float = 1.0
    bidirectional: bool = False
    state: str = "active"
    created_at: datetime = field(default_factory=utcnow)
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "source_id": self.source_id,
            "target_id": self.target_id, "edge_type": self.edge_type,
            "config": _to_json(self.config), "weight": self.weight,
            "bidirectional": self.bidirectional, "state": self.state,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "metadata": _to_json(self.metadata),
        }

# Backward-compatible alias
AgentEdge = ActorEdge


@dataclass
class Capability:
    """Registered capability (tool/ability) in the platform."""
    id: str = field(default_factory=uuid7)
    name: str = ""
    capability_type: str = ""           # browser | api | plugin | llm | system (extensible via type_registry)
    version: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[Dict] = None
    output_schema: Optional[Dict] = None
    config: Optional[Dict] = None
    execution_mode: str = "sync"        # sync | async | streaming
    timeout_ms: int = 30000
    retry_policy: Optional[Dict] = None
    state: str = "active"
    created_at: datetime = field(default_factory=utcnow)
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "capability_type": self.capability_type,
            "version": self.version, "description": self.description,
            "input_schema": _to_json(self.input_schema),
            "output_schema": _to_json(self.output_schema),
            "config": _to_json(self.config),
            "execution_mode": self.execution_mode,
            "timeout_ms": self.timeout_ms,
            "retry_policy": _to_json(self.retry_policy),
            "state": self.state, "created_at": self.created_at,
            "updated_at": self.updated_at, "metadata": _to_json(self.metadata),
        }

# Backward-compatible alias
Tool = Capability


@dataclass
class CapabilityGrant:
    """Permission granting an actor access to a capability."""
    id: str = field(default_factory=uuid7)
    actor_id: str = ""
    capability_id: str = ""
    granted_by: str = ""
    scope: str = "full"                 # full | read_only | execute_only | limited
    constraints: Optional[Dict] = None
    expires_at: Optional[datetime] = None
    state: str = "active"
    created_at: datetime = field(default_factory=utcnow)
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor_id": self.actor_id,
            "capability_id": self.capability_id, "granted_by": self.granted_by,
            "scope": self.scope, "constraints": _to_json(self.constraints),
            "expires_at": self.expires_at, "state": self.state,
            "created_at": self.created_at, "revoked_at": self.revoked_at,
            "revoked_by": self.revoked_by, "metadata": _to_json(self.metadata),
        }


@dataclass
class Event:
    """Append-only telemetry/audit event."""
    id: str = field(default_factory=uuid7)
    actor_id: str = ""
    event_type: str = ""                # action_executed | error | state_change | ...
    severity: str = "info"
    summary: Optional[str] = None
    payload: Optional[Dict] = None
    correlation_id: Optional[str] = None
    operation_id: Optional[str] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor_id": self.actor_id,
            "event_type": self.event_type, "severity": self.severity,
            "summary": self.summary, "payload": _to_json(self.payload),
            "correlation_id": self.correlation_id,
            "operation_id": self.operation_id,
            "source_ip": self.source_ip, "user_agent": self.user_agent,
            "created_at": self.created_at, "metadata": _to_json(self.metadata),
        }


# ═════════════════════════════════════════════════════════════════════════════
# IDENTITY EXTENSION MODELS
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Connection:
    """Inter-actor network connection (Tailscale tunnel, exit node routing)."""
    id: str = field(default_factory=uuid7)
    source_actor_id: str = ""
    target_actor_id: str = ""
    protocol: str = ""                    # tailnet_http | tailnet_ws | tailnet_socks5 | direct_http
    transport: str = ""                   # tailscale | wireguard | direct | tor
    source_endpoint: Optional[str] = None
    target_endpoint: Optional[str] = None
    current_exit_node_ip: Optional[str] = None
    default_exit_node_ip: Optional[str] = None
    exit_node_actor_id: Optional[str] = None
    proxy_config: Optional[Dict] = None
    routing_rule: Optional[str] = None    # host_via_admin_ip | worker_via_client_ip | dynamic | direct
    pinned_services: Optional[List[Dict]] = None
    auth_state_path: Optional[str] = None
    auth_state_storage: Optional[str] = None
    auth_persistence: Optional[str] = None
    state: str = "pending"
    last_ping_ms: Optional[int] = None
    last_verified_at: Optional[datetime] = None
    exit_node_switched_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=utcnow)
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "source_actor_id": self.source_actor_id,
            "target_actor_id": self.target_actor_id,
            "protocol": self.protocol, "transport": self.transport,
            "source_endpoint": self.source_endpoint,
            "target_endpoint": self.target_endpoint,
            "current_exit_node_ip": self.current_exit_node_ip,
            "default_exit_node_ip": self.default_exit_node_ip,
            "exit_node_actor_id": self.exit_node_actor_id,
            "proxy_config": _to_json(self.proxy_config),
            "routing_rule": self.routing_rule,
            "pinned_services": _to_json(self.pinned_services),
            "auth_state_path": self.auth_state_path,
            "auth_state_storage": self.auth_state_storage,
            "auth_persistence": self.auth_persistence,
            "state": self.state, "last_ping_ms": self.last_ping_ms,
            "last_verified_at": self.last_verified_at,
            "exit_node_switched_at": self.exit_node_switched_at,
            "created_at": self.created_at, "metadata": _to_json(self.metadata),
        }

# Backward-compatible alias
RuntimeConnection = Connection


@dataclass
class ActorProfile:
    """Persistent browser/service profile with encrypted storage."""
    id: str = field(default_factory=uuid7)
    actor_id: str = ""
    profile_type: str = ""               # browser_chrome | tailscale | cli_tool | ai_context
    account_identity: Optional[str] = None
    storage_backend: str = "google_drive"
    storage_path: str = ""
    storage_folder_id: Optional[str] = None
    encryption_method: str = "fernet"
    encryption_key_ref: Optional[str] = None
    persistence_mode: str = "periodic"    # periodic | on_milestone | on_terminate | once_per_account
    save_interval_seconds: Optional[int] = None
    last_saved_at: Optional[datetime] = None
    save_count: int = 0
    state: str = "fresh"
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: datetime = field(default_factory=utcnow)
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict] = None

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor_id": self.actor_id,
            "profile_type": self.profile_type,
            "account_identity": self.account_identity,
            "storage_backend": self.storage_backend,
            "storage_path": self.storage_path,
            "storage_folder_id": self.storage_folder_id,
            "encryption_method": self.encryption_method,
            "encryption_key_ref": self.encryption_key_ref,
            "persistence_mode": self.persistence_mode,
            "save_interval_seconds": self.save_interval_seconds,
            "last_saved_at": self.last_saved_at,
            "save_count": self.save_count, "state": self.state,
            "checksum": self.checksum, "size_bytes": self.size_bytes,
            "created_at": self.created_at, "expires_at": self.expires_at,
            "metadata": _to_json(self.metadata),
        }

# Backward-compatible alias
AgentProfile = ActorProfile


@dataclass
class Bundle:
    """Portable runtime bundle (capabilities + AI context + services + workflow)."""
    id: str = field(default_factory=uuid7)
    creator_id: str = ""
    environment_type: str = ""            # runtime_sandbox | workflow_bundle | tool_kit
    manifest: Optional[Dict] = None       # {services, capabilities, ai_context, workflow_vars}
    storage_backend: str = "google_drive"
    storage_path: str = ""
    bundle_checksum: Optional[str] = None
    bundle_size_bytes: Optional[int] = None
    is_portable: bool = False
    visibility: str = "private"           # private | shared | marketplace
    compatible_runtimes: Optional[List[str]] = None
    created_at: datetime = field(default_factory=utcnow)
    last_serialized_at: Optional[datetime] = None
    version: str = "1.0.0"
    state: str = "active"

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "creator_id": self.creator_id,
            "environment_type": self.environment_type,
            "manifest": _to_json(self.manifest),
            "storage_backend": self.storage_backend,
            "storage_path": self.storage_path,
            "bundle_checksum": self.bundle_checksum,
            "bundle_size_bytes": self.bundle_size_bytes,
            "is_portable": self.is_portable, "visibility": self.visibility,
            "compatible_runtimes": _to_json(self.compatible_runtimes),
            "created_at": self.created_at,
            "last_serialized_at": self.last_serialized_at,
            "version": self.version, "state": self.state,
        }

# Backward-compatible alias
AgentEnvironment = Bundle


@dataclass
class ActorVersion:
    """Git-like version snapshot with human-gated approval model."""
    id: str = field(default_factory=uuid7)
    actor_id: str = ""
    version_tag: str = ""                 # Semver: "1.0.0"
    version_hash: str = ""               # SHA-256 of serialized state
    parent_version_id: Optional[str] = None
    branch: str = "main"
    config_snapshot: Optional[Dict] = None
    runtime_state_snapshot: Optional[Dict] = None
    capability_grants_snapshot: Optional[List[str]] = None
    bundle_id: Optional[str] = None
    change_type: str = "patch"            # patch | minor | major | rollback | fork
    change_summary: Optional[str] = None
    diff_from_parent: Optional[Dict] = None
    authored_by: str = ""                 # → actors.id
    reviewed_by: Optional[str] = None
    operation_id: Optional[str] = None
    requires_human_approval: bool = False
    approval_status: Optional[str] = None # pending | approved | rejected | auto_approved
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    git_repo_url: Optional[str] = None
    git_commit_hash: Optional[str] = None
    git_branch: Optional[str] = None
    ci_pipeline_status: Optional[str] = None
    ci_pipeline_url: Optional[str] = None
    state: str = "active"
    is_current: bool = False
    created_at: datetime = field(default_factory=utcnow)

    def to_db_row(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor_id": self.actor_id,
            "version_tag": self.version_tag, "version_hash": self.version_hash,
            "parent_version_id": self.parent_version_id, "branch": self.branch,
            "config_snapshot": _to_json(self.config_snapshot),
            "runtime_state_snapshot": _to_json(self.runtime_state_snapshot),
            "capability_grants_snapshot": _to_json(self.capability_grants_snapshot),
            "bundle_id": self.bundle_id,
            "change_type": self.change_type,
            "change_summary": self.change_summary,
            "diff_from_parent": _to_json(self.diff_from_parent),
            "authored_by": self.authored_by, "reviewed_by": self.reviewed_by,
            "operation_id": self.operation_id,
            "requires_human_approval": self.requires_human_approval,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by, "approved_at": self.approved_at,
            "git_repo_url": self.git_repo_url,
            "git_commit_hash": self.git_commit_hash,
            "git_branch": self.git_branch,
            "ci_pipeline_status": self.ci_pipeline_status,
            "ci_pipeline_url": self.ci_pipeline_url,
            "state": self.state, "is_current": self.is_current,
            "created_at": self.created_at,
        }

# Backward-compatible alias
AgentVersion = ActorVersion
