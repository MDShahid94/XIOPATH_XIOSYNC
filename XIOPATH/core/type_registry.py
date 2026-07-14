"""
XIOPATH — Type Registry (Phase 2)
=====================================
Database-backed type system replacing hardcoded constants.

The TypeRegistry manages all type categories in the ontology:
  - actor_type, actor_subtype
  - edge_type, operation_type
  - lifecycle_state, lifecycle_phase
  - event_type, severity
  - capability_type, action_type

Features:
  - In-memory LRU cache with TTL for hot-path validation
  - Runtime extensibility: creators register custom types via API
  - JSON Schema validation for action_type specs
  - Org-scoped types (Phase 4 prep)
  - Builtin vs. user-created distinction

Usage:
    registry = TypeRegistry(db)
    registry.seed_builtins()

    registry.is_valid("actor_type", "human")            # True
    registry.is_valid("actor_type", "alien")             # False
    registry.get_types("edge_type")                      # ["manages", "delegates_to", ...]
    registry.validate_action_spec("browser", {...})      # raises ValueError on invalid
"""
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set

from sqlalchemy import text

logger = logging.getLogger("TypeRegistry")


# ─── Action Type JSON Schemas ────────────────────────────────────────────────
# Strict schemas for the `action_spec` field in knowledge_nodes (Phase 5).
# Each action_type has a required schema that its spec must conform to.

ACTION_TYPE_SCHEMAS = {
    "browser": {
        "type": "object",
        "required": ["steps"],
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["action"],
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["click", "type", "navigate", "scroll", "wait",
                                     "select", "hover", "screenshot", "extract", "assert"]
                        },
                        "selector": {"type": "string"},
                        "value": {},
                        "timeout_ms": {"type": "integer", "minimum": 0},
                        "description": {"type": "string"},
                    }
                },
                "minItems": 1,
            },
            "url": {"type": "string", "format": "uri"},
            "preconditions": {"type": "array", "items": {"type": "string"}},
            "postconditions": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
    "api_call": {
        "type": "object",
        "required": ["method", "url"],
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]},
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "body": {},
            "query_params": {"type": "object"},
            "auth_type": {"type": "string", "enum": ["none", "bearer", "api_key", "oauth2", "basic"]},
            "timeout_ms": {"type": "integer", "minimum": 0},
            "retry_policy": {
                "type": "object",
                "properties": {
                    "max_retries": {"type": "integer"},
                    "backoff_ms": {"type": "integer"},
                }
            },
            "expected_status": {"type": "array", "items": {"type": "integer"}},
        },
        "additionalProperties": False,
    },
    "script": {
        "type": "object",
        "required": ["language", "source"],
        "properties": {
            "language": {"type": "string", "enum": ["python", "javascript", "bash", "sql"]},
            "source": {"type": "string", "minLength": 1},
            "args": {"type": "object"},
            "env": {"type": "object"},
            "timeout_ms": {"type": "integer", "minimum": 0},
            "sandbox": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    "llm_prompt": {
        "type": "object",
        "required": ["model", "prompt"],
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string", "minLength": 1},
            "system_prompt": {"type": "string"},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "max_tokens": {"type": "integer", "minimum": 1},
            "stop_sequences": {"type": "array", "items": {"type": "string"}},
            "tools": {"type": "array"},
            "response_format": {"type": "string", "enum": ["text", "json", "structured"]},
        },
        "additionalProperties": False,
    },
    "composite": {
        "type": "object",
        "required": ["steps"],
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["action_type", "action_spec"],
                    "properties": {
                        "action_type": {"type": "string"},
                        "action_spec": {"type": "object"},
                        "condition": {"type": "string"},
                        "on_failure": {"type": "string", "enum": ["abort", "skip", "retry"]},
                    }
                },
                "minItems": 1,
            },
            "execution_mode": {"type": "string", "enum": ["sequential", "parallel", "conditional"]},
            "max_retries": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    },
}


# ─── Builtin Type Definitions ────────────────────────────────────────────────
# These are seeded on first boot and marked is_builtin=True.
# They can never be deleted, only deprecated.

