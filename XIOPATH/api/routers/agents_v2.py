"""
XIOPATH — API v2: Agents Router
===================================
CRUD endpoints for the Universal Agent Ontology.
All endpoints require authentication; write operations require admin role.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from api.routers.auth import get_current_user, require_admin, require_worker_or_admin
from core.ontology_models import (
    Agent, AgentOperation, AgentEdge, Tool, CapabilityGrant, Event,
    RuntimeConnection, AgentProfile, AgentEnvironment, AgentVersion,
    uuid7, utcnow, _to_json, _from_json,
    LIFECYCLE_STATES, AGENT_TYPES, OPERATION_TYPES, EDGE_TYPES,
)
from core.ontology_ops import OntologyManager

router = APIRouter(prefix="/agents", tags=["Agents v2"])
logger = logging.getLogger(__name__)


def _get_ontology(request: Request) -> OntologyManager:
    """Get the OntologyManager from app state."""
    if not hasattr(request.app.state, 'ontology'):
        from core.ontology_ops import OntologyManager
        request.app.state.ontology = OntologyManager(request.app.state.db)
    return request.app.state.ontology


# ─── Request/Response Models ─────────────────────────────────────────────────

class CreateAgentRequest(BaseModel):
    agent_type: str = Field(..., description="human | ai | compute | tool | workflow | ecosystem")
    agent_subtype: Optional[str] = None
    role: Optional[str] = None
    alias: Optional[str] = None
    parent_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateAgentRequest(BaseModel):
    alias: Optional[str] = None
    role: Optional[str] = None
    state: Optional[str] = None
    lifecycle_phase: Optional[str] = None
    runtime_args: Optional[Dict[str, Any]] = None
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


class RegisterToolRequest(BaseModel):
    name: str
    tool_type: str = Field(..., description="browser | api | plugin | llm | system")
    version: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    execution_mode: str = "sync"
    timeout_ms: int = 30000


class GrantCapabilityRequest(BaseModel):
    agent_id: str
    tool_id: str
    scope: str = "full"
    constraints: Optional[Dict[str, Any]] = None
    expires_at: Optional[str] = None


class ApproveVersionRequest(BaseModel):
    approval_status: str = Field(..., description="approved | rejected")


class CreateConnectionRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    protocol: str
    transport: str
    source_endpoint: Optional[str] = None
    target_endpoint: Optional[str] = None
    routing_rule: Optional[str] = None
    proxy_config: Optional[Dict[str, Any]] = None


class CreateProfileRequest(BaseModel):
    agent_id: str
    profile_type: str
    account_identity: Optional[str] = None
    storage_backend: str = "google_drive"
    storage_path: str
    encryption_method: str = "fernet"
    encryption_key_ref: Optional[str] = None
    persistence_mode: str = "periodic"
    save_interval_seconds: Optional[int] = None


class CreateEnvironmentRequest(BaseModel):
    agent_id: str
    environment_type: str
    manifest: Dict[str, Any]
    storage_backend: str = "google_drive"
    storage_path: str
    visibility: str = "private"
    compatible_runtimes: Optional[List[str]] = None


# ═════════════════════════════════════════════════════════════════════════════
# AGENT CRUD
# ═════════════════════════════════════════════════════════════════════════════

@router.post("")
async def create_agent(
    req: CreateAgentRequest,
    request: Request,
    user: dict = Depends(require_worker_or_admin),  # Workers can self-register
):
    """Register a new agent in the ontology."""
    ontology = _get_ontology(request)

    if req.agent_type not in AGENT_TYPES:
        raise HTTPException(400, f"Invalid agent_type. Must be one of: {sorted(AGENT_TYPES)}")

    agent = Agent(
        agent_type=req.agent_type,
        agent_subtype=req.agent_subtype,
        role=req.role,
        alias=req.alias,
        parent_id=req.parent_id,
        config=req.config,
        metadata=req.metadata,
        created_by=user.get("sub"),
    )
    agent_id = ontology.create_agent(agent)

    # Log the creation event
    ontology.log_event(Event(
        agent_id=agent_id,
        event_type="state_change",
        summary=f"Agent created: {req.alias or agent_id} ({req.agent_type}.{req.agent_subtype})",
        payload={"created_by": user.get("sub")},
    ))

    return {"status": "success", "id": agent_id, "alias": req.alias}


@router.get("")
async def list_agents(
    request: Request,
    agent_type: Optional[str] = None,
    state: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List all agents, optionally filtered by type and/or state."""
    ontology = _get_ontology(request)
    agents = ontology.list_agents(agent_type=agent_type, state=state)
    return {"agents": agents, "total": len(agents)}


# ── Static-path GETs MUST be declared before /{agent_id} to avoid being
#    swallowed by the catch-all dynamic route. ──

