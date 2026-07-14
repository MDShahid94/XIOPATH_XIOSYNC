"""
XIOPATH — API v2: Actors Router
===================================
CRUD endpoints for the Universal Actor Ontology.
All endpoints require authentication; write operations require admin role.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from api.routers.auth import get_current_user, require_admin, require_worker_or_admin
from core.ontology_models import (
    Actor, Operation, ActorEdge, Capability, CapabilityGrant, Event,
    Connection, ActorProfile, Bundle, ActorVersion,
    uuid7, utcnow, _to_json, _from_json,
)
from core.ontology_ops import OntologyManager

router = APIRouter(prefix="/actors", tags=["Actors v2"])
logger = logging.getLogger(__name__)


def _get_ontology(request: Request) -> OntologyManager:
    """Get the OntologyManager from app state."""
    if not hasattr(request.app.state, 'ontology'):
        from core.ontology_ops import OntologyManager
        db = request.app.state.db
        request.app.state.ontology = OntologyManager(db)
    return request.app.state.ontology


def _get_type_registry(request: Request):
    """Get the TypeRegistry from app state, with lazy init fallback."""
    registry = getattr(request.app.state, 'type_registry', None)
    if registry is None:
        from core.type_registry import TypeRegistry
        db = request.app.state.db
        registry = TypeRegistry(db)
        request.app.state.type_registry = registry
    return registry


# ─── Request/Response Models ─────────────────────────────────────────────────

class CreateActorRequest(BaseModel):
    actor_type: str = Field(..., description="human | ai | compute (extensible via type_registry)")
    actor_subtype: Optional[str] = None
    role: Optional[str] = None
    alias: Optional[str] = None
    parent_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateActorRequest(BaseModel):
    alias: Optional[str] = None
    role: Optional[str] = None
    state: Optional[str] = None
    lifecycle_phase: Optional[str] = None
    runtime_state: Optional[Dict[str, Any]] = None
    health_status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class RecordOperationRequest(BaseModel):
    operation: str = Field(..., description="proposition | design | implementation | initiation | ...")
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    trigger: Optional[str] = "user_command"
    collaborators: Optional[List[Dict[str, str]]] = None
    scope: Optional[str] = "agent"
    depth_level: int = 0
    parent_operation_id: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None
    outcome: Optional[str] = "pending"


class CreateEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    edge_type: str = Field(..., description="manages | delegates_to | collaborates_with | ...")
    config: Optional[Dict[str, Any]] = None
    weight: float = 1.0
    bidirectional: bool = False


class RegisterCapabilityRequest(BaseModel):
    name: str
    capability_type: str = Field(..., description="browser | api | plugin | llm | system (extensible via type_registry)")
    version: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    execution_mode: str = "sync"
    timeout_ms: int = 30000


class GrantCapabilityRequest(BaseModel):
    actor_id: str
    capability_id: str
    scope: str = "full"
    constraints: Optional[Dict[str, Any]] = None
    expires_at: Optional[str] = None


class ApproveVersionRequest(BaseModel):
    approval_status: str = Field(..., description="approved | rejected")


class CreateConnectionRequest(BaseModel):
    source_actor_id: str
    target_actor_id: str
    protocol: str
    transport: str
    source_endpoint: Optional[str] = None
    target_endpoint: Optional[str] = None
    routing_rule: Optional[str] = None
    proxy_config: Optional[Dict[str, Any]] = None


class CreateProfileRequest(BaseModel):
    actor_id: str
    profile_type: str
    account_identity: Optional[str] = None
    storage_backend: str = "google_drive"
    storage_path: str
    encryption_method: str = "fernet"
    encryption_key_ref: Optional[str] = None
    persistence_mode: str = "periodic"
    save_interval_seconds: Optional[int] = None


class CreateBundleRequest(BaseModel):
    actor_id: str
    environment_type: str
    manifest: Dict[str, Any]
    storage_backend: str = "google_drive"
    storage_path: str
    visibility: str = "private"
    compatible_runtimes: Optional[List[str]] = None


# ═════════════════════════════════════════════════════════════════════════════
# ACTOR CRUD
# ═════════════════════════════════════════════════════════════════════════════

@router.post("")
async def create_actor(
    req: CreateActorRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a new actor in the ontology. Platform-admin only."""
    ontology = _get_ontology(request)

    registry = _get_type_registry(request)
    if not registry.is_valid("actor_type", req.actor_type):
        valid = registry.get_types("actor_type")
        raise HTTPException(400, f"Invalid actor_type. Must be one of: {sorted(valid)}")

    actor = Actor(
        actor_type=req.actor_type,
        actor_subtype=req.actor_subtype,
        role=req.role,
        alias=req.alias,
        parent_id=req.parent_id,
        config=req.config,
        metadata=req.metadata,
        created_by=user.get("sub"),
    )
    actor_id = ontology.create_actor(actor)

    # Log the creation event
    ontology.log_event(Event(
        actor_id=actor_id,
        event_type="state_change",
        summary=f"Actor created: {req.alias or actor_id} ({req.actor_type}.{req.actor_subtype})",
        payload={"created_by": user.get("sub")},
    ))

    return {"status": "success", "id": actor_id, "alias": req.alias}


