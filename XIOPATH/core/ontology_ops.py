"""
XIOPATH — Ontology Database Operations (v5.0)
=================================================
CRUD operations for the ontology tables (actors, operations, edges, etc.).
Builds on top of the existing DatabaseManager's SessionLocal.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import text

from core.ontology_models import (
    Actor, Operation, ActorEdge, Capability, CapabilityGrant, Event,
    # Backward-compatible aliases for external consumers
    Agent, AgentOperation, AgentEdge, Tool,
    uuid7, utcnow, _to_json, _from_json,
)

logger = logging.getLogger(__name__)


class OntologyManager:
    """
    Manages CRUD operations for the ontology schema tables.
    Wraps around an existing DatabaseManager instance.
    """

    def __init__(self, db_manager):
        """
        Args:
            db_manager: A core.database.DatabaseManager instance with SessionLocal.
        """
        self.db = db_manager

    # ─── ACTORS ──────────────────────────────────────────────────────────────

    def create_actor(self, actor: Actor) -> str:
        """Insert a new actor. Returns the actor ID."""
        row = actor.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        with self.db.SessionLocal() as session:
            session.execute(
                text(f"INSERT INTO actors ({cols}) VALUES ({placeholders})"),
                row
            )
            session.commit()
        logger.info(f"Actor created: {actor.alias or actor.id} ({actor.actor_type}.{actor.actor_subtype})")
        return actor.id

    # Backward-compatible alias
    def create_agent(self, agent: Actor) -> str:
        return self.create_actor(agent)

    def get_actor(self, actor_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single actor by ID."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM actors WHERE id = :id"), {"id": actor_id}
            ).fetchone()
            if not row:
                return None
            return dict(row._mapping)

    # Backward-compatible alias
    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self.get_actor(agent_id)

    def update_actor(self, actor_id: str, **updates) -> bool:
        """Update specific fields on an actor."""
        updates["updated_at"] = utcnow()
        # Serialize JSON fields
        for key in ("config", "runtime_state", "metadata"):
            if key in updates and not isinstance(updates[key], str):
                updates[key] = _to_json(updates[key])
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["_id"] = actor_id
        with self.db.SessionLocal() as session:
            result = session.execute(
                text(f"UPDATE actors SET {set_clause} WHERE id = :_id"),
                updates
            )
            session.commit()
            return result.rowcount > 0

    # Backward-compatible alias
    def update_agent(self, agent_id: str, **updates) -> bool:
        return self.update_actor(agent_id, **updates)

    def list_actors(self, actor_type: Optional[str] = None, state: Optional[str] = None) -> List[Dict]:
        """List actors, optionally filtered by type and/or state."""
        query = "SELECT * FROM actors WHERE 1=1"
        params = {}
        if actor_type:
            query += " AND actor_type = :actor_type"
            params["actor_type"] = actor_type
        if state:
            query += " AND state = :state"
            params["state"] = state
        query += " ORDER BY created_at DESC"
        with self.db.SessionLocal() as session:
            rows = session.execute(text(query), params).fetchall()
            return [dict(r._mapping) for r in rows]

    # Backward-compatible alias
    def list_agents(self, agent_type: Optional[str] = None, state: Optional[str] = None) -> List[Dict]:
        return self.list_actors(actor_type=agent_type, state=state)

    # ─── OPERATIONS ──────────────────────────────────────────────────────────

    def record_operation(self, op: Operation) -> str:
        """Insert an operation record. Returns the operation ID."""
        row = op.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        with self.db.SessionLocal() as session:
            session.execute(
                text(f"INSERT INTO operations ({cols}) VALUES ({placeholders})"),
                row
            )
            # Update the actor's state if to_state is specified
            if op.to_state:
                session.execute(
                    text("UPDATE actors SET state = :state, updated_at = :now WHERE id = :id"),
                    {"state": op.to_state, "now": utcnow(), "id": op.actor_id}
                )
            session.commit()
        logger.info(f"Operation recorded: {op.operation} on {op.actor_id} ({op.outcome or 'pending'})")
        return op.id

    def get_operations(self, actor_id: str, limit: int = 50) -> List[Dict]:
        """Get operation history for an actor, newest first."""
        with self.db.SessionLocal() as session:
            rows = session.execute(
                text("SELECT * FROM operations WHERE actor_id = :id ORDER BY started_at DESC LIMIT :limit"),
                {"id": actor_id, "limit": limit}
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    # ─── EDGES ───────────────────────────────────────────────────────────────

    def create_edge(self, edge: ActorEdge) -> str:
        """Insert a new directed edge. Returns the edge ID."""
        row = edge.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        with self.db.SessionLocal() as session:
            session.execute(
                text(f"INSERT INTO actor_edges ({cols}) VALUES ({placeholders})"),
                row
            )
            session.commit()
        logger.info(f"Edge created: {edge.source_id} --[{edge.edge_type}]--> {edge.target_id}")
        return edge.id

    def get_edges(self, actor_id: str, direction: str = "outgoing") -> List[Dict]:
        """Get edges for an actor. direction: 'outgoing', 'incoming', or 'both'."""
        queries = []
        params = {"id": actor_id}
        if direction in ("outgoing", "both"):
            queries.append("SELECT * FROM actor_edges WHERE source_id = :id AND state = 'active'")
        if direction in ("incoming", "both"):
            queries.append("SELECT * FROM actor_edges WHERE target_id = :id AND state = 'active'")
        full_query = " UNION ALL ".join(queries) + " ORDER BY created_at DESC"
        with self.db.SessionLocal() as session:
            rows = session.execute(text(full_query), params).fetchall()
            return [dict(r._mapping) for r in rows]

    # ─── CAPABILITIES ────────────────────────────────────────────────────────

    def register_capability(self, capability: Capability) -> str:
        """Register a new capability. Returns the capability ID."""
        row = capability.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        with self.db.SessionLocal() as session:
            session.execute(
                text(f"INSERT INTO capabilities ({cols}) VALUES ({placeholders})"),
                row
            )
            session.commit()
        logger.info(f"Capability registered: {capability.name} ({capability.capability_type})")
        return capability.id

    # Backward-compatible alias
    def register_tool(self, tool: Capability) -> str:
        return self.register_capability(tool)

    def list_capabilities(self, state: str = "active") -> List[Dict]:
        """List capabilities, optionally filtered by state."""
        with self.db.SessionLocal() as session:
            rows = session.execute(
                text("SELECT * FROM capabilities WHERE state = :state ORDER BY name"),
                {"state": state}
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    # Backward-compatible alias
    def list_tools(self, state: str = "active") -> List[Dict]:
        return self.list_capabilities(state=state)

    # ─── CAPABILITY GRANTS ───────────────────────────────────────────────────

    def grant_capability(self, grant: CapabilityGrant) -> str:
        """Grant a capability to an actor. Returns the grant ID."""
        row = grant.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        with self.db.SessionLocal() as session:
            session.execute(
                text(f"INSERT INTO capability_grants ({cols}) VALUES ({placeholders})"),
                row
            )
            session.commit()
        logger.info(f"Capability granted: {grant.actor_id} → {grant.capability_id}")
        return grant.id

    def get_actor_capabilities(self, actor_id: str) -> List[Dict]:
        """Get all active capability grants for an actor."""
        with self.db.SessionLocal() as session:
            rows = session.execute(
                text("""
                    SELECT cg.*, c.name as capability_name, c.capability_type
                    FROM capability_grants cg
                    JOIN capabilities c ON cg.capability_id = c.id
                    WHERE cg.actor_id = :id AND cg.state = 'active'
                    ORDER BY cg.created_at DESC
                """),
                {"id": actor_id}
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    # Backward-compatible alias
    def get_agent_capabilities(self, agent_id: str) -> List[Dict]:
        return self.get_actor_capabilities(agent_id)

    # ─── EVENTS ──────────────────────────────────────────────────────────────

    def log_event(self, event: Event) -> str:
        """Log a telemetry/audit event. Returns the event ID."""
        row = event.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        with self.db.SessionLocal() as session:
            session.execute(
                text(f"INSERT INTO events ({cols}) VALUES ({placeholders})"),
                row
            )
            session.commit()
        return event.id

    def get_events(self, actor_id: Optional[str] = None, event_type: Optional[str] = None,
                   correlation_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Query events with optional filters."""
        query = "SELECT * FROM events WHERE 1=1"
        params = {"limit": limit}
        if actor_id:
            query += " AND actor_id = :actor_id"
            params["actor_id"] = actor_id
        if event_type:
            query += " AND event_type = :event_type"
            params["event_type"] = event_type
        if correlation_id:
            query += " AND correlation_id = :correlation_id"
            params["correlation_id"] = correlation_id
        query += " ORDER BY created_at DESC LIMIT :limit"
        with self.db.SessionLocal() as session:
            rows = session.execute(text(query), params).fetchall()
            return [dict(r._mapping) for r in rows]

    # ─── SEED ────────────────────────────────────────────────────────────────

    def seed_initial_actors(self) -> Dict[str, str]:
        """
        Seed the 3 foundational actors + their relationships.
        Idempotent: skips if actors already exist.
        Returns a dict of {alias: id} for the created actors.
        """
        # Check if already seeded
        existing = self.list_actors()
        if existing:
            logger.info(f"Seed skipped: {len(existing)} actors already exist")
            return {a["alias"]: a["id"] for a in existing if a.get("alias")}

        now = utcnow()
        actors = {}

        # 1. Super Admin (human)
        sa = Actor(
            actor_type="human", actor_subtype="admin",
            role="owner", alias="Super Admin",
            state="active", lifecycle_phase="operational",
            trust_tier="admin",
            created_at=now,
        )
        self.create_actor(sa)
        actors["super_admin"] = sa.id

        # 2. API Server (compute actor)
        api = Actor(
            actor_type="compute", actor_subtype="api_server",
            role="api_gateway", alias="API Server",
            parent_id=sa.id,
            state="active", lifecycle_phase="operational",
            created_by=sa.id, created_at=now,
        )
        self.create_actor(api)
        actors["api_server"] = api.id

        # 3. LLM Engine Template (AI actor — template for actual workers)
        llm = Actor(
            actor_type="ai", actor_subtype="llm_engine",
            role="inference_engine", alias="LLM Engine Template",
            parent_id=sa.id,
            state="designing", lifecycle_phase="pre_birth",
            created_by=sa.id, created_at=now,
            config={"model": "gemini-2.0-flash", "connection": "websocket"},
        )
        self.create_actor(llm)
        actors["llm_engine"] = llm.id

        # --- EDGES ---
        # Super Admin manages API Server
        self.create_edge(ActorEdge(
            source_id=sa.id, target_id=api.id,
            edge_type="manages", created_at=now,
        ))
        # Super Admin collaborates with LLM Engine
        self.create_edge(ActorEdge(
            source_id=sa.id, target_id=llm.id,
            edge_type="collaborates_with", bidirectional=True,
            created_at=now,
        ))

        # --- LOG SEED EVENT ---
        self.log_event(Event(
            actor_id=sa.id,
            event_type="state_change",
            severity="info",
            summary="Ontology seed: 3 foundational actors + 2 edges created",
            payload={"actors": actors},
            created_at=now,
        ))

        # --- RECORD OPERATION ---
        self.record_operation(Operation(
            actor_id=api.id,
            operation="initiation",
            from_state="proposed", to_state="active",
            trigger="system",
            initiated_by=sa.id,
            collaborators=[{"actor_id": sa.id, "role": "owner"}],
            scope="organization", depth_level=0,
            rationale="Initial platform seed — v5.0 Three Primitives ontology",
            outcome="success",
            started_at=now, completed_at=now, duration_ms=0,
        ))

        logger.info(f"Seed complete: {len(actors)} actors, 2 edges, 1 event, 1 operation")
        return actors

    # Backward-compatible alias
    def seed_initial_agents(self) -> Dict[str, str]:
        return self.seed_initial_actors()