BUILTIN_TYPES: List[Dict[str, Any]] = [
    # ── actor_type ──
    {"category": "actor_type", "name": "human",   "display_name": "Human",   "description": "Human user or administrator"},
    {"category": "actor_type", "name": "ai",      "display_name": "AI",      "description": "AI model or inference engine"},
    {"category": "actor_type", "name": "compute", "display_name": "Compute", "description": "Runtime, server, or compute node"},

    # ── actor_subtype ──
    {"category": "actor_subtype", "name": "admin",            "parent_name": "human",   "display_name": "Admin"},
    {"category": "actor_subtype", "name": "member",           "parent_name": "human",   "display_name": "Member"},
    {"category": "actor_subtype", "name": "creator",          "parent_name": "human",   "display_name": "Creator"},
    {"category": "actor_subtype", "name": "llm_engine",       "parent_name": "ai",      "display_name": "LLM Engine"},
    {"category": "actor_subtype", "name": "embedding_engine", "parent_name": "ai",      "display_name": "Embedding Engine"},
    {"category": "actor_subtype", "name": "api_server",       "parent_name": "compute", "display_name": "API Server"},
    {"category": "actor_subtype", "name": "worker_node",      "parent_name": "compute", "display_name": "Worker Node"},
    {"category": "actor_subtype", "name": "colab_runtime",    "parent_name": "compute", "display_name": "Colab Runtime"},

    # ── lifecycle_state ──
    {"category": "lifecycle_state", "name": "proposed",     "display_name": "Proposed",     "description": "Initial proposal stage"},
    {"category": "lifecycle_state", "name": "designing",    "display_name": "Designing",    "description": "Under design"},
    {"category": "lifecycle_state", "name": "implementing", "display_name": "Implementing", "description": "Being implemented"},
    {"category": "lifecycle_state", "name": "validating",   "display_name": "Validating",   "description": "Under validation"},
    {"category": "lifecycle_state", "name": "initializing", "display_name": "Initializing", "description": "Starting up"},
    {"category": "lifecycle_state", "name": "active",       "display_name": "Active",       "description": "Fully operational"},
    {"category": "lifecycle_state", "name": "updating",     "display_name": "Updating",     "description": "Being updated"},
    {"category": "lifecycle_state", "name": "suspended",    "display_name": "Suspended",    "description": "Temporarily paused"},
    {"category": "lifecycle_state", "name": "migrating",    "display_name": "Migrating",    "description": "Being migrated"},
    {"category": "lifecycle_state", "name": "terminating",  "display_name": "Terminating",  "description": "Shutting down"},
    {"category": "lifecycle_state", "name": "terminated",   "display_name": "Terminated",   "description": "Shut down"},
    {"category": "lifecycle_state", "name": "archived",     "display_name": "Archived",     "description": "Preserved for history"},

    # ── lifecycle_phase ──
    {"category": "lifecycle_phase", "name": "pre_birth",    "display_name": "Pre-Birth"},
    {"category": "lifecycle_phase", "name": "birth",        "display_name": "Birth"},
    {"category": "lifecycle_phase", "name": "operational",  "display_name": "Operational"},
    {"category": "lifecycle_phase", "name": "end_of_life",  "display_name": "End of Life"},

    # ── operation_type ──
    {"category": "operation_type", "name": "proposition",     "display_name": "Proposition"},
    {"category": "operation_type", "name": "design",          "display_name": "Design"},
    {"category": "operation_type", "name": "implementation",  "display_name": "Implementation"},
    {"category": "operation_type", "name": "validation",      "display_name": "Validation"},
    {"category": "operation_type", "name": "initiation",      "display_name": "Initiation"},
    {"category": "operation_type", "name": "updation",        "display_name": "Updation"},
    {"category": "operation_type", "name": "suspension",      "display_name": "Suspension"},
    {"category": "operation_type", "name": "migration",       "display_name": "Migration"},
    {"category": "operation_type", "name": "termination",     "display_name": "Termination"},
    {"category": "operation_type", "name": "archival",        "display_name": "Archival"},
    {"category": "operation_type", "name": "rollback",        "display_name": "Rollback"},

    # ── edge_type ──
    {"category": "edge_type", "name": "manages",           "display_name": "Manages"},
    {"category": "edge_type", "name": "delegates_to",      "display_name": "Delegates To"},
    {"category": "edge_type", "name": "collaborates_with", "display_name": "Collaborates With"},
    {"category": "edge_type", "name": "provides",          "display_name": "Provides"},
    {"category": "edge_type", "name": "owns",              "display_name": "Owns"},

    # ── event_type ──
    {"category": "event_type", "name": "action_executed", "display_name": "Action Executed"},
    {"category": "event_type", "name": "error",           "display_name": "Error"},
    {"category": "event_type", "name": "state_change",    "display_name": "State Change"},
    {"category": "event_type", "name": "heartbeat",       "display_name": "Heartbeat"},
    {"category": "event_type", "name": "tool_invoked",    "display_name": "Tool Invoked"},
    {"category": "event_type", "name": "auth_event",      "display_name": "Auth Event"},
    {"category": "event_type", "name": "metric",          "display_name": "Metric"},

    # ── severity ──
    {"category": "severity", "name": "debug",    "display_name": "Debug"},
    {"category": "severity", "name": "info",     "display_name": "Info"},
    {"category": "severity", "name": "warn",     "display_name": "Warning"},
    {"category": "severity", "name": "error",    "display_name": "Error"},
    {"category": "severity", "name": "critical", "display_name": "Critical"},

    # ── capability_type ──
    {"category": "capability_type", "name": "browser", "display_name": "Browser Automation"},
    {"category": "capability_type", "name": "api",     "display_name": "API Integration"},
    {"category": "capability_type", "name": "plugin",  "display_name": "Plugin"},
    {"category": "capability_type", "name": "llm",     "display_name": "LLM Inference"},
    {"category": "capability_type", "name": "system",  "display_name": "System Utility"},

    # ── action_type (with JSON schemas) ──
    {"category": "action_type", "name": "browser",    "display_name": "Browser Action",    "description": "Automated browser interaction steps",     "schema": ACTION_TYPE_SCHEMAS["browser"]},
    {"category": "action_type", "name": "api_call",   "display_name": "API Call",          "description": "HTTP API request",                        "schema": ACTION_TYPE_SCHEMAS["api_call"]},
    {"category": "action_type", "name": "script",     "display_name": "Script Execution",  "description": "Run a script in a sandboxed environment", "schema": ACTION_TYPE_SCHEMAS["script"]},
    {"category": "action_type", "name": "llm_prompt", "display_name": "LLM Prompt",        "description": "Send a prompt to an LLM model",           "schema": ACTION_TYPE_SCHEMAS["llm_prompt"]},
    {"category": "action_type", "name": "composite",  "display_name": "Composite Action",  "description": "Multi-step workflow combining actions",    "schema": ACTION_TYPE_SCHEMAS["composite"]},
]