@router.get("/tools")
async def list_tools(
    request: Request,
    state: str = "active",
    user: dict = Depends(get_current_user),
):
    """List registered tools."""
    ontology = _get_ontology(request)
    tools = ontology.list_tools(state=state)
    return {"tools": tools, "total": len(tools)}


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


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get a single agent with full state."""
    ontology = _get_ontology(request)
    agent = ontology.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Enrich with edges and recent operations
    edges = ontology.get_edges(agent_id, "both")
    ops = ontology.get_operations(agent_id, limit=10)
    capabilities = ontology.get_agent_capabilities(agent_id)

    return {
        "agent": agent,
        "edges": edges,
        "recent_operations": ops,
        "capabilities": capabilities,
    }


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str,
    req: UpdateAgentRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Update an agent's mutable fields (runtime_args, state, etc.)."""
    ontology = _get_ontology(request)

    existing = ontology.get_agent(agent_id)
    if not existing:
        raise HTTPException(404, "Agent not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    if "state" in updates and updates["state"] not in LIFECYCLE_STATES:
        raise HTTPException(400, f"Invalid state. Must be one of: {sorted(LIFECYCLE_STATES)}")

    success = ontology.update_agent(agent_id, **updates)
    if not success:
        raise HTTPException(500, "Failed to update agent")

    return {"status": "success", "updated_fields": list(updates.keys())}


# ═════════════════════════════════════════════════════════════════════════════
# OPERATIONS
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/{agent_id}/operations")
async def record_operation(
    agent_id: str,
    req: RecordOperationRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Record a lifecycle operation on an agent."""
    ontology = _get_ontology(request)

    existing = ontology.get_agent(agent_id)
    if not existing:
        raise HTTPException(404, "Agent not found")

    if req.operation not in OPERATION_TYPES:
        raise HTTPException(400, f"Invalid operation. Must be one of: {sorted(OPERATION_TYPES)}")

    op = AgentOperation(
        agent_id=agent_id,
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


@router.get("/{agent_id}/operations")
async def get_operations(
    agent_id: str,
    request: Request,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """Get operation history for an agent."""
    ontology = _get_ontology(request)
    ops = ontology.get_operations(agent_id, limit=limit)
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
    """Create a typed relationship between two agents."""
    ontology = _get_ontology(request)

    if req.edge_type not in EDGE_TYPES:
        raise HTTPException(400, f"Invalid edge_type. Must be one of: {sorted(EDGE_TYPES)}")

    # Verify both agents exist
    for aid in (req.source_id, req.target_id):
        if not ontology.get_agent(aid):
            raise HTTPException(404, f"Agent not found: {aid}")

    edge = AgentEdge(
        source_id=req.source_id,
        target_id=req.target_id,
        edge_type=req.edge_type,
        config=req.config,
        weight=req.weight,
        bidirectional=req.bidirectional,
    )
    edge_id = ontology.create_edge(edge)

    return {"status": "success", "edge_id": edge_id}


@router.get("/{agent_id}/edges")
async def get_edges(
    agent_id: str,
    request: Request,
    direction: str = "both",
    user: dict = Depends(get_current_user),
):
    """Get edges for an agent. direction: outgoing, incoming, or both."""
    ontology = _get_ontology(request)
    edges = ontology.get_edges(agent_id, direction=direction)
    return {"edges": edges, "total": len(edges)}


# ═════════════════════════════════════════════════════════════════════════════
# TOOLS & CAPABILITIES
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/tools")
async def register_tool(
    req: RegisterToolRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a new tool in the registry."""
    ontology = _get_ontology(request)
    tool = Tool(
        name=req.name,
        tool_type=req.tool_type,
        version=req.version,
        description=req.description,
        input_schema=req.input_schema,
        output_schema=req.output_schema,
        config=req.config,
        execution_mode=req.execution_mode,
        timeout_ms=req.timeout_ms,
    )
    tool_id = ontology.register_tool(tool)
    return {"status": "success", "tool_id": tool_id}


# NOTE: GET /tools moved before /{agent_id} to avoid route conflict


@router.post("/capabilities")
async def grant_capability(
    req: GrantCapabilityRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Grant a tool capability to an agent."""
    ontology = _get_ontology(request)
    grant = CapabilityGrant(
        agent_id=req.agent_id,
        tool_id=req.tool_id,
        granted_by=user.get("sub"),
        scope=req.scope,
        constraints=req.constraints,
    )
    grant_id = ontology.grant_capability(grant)
    return {"status": "success", "grant_id": grant_id}


@router.get("/{agent_id}/capabilities")
async def get_capabilities(
    agent_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get all tool capabilities granted to an agent."""
    ontology = _get_ontology(request)
    caps = ontology.get_agent_capabilities(agent_id)
    return {"capabilities": caps, "total": len(caps)}


# ═════════════════════════════════════════════════════════════════════════════
# VERSIONS
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/{agent_id}/versions")
async def get_versions(
    agent_id: str,
    request: Request,
    branch: str = "main",
    user: dict = Depends(get_current_user),
):
    """Get version history for an agent."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    with ontology.db.SessionLocal() as session:
        rows = session.execute(
            text("""SELECT * FROM actor_versions
                    WHERE agent_id = :id AND branch = :branch
                    ORDER BY created_at DESC"""),
            {"id": agent_id, "branch": branch}
        ).fetchall()
        versions = [dict(r._mapping) for r in rows]
    return {"versions": versions, "total": len(versions)}


@router.post("/{agent_id}/versions/{version_id}/approve")
async def approve_version(
    agent_id: str,
    version_id: str,
    req: ApproveVersionRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Approve or reject a pending agent version (human-gated authority)."""
    ontology = _get_ontology(request)
    from sqlalchemy import text

    with ontology.db.safe_transaction() as session:
        row = session.execute(
            text("SELECT * FROM actor_versions WHERE id = :id AND agent_id = :aid"),
            {"id": version_id, "aid": agent_id}
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
                        WHERE agent_id = :aid AND branch = :branch AND is_current = 1"""),
                {"aid": agent_id, "branch": version.get("branch", "main")}
            )
            session.execute(
                text("UPDATE actor_versions SET is_current = 1 WHERE id = :id"),
                {"id": version_id}
            )


    ontology.log_event(Event(
        agent_id=agent_id,
        event_type="state_change",
        summary=f"Version {version.get('version_tag')} {req.approval_status} by {user.get('sub')}",
        payload={"version_id": version_id, "status": req.approval_status},
    ))

    return {"status": "success", "approval_status": req.approval_status}


@router.post("/{agent_id}/rollback")
async def rollback_version(
    agent_id: str,
    request: Request,
    target_version_id: Optional[str] = None,
    user: dict = Depends(require_admin),
):
    """Rollback an agent to a previous version."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    import hashlib

    with ontology.db.safe_transaction() as session:
        # Find target version (specified or previous)
        if target_version_id:
            row = session.execute(
                text("SELECT * FROM actor_versions WHERE id = :id AND agent_id = :aid"),
                {"id": target_version_id, "aid": agent_id}
            ).fetchone()
        else:
            # Get the second most recent approved version
            row = session.execute(
                text("""SELECT * FROM actor_versions
                        WHERE agent_id = :aid AND approval_status = 'approved'
                        ORDER BY created_at DESC LIMIT 1 OFFSET 1"""),
                {"aid": agent_id}
            ).fetchone()

        if not row:
            raise HTTPException(404, "No version to rollback to")

        target = dict(row._mapping)

        # Apply the config snapshot
        config_snapshot = target.get("config_snapshot")
        if config_snapshot:
            ontology.update_agent(agent_id, config=_from_json(config_snapshot))

        # Create a rollback version entry
        rollback_hash = hashlib.sha256(
            _to_json({"rollback_to": target["id"]}).encode()
        ).hexdigest()

        rollback_version = AgentVersion(
            agent_id=agent_id,
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
                    WHERE agent_id = :aid AND id != :new_id"""),
            {"aid": agent_id, "new_id": rollback_version.id}
        )

    # Record the rollback operation
    ontology.record_operation(AgentOperation(
        agent_id=agent_id,
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

# NOTE: GET /connections moved before /{agent_id} to avoid route conflict


@router.post("/connections")
async def create_connection(
    req: CreateConnectionRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a new runtime connection."""
    ontology = _get_ontology(request)
    conn = RuntimeConnection(
        source_agent_id=req.source_agent_id,
        target_agent_id=req.target_agent_id,
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
    """Register an agent profile (browser, tailscale, etc.)."""
    ontology = _get_ontology(request)
    profile = AgentProfile(
        agent_id=req.agent_id,
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


@router.get("/{agent_id}/profiles")
async def get_profiles(
    agent_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get all profiles for an agent."""
    ontology = _get_ontology(request)
    from sqlalchemy import text
    with ontology.db.SessionLocal() as session:
        rows = session.execute(
            text("SELECT * FROM actor_profiles WHERE agent_id = :id ORDER BY created_at DESC"),
            {"id": agent_id}
        ).fetchall()
        profiles = [dict(r._mapping) for r in rows]
    return {"profiles": profiles, "total": len(profiles)}


# ═════════════════════════════════════════════════════════════════════════════
# ENVIRONMENTS
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/environments")
async def create_environment(
    req: CreateEnvironmentRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Register a portable agent environment bundle."""
    ontology = _get_ontology(request)
    env = AgentEnvironment(
        agent_id=req.agent_id,
        environment_type=req.environment_type,
        manifest=req.manifest,
        storage_backend=req.storage_backend,
        storage_path=req.storage_path,
        visibility=req.visibility,
        compatible_runtimes=req.compatible_runtimes,
    )
    row = env.to_db_row()
    from sqlalchemy import text
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with ontology.db.safe_transaction() as session:
        session.execute(text(f"INSERT INTO bundles ({cols}) VALUES ({placeholders})"), row)

    return {"status": "success", "environment_id": env.id}


# ═════════════════════════════════════════════════════════════════════════════
# EVENTS (read-only)
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/{agent_id}/events")
async def get_events(
    agent_id: str,
    request: Request,
    event_type: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Get telemetry/audit events for an agent."""
    ontology = _get_ontology(request)
    events = ontology.get_events(agent_id=agent_id, event_type=event_type, limit=limit)
    return {"events": events, "total": len(events)}