@router.get("")
async def list_actors(
    request: Request,
    actor_type: Optional[str] = None,
    state: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List all actors, optionally filtered by type and/or state."""
    ontology = _get_ontology(request)
    actors = ontology.list_actors(actor_type=actor_type, state=state)
    return {"actors": actors, "total": len(actors)}


# ── Static-path GETs MUST be declared before /{actor_id} to avoid being
#    swallowed by the catch-all dynamic route. ──

@router.get("/tools")
async def list_capabilities(
    request: Request,
    state: str = "active",
    user: dict = Depends(get_current_user),
):
    """List registered capabilities."""
    ontology = _get_ontology(request)
    capabilities = ontology.list_capabilities(state=state)
    return {"capabilities": capabilities, "total": len(capabilities)}


@router.get("/connections")
async def list_connections(
    request: Request,
    state: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List runtime connections."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    query = "SELECT * FROM connections WHERE 1=1"
    params = {}
    if state:
        query += " AND state = :state"
        params["state"] = state
    query += " ORDER BY created_at DESC"
    with ontology.db.SessionLocal() as session:
        rows = session.execute(text(query), params).fetchall()
        connections = [dict(r._mapping) for r in rows]
    return {"connections": connections, "total": len(connections)}


@router.get("/{actor_id}")
async def get_actor(
    actor_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get a single actor with full state."""
    ontology = _get_ontology(request)
    actor = ontology.get_actor(actor_id)
    if not actor:
        raise HTTPException(404, "Actor not found")

    # Enrich with edges and recent operations
    edges = ontology.get_edges(actor_id, "both")
    ops = ontology.get_operations(actor_id, limit=10)
    capabilities = ontology.get_actor_capabilities(actor_id)

    return {
        "actor": actor,
        "edges": edges,
        "recent_operations": ops,
        "capabilities": capabilities,
    }


@router.patch("/{actor_id}")
async def update_actor(
    actor_id: str,
    req: UpdateActorRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Update an actor's mutable fields (runtime_args, state, etc.)."""
    ontology = _get_ontology(request)

    existing = ontology.get_actor(actor_id)
    if not existing:
        raise HTTPException(404, "Actor not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    if "state" in updates:
        registry = _get_type_registry(request)
        if not registry.is_valid("lifecycle_state", updates["state"]):
            valid = registry.get_types("lifecycle_state")
            raise HTTPException(400, f"Invalid state. Must be one of: {sorted(valid)}")

    success = ontology.update_actor(actor_id, **updates)
    if not success:
        raise HTTPException(500, "Failed to update actor")

    return {"status": "success", "updated_fields": list(updates.keys())}


# ═════════════════════════════════════════════════════════════════════════════
# OPERATIONS
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/{actor_id}/operations")
async def record_operation(
    actor_id: str,
    req: RecordOperationRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Record a lifecycle operation on an actor."""
    ontology = _get_ontology(request)

    existing = ontology.get_actor(actor_id)
    if not existing:
        raise HTTPException(404, "Actor not found")

    registry = _get_type_registry(request)
    if not registry.is_valid("operation_type", req.operation):
        valid = registry.get_types("operation_type")
        raise HTTPException(400, f"Invalid operation. Must be one of: {sorted(valid)}")

    op = Operation(
        actor_id=actor_id,
        operation=req.operation,
        from_state=req.from_state or existing.get("state"),
        to_state=req.to_state,
        trigger=req.trigger,
        initiated_by=user.get("sub"),
        collaborators=req.collaborators,
        scope=req.scope,
        depth_level=req.depth_level,
        parent_operation_id=req.parent_operation_id,
        artifacts=req.artifacts,
        rationale=req.rationale,
        outcome=req.outcome,
    )
    op_id = ontology.record_operation(op)

    return {"status": "success", "operation_id": op_id}


@router.get("/{actor_id}/operations")
async def get_operations(
    actor_id: str,
    request: Request,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """Get operation history for an actor."""
    ontology = _get_ontology(request)
    ops = ontology.get_operations(actor_id, limit=limit)
    return {"operations": ops, "total": len(ops)}


# ═════════════════════════════════════════════════════════════════════════════
# EDGES
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/edges")
async def create_edge(
    req: CreateEdgeRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Create a typed relationship between two actors."""
    ontology = _get_ontology(request)

    registry = _get_type_registry(request)
    if not registry.is_valid("edge_type", req.edge_type):
        valid = registry.get_types("edge_type")
        raise HTTPException(400, f"Invalid edge_type. Must be one of: {sorted(valid)}")

    # Verify both agents exist
    for aid in (req.source_id, req.target_id):
        if not ontology.get_actor(aid):
            raise HTTPException(404, f"Actor not found: {aid}")

    edge = ActorEdge(
        source_id=req.source_id,
        target_id=req.target_id,
        edge_type=req.edge_type,
        config=req.config,
        weight=req.weight,
        bidirectional=req.bidirectional,
    )
    edge_id = ontology.create_edge(edge)

    return {"status": "success", "edge_id": edge_id}


@router.get("/{actor_id}/edges")
async def get_edges(
    actor_id: str,
    request: Request,
    direction: str = "both",
    user: dict = Depends(get_current_user),
):
    """Get edges for an actor. direction: outgoing, incoming, or both."""
    ontology = _get_ontology(request)
    edges = ontology.get_edges(actor_id, direction=direction)
    return {"edges": edges, "total": len(edges)}


# ═════════════════════════════════════════════════════════════════════════════
# CAPABILITIES
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/tools")
async def register_capability(
    req: RegisterCapabilityRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a new capability in the registry."""
    ontology = _get_ontology(request)
    capability = Capability(
        name=req.name,
        capability_type=req.capability_type,
        version=req.version,
        description=req.description,
        input_schema=req.input_schema,
        output_schema=req.output_schema,
        config=req.config,
        execution_mode=req.execution_mode,
        timeout_ms=req.timeout_ms,
    )
    capability_id = ontology.register_capability(capability)
    return {"status": "success", "capability_id": capability_id}


# NOTE: GET /tools moved before /{actor_id} to avoid route conflict


@router.post("/capabilities")
async def grant_capability(
    req: GrantCapabilityRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Grant a capability to an actor."""
    ontology = _get_ontology(request)
    grant = CapabilityGrant(
        actor_id=req.actor_id,
        capability_id=req.capability_id,
        granted_by=user.get("sub"),
        scope=req.scope,
        constraints=req.constraints,
    )
    grant_id = ontology.grant_capability(grant)
    return {"status": "success", "grant_id": grant_id}


@router.get("/{actor_id}/capabilities")
async def get_capabilities(
    actor_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get all capabilities granted to an actor."""
    ontology = _get_ontology(request)
    caps = ontology.get_actor_capabilities(actor_id)
    return {"capabilities": caps, "total": len(caps)}


# ═════════════════════════════════════════════════════════════════════════════
# VERSIONS
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/{actor_id}/versions")
async def get_versions(
    actor_id: str,
    request: Request,
    branch: str = "main",
    user: dict = Depends(get_current_user),
):
    """Get version history for an actor."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    with ontology.db.SessionLocal() as session:
        rows = session.execute(
            text("""SELECT * FROM actor_versions
                    WHERE actor_id = :id AND branch = :branch
                    ORDER BY created_at DESC"""),
            {"id": actor_id, "branch": branch}
        ).fetchall()
        versions = [dict(r._mapping) for r in rows]
    return {"versions": versions, "total": len(versions)}


@router.post("/{actor_id}/versions/{version_id}/approve")
async def approve_version(
    actor_id: str,
    version_id: str,
    req: ApproveVersionRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Approve or reject a pending actor version (human-gated authority)."""
    ontology = _get_ontology(request)
    from sqlalchemy import text

    with ontology.db.safe_transaction() as session:
        row = session.execute(
            text("SELECT * FROM actor_versions WHERE id = :id AND actor_id = :aid"),
            {"id": version_id, "aid": actor_id}
        ).fetchone()

        if not row:
            raise HTTPException(404, "Version not found")

        version = dict(row._mapping)
        if version.get("approval_status") not in (None, "pending"):
            raise HTTPException(400, f"Version already {version['approval_status']}")

        now = utcnow()
        session.execute(
            text("""UPDATE actor_versions
                    SET approval_status = :status, approved_by = :by, approved_at = :at
                    WHERE id = :id"""),
            {
                "status": req.approval_status,
                "by": user.get("sub"),
                "at": now,
                "id": version_id,
            }
        )

        # If approved, mark as current and supersede old current
        if req.approval_status == "approved":
            session.execute(
                text("""UPDATE actor_versions
                        SET is_current = 0
                        WHERE actor_id = :aid AND branch = :branch AND is_current = 1"""),
                {"aid": actor_id, "branch": version.get("branch", "main")}
            )
            session.execute(
                text("UPDATE actor_versions SET is_current = 1 WHERE id = :id"),
                {"id": version_id}
            )


    ontology.log_event(Event(
        actor_id=actor_id,
        event_type="state_change",
        summary=f"Version {version.get('version_tag')} {req.approval_status} by {user.get('sub')}",
        payload={"version_id": version_id, "status": req.approval_status},
    ))

    return {"status": "success", "approval_status": req.approval_status}


@router.post("/{actor_id}/rollback")
async def rollback_version(
    actor_id: str,
    request: Request,
    target_version_id: Optional[str] = None,
    user: dict = Depends(require_admin),
):
    """Rollback an actor to a previous version."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    import hashlib

    with ontology.db.safe_transaction() as session:
        # Find target version (specified or previous)
        if target_version_id:
            row = session.execute(
                text("SELECT * FROM actor_versions WHERE id = :id AND actor_id = :aid"),
                {"id": target_version_id, "aid": actor_id}
            ).fetchone()
        else:
            # Get the second most recent approved version
            row = session.execute(
                text("""SELECT * FROM actor_versions
                        WHERE actor_id = :aid AND approval_status = 'approved'
                        ORDER BY created_at DESC LIMIT 1 OFFSET 1"""),
                {"aid": actor_id}
            ).fetchone()

        if not row:
            raise HTTPException(404, "No version to rollback to")

        target = dict(row._mapping)

        # Apply the config snapshot
        config_snapshot = target.get("config_snapshot")
        if config_snapshot:
            ontology.update_actor(actor_id, config=_from_json(config_snapshot))

        # Create a rollback version entry
        rollback_hash = hashlib.sha256(
            _to_json({"rollback_to": target["id"]}).encode()
        ).hexdigest()

        rollback_version = ActorVersion(
            actor_id=actor_id,
            version_tag=f"rollback-to-{target.get('version_tag', 'unknown')}",
            version_hash=rollback_hash,
            parent_version_id=target["id"],
            branch=target.get("branch", "main"),
            config_snapshot=_from_json(config_snapshot) if config_snapshot else {},
            change_type="rollback",
            change_summary=f"Rolled back to version {target.get('version_tag')}",
            authored_by=user.get("sub"),
            approval_status="auto_approved",
            is_current=True,
        )
        rv_row = rollback_version.to_db_row()
        cols = ", ".join(rv_row.keys())
        placeholders = ", ".join(f":{k}" for k in rv_row.keys())
        session.execute(text(f"INSERT INTO actor_versions ({cols}) VALUES ({placeholders})"), rv_row)

        # Unset previous current
        session.execute(
            text("""UPDATE actor_versions SET is_current = 0
                    WHERE actor_id = :aid AND id != :new_id"""),
            {"aid": actor_id, "new_id": rollback_version.id}
        )

    # Record the rollback operation
    ontology.record_operation(Operation(
        actor_id=actor_id,
        operation="rollback",
        trigger="user_command",
        initiated_by=user.get("sub"),
        rationale=f"Rolled back to version {target.get('version_tag')}",
        outcome="success",
    ))

    return {
        "status": "success",
        "rolled_back_to": target.get("version_tag"),
        "new_version_id": rollback_version.id,
    }


# ═════════════════════════════════════════════════════════════════════════════
# CONNECTIONS
# ═════════════════════════════════════════════════════════════════════════════

# NOTE: GET /connections moved before /{actor_id} to avoid route conflict


@router.post("/connections")
async def create_connection(
    req: CreateConnectionRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a new runtime connection."""
    ontology = _get_ontology(request)
    conn = Connection(
        source_actor_id=req.source_actor_id,
        target_actor_id=req.target_actor_id,
        protocol=req.protocol,
        transport=req.transport,
        source_endpoint=req.source_endpoint,
        target_endpoint=req.target_endpoint,
        routing_rule=req.routing_rule,
        proxy_config=req.proxy_config,
    )
    row = conn.to_db_row()
    from sqlalchemy import text
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with ontology.db.safe_transaction() as session:
        session.execute(text(f"INSERT INTO connections ({cols}) VALUES ({placeholders})"), row)

    return {"status": "success", "connection_id": conn.id}


# ═════════════════════════════════════════════════════════════════════════════
# PROFILES
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/profiles")
async def create_profile(
    req: CreateProfileRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register an actor profile (browser, tailscale, etc.)."""
    ontology = _get_ontology(request)
    profile = ActorProfile(
        actor_id=req.actor_id,
        profile_type=req.profile_type,
        account_identity=req.account_identity,
        storage_backend=req.storage_backend,
        storage_path=req.storage_path,
        encryption_method=req.encryption_method,
        encryption_key_ref=req.encryption_key_ref,
        persistence_mode=req.persistence_mode,
        save_interval_seconds=req.save_interval_seconds,
    )
    row = profile.to_db_row()
    from sqlalchemy import text
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with ontology.db.safe_transaction() as session:
        session.execute(text(f"INSERT INTO actor_profiles ({cols}) VALUES ({placeholders})"), row)

    return {"status": "success", "profile_id": profile.id}


@router.get("/{actor_id}/profiles")
async def get_profiles(
    actor_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get all profiles for an actor."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    with ontology.db.SessionLocal() as session:
        rows = session.execute(
            text("SELECT * FROM actor_profiles WHERE actor_id = :id ORDER BY created_at DESC"),
            {"id": actor_id}
        ).fetchall()
        profiles = [dict(r._mapping) for r in rows]
    return {"profiles": profiles, "total": len(profiles)}


# ═════════════════════════════════════════════════════════════════════════════
# ENVIRONMENTS
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/environments")
async def create_environment(
    req: CreateBundleRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a portable bundle."""
    ontology = _get_ontology(request)
    bundle = Bundle(
        actor_id=req.actor_id,
        environment_type=req.environment_type,
        manifest=req.manifest,
        storage_backend=req.storage_backend,
        storage_path=req.storage_path,
        visibility=req.visibility,
        compatible_runtimes=req.compatible_runtimes,
    )
    row = bundle.to_db_row()
    from sqlalchemy import text
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with ontology.db.safe_transaction() as session:
        session.execute(text(f"INSERT INTO bundles ({cols}) VALUES ({placeholders})"), row)

    return {"status": "success", "bundle_id": bundle.id}


# ═════════════════════════════════════════════════════════════════════════════
# EVENTS (read-only)
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/{actor_id}/events")
async def get_events(
    actor_id: str,
    request: Request,
    event_type: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Get telemetry/audit events for an actor."""
    ontology = _get_ontology(request)
    events = ontology.get_events(actor_id=actor_id, event_type=event_type, limit=limit)
    return {"events": events, "total": len(events)}