def _uuid7() -> str:
    """Generate a UUIDv7 (time-ordered) string."""
    import uuid
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TypeRegistry:
    """
    Database-backed type system with in-memory cache.

    The cache is a dict of {category: {name: row_dict}} that is lazily loaded
    on first access and invalidated on any write operation.

    Thread-safe via a reentrant lock.
    """

    def __init__(self, db):
        self.db = db
        self._cache: Dict[str, Dict[str, dict]] = {}
        self._cache_loaded = False
        self._lock = threading.RLock()

    # ═══════════════════════════════════════════════════════════════════════
    # CACHE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def _ensure_cache(self) -> None:
        """Load the full type_registry into memory if not yet cached."""
        if self._cache_loaded:
            return
        with self._lock:
            if self._cache_loaded:
                return
            try:
                with self.db.SessionLocal() as session:
                    rows = session.execute(
                        text("SELECT * FROM type_registry WHERE state = 'active' ORDER BY sort_order, name")
                    ).mappings().all()
                    self._cache.clear()
                    for row in rows:
                        cat = row["category"]
                        name = row["name"]
                        if cat not in self._cache:
                            self._cache[cat] = {}
                        self._cache[cat][name] = dict(row)
                    self._cache_loaded = True
                    logger.debug(f"TypeRegistry cache loaded: {sum(len(v) for v in self._cache.values())} types across {len(self._cache)} categories")
            except Exception as e:
                logger.warning(f"TypeRegistry cache load failed (table may not exist): {e}")
                # Fall back to hardcoded constants
                self._cache_loaded = False

    def invalidate_cache(self) -> None:
        """Force cache reload on next access."""
        with self._lock:
            self._cache.clear()
            self._cache_loaded = False

    # ═══════════════════════════════════════════════════════════════════════
    # VALIDATION
    # ═══════════════════════════════════════════════════════════════════════

    def is_valid(self, category: str, name: str, org_id: Optional[str] = None) -> bool:
        """
        Check if a type name is valid within a category.

        Falls back to hardcoded constants if the cache isn't available.
        """
        self._ensure_cache()
        if self._cache_loaded:
            cat_cache = self._cache.get(category, {})
            entry = cat_cache.get(name)
            if entry is None:
                return False
            # If org-scoped, check org_id matches (or entry is global)
            if org_id and entry.get("org_id") and entry["org_id"] != org_id:
                return False
            return True
        # Fallback to hardcoded constants
        return self._fallback_is_valid(category, name)

    def is_valid_subtype(self, parent_type: str, subtype: str) -> bool:
        """Check if a subtype is valid for a given parent type."""
        self._ensure_cache()
        if self._cache_loaded:
            subtypes = self._cache.get("actor_subtype", {})
            entry = subtypes.get(subtype)
            if entry is None:
                return False
            return entry.get("parent_name") == parent_type
        # Fallback
        from core.ontology_models import ACTOR_SUBTYPES
        return subtype in ACTOR_SUBTYPES.get(parent_type, set())

    def get_types(self, category: str, org_id: Optional[str] = None) -> List[str]:
        """Get all valid type names for a category."""
        self._ensure_cache()
        if self._cache_loaded:
            cat_cache = self._cache.get(category, {})
            if org_id:
                return [name for name, entry in cat_cache.items()
                        if not entry.get("org_id") or entry["org_id"] == org_id]
            return list(cat_cache.keys())
        return self._fallback_get_types(category)

    def get_type_details(self, category: str, name: str) -> Optional[dict]:
        """Get full details for a specific type."""
        self._ensure_cache()
        if self._cache_loaded:
            return self._cache.get(category, {}).get(name)
        return None

    def get_schema(self, category: str, name: str) -> Optional[dict]:
        """Get the JSON Schema for a type (mainly for action_type)."""
        details = self.get_type_details(category, name)
        if details and details.get("schema"):
            schema_val = details["schema"]
            if isinstance(schema_val, str):
                return json.loads(schema_val)
            return schema_val
        return None

    def validate_action_spec(self, action_type: str, spec: dict) -> None:
        """
        Validate an action_spec against its registered JSON Schema.

        Raises ValueError if invalid.
        Uses jsonschema if available, otherwise does structural validation.
        """
        schema = self.get_schema("action_type", action_type)
        if schema is None:
            if not self.is_valid("action_type", action_type):
                raise ValueError(f"Unknown action_type: '{action_type}'. Valid types: {self.get_types('action_type')}")
            return  # No schema defined, pass

        try:
            import jsonschema
            jsonschema.validate(instance=spec, schema=schema)
        except ImportError:
            # Fallback: basic structural validation
            self._basic_schema_validate(schema, spec)
        except Exception as e:
            raise ValueError(f"action_spec validation failed for '{action_type}': {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # REGISTRATION
    # ═══════════════════════════════════════════════════════════════════════

    def register_type(
        self,
        category: str,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        parent_name: Optional[str] = None,
        schema: Optional[dict] = None,
        org_id: Optional[str] = None,
        created_by: Optional[str] = None,
        sort_order: int = 100,
        metadata: Optional[dict] = None,
    ) -> str:
        """Register a new type. Returns the type ID."""
        type_id = _uuid7()
        now = _utcnow()

        row = {
            "id": type_id,
            "category": category,
            "name": name,
            "parent_name": parent_name,
            "display_name": display_name or name.replace("_", " ").title(),
            "description": description,
            "schema": json.dumps(schema) if schema else None,
            "is_builtin": False,
            "org_id": org_id,
            "state": "active",
            "sort_order": sort_order,
            "created_at": now,
            "created_by": created_by,
            "metadata": json.dumps(metadata) if metadata else None,
        }

        with self.db.safe_transaction() as session:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            session.execute(
                text(f"INSERT INTO type_registry ({cols}) VALUES ({placeholders})"),
                row,
            )

        self.invalidate_cache()
        logger.info(f"Registered type: {category}/{name} (id={type_id})")
        return type_id

    def deprecate_type(self, category: str, name: str) -> bool:
        """Mark a type as deprecated. Builtin types can be deprecated but not deleted."""
        with self.db.safe_transaction() as session:
            result = session.execute(
                text("UPDATE type_registry SET state = 'deprecated' WHERE category = :cat AND name = :name"),
                {"cat": category, "name": name},
            )
            if result.rowcount == 0:
                return False

        self.invalidate_cache()
        logger.info(f"Deprecated type: {category}/{name}")
        return True

    def delete_type(self, category: str, name: str) -> bool:
        """Delete a user-created type. Builtin types cannot be deleted."""
        with self.db.safe_transaction() as session:
            result = session.execute(
                text("DELETE FROM type_registry WHERE category = :cat AND name = :name AND is_builtin = 0"),
                {"cat": category, "name": name},
            )
            if result.rowcount == 0:
                return False

        self.invalidate_cache()
        logger.info(f"Deleted type: {category}/{name}")
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # SEED
    # ═══════════════════════════════════════════════════════════════════════

    def seed_builtins(self) -> Dict[str, int]:
        """
        Seed all builtin types. Idempotent — skips types that already exist.
        Returns counts per category.
        """
        counts: Dict[str, int] = {}
        now = _utcnow()

        with self.db.safe_transaction() as session:
            for type_def in BUILTIN_TYPES:
                cat = type_def["category"]
                name = type_def["name"]

                # Check if already exists
                existing = session.execute(
                    text("SELECT id FROM type_registry WHERE category = :cat AND name = :name AND (org_id IS NULL)"),
                    {"cat": cat, "name": name},
                ).fetchone()

                if existing:
                    continue

                row = {
                    "id": _uuid7(),
                    "category": cat,
                    "name": name,
                    "parent_name": type_def.get("parent_name"),
                    "display_name": type_def.get("display_name", name.replace("_", " ").title()),
                    "description": type_def.get("description"),
                    "schema": json.dumps(type_def["schema"]) if type_def.get("schema") else None,
                    "is_builtin": True,
                    "org_id": None,
                    "state": "active",
                    "sort_order": type_def.get("sort_order", 0),
                    "created_at": now,
                    "created_by": "system",
                    "metadata": None,
                }

                cols = ", ".join(row.keys())
                placeholders = ", ".join(f":{k}" for k in row.keys())
                session.execute(
                    text(f"INSERT INTO type_registry ({cols}) VALUES ({placeholders})"),
                    row,
                )
                counts[cat] = counts.get(cat, 0) + 1

        self.invalidate_cache()
        total = sum(counts.values())
        if total > 0:
            logger.info(f"TypeRegistry seeded: {total} builtin types ({counts})")
        else:
            logger.debug("TypeRegistry: all builtins already exist")
        return counts

    # ═══════════════════════════════════════════════════════════════════════
    # FALLBACK (when type_registry table doesn't exist yet)
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _fallback_is_valid(category: str, name: str) -> bool:
        from core.ontology_models import (
            ACTOR_TYPES, ACTOR_SUBTYPES, LIFECYCLE_STATES, LIFECYCLE_PHASES,
            OPERATION_TYPES, EDGE_TYPES, EVENT_TYPES, SEVERITY_LEVELS,
        )
        fallback_map = {
            "actor_type": ACTOR_TYPES,
            "lifecycle_state": LIFECYCLE_STATES,
            "lifecycle_phase": LIFECYCLE_PHASES,
            "operation_type": OPERATION_TYPES,
            "edge_type": EDGE_TYPES,
            "event_type": EVENT_TYPES,
            "severity": SEVERITY_LEVELS,
        }
        if category == "actor_subtype":
            for subtypes in ACTOR_SUBTYPES.values():
                if name in subtypes:
                    return True
            return False
        types = fallback_map.get(category)
        if types:
            return name in types
        return True  # Unknown category — permissive fallback

    @staticmethod
    def _fallback_get_types(category: str) -> List[str]:
        from core.ontology_models import (
            ACTOR_TYPES, ACTOR_SUBTYPES, LIFECYCLE_STATES,
            OPERATION_TYPES, EDGE_TYPES, EVENT_TYPES, SEVERITY_LEVELS,
        )
        fallback_map = {
            "actor_type": ACTOR_TYPES,
            "lifecycle_state": LIFECYCLE_STATES,
            "operation_type": OPERATION_TYPES,
            "edge_type": EDGE_TYPES,
            "event_type": EVENT_TYPES,
            "severity": SEVERITY_LEVELS,
        }
        if category == "actor_subtype":
            all_subs = set()
            for subs in ACTOR_SUBTYPES.values():
                all_subs.update(subs)
            return sorted(all_subs)
        types = fallback_map.get(category)
        return sorted(types) if types else []

    @staticmethod
    def _basic_schema_validate(schema: dict, instance: dict) -> None:
        """Minimal structural validation when jsonschema is not installed."""
        required = schema.get("required", [])
        for field in required:
            if field not in instance:
                raise ValueError(f"Missing required field: '{field}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance.keys()) - set(props.keys())
            if extra:
                raise ValueError(f"Unexpected fields: {extra}")
