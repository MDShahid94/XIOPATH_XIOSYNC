"""
XIOPATH — Phantom ↔ Ontology Bridge
======================================
Maps every phantom lifecycle action to the Universal Agent Ontology.

This is the SOLE integration point between the phantom infrastructure
and the ontology system. All phantom modules route through this bridge
to ensure every phantom entity, lifecycle event, and health check
appears in the ontology graph.

Design principle: Phantom internal models (vault, identity, TOTP seeds)
remain as internal data structures. But the *identity* and *lifecycle*
of each phantom lives in the ontology `agents` table.

Educational purpose only.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from core.ontology_models import (
    Actor, Operation, ActorEdge, Capability, CapabilityGrant, Event,
    uuid7, utcnow,
    ACTOR_SUBTYPES, EDGE_TYPES, LIFECYCLE_STATES,
)
from core.ontology_ops import OntologyManager

logger = logging.getLogger("phantom.ontology_bridge")


# ─── State Mapping ──────────────────────────────────────────────────────────

# Maps PhantomState enum values → (lifecycle_state, lifecycle_phase)
PHANTOM_STATE_MAP = {
    "provisioning": ("provisioning", "birth"),
    "aging":        ("aging", "birth"),
    "active":       ("active", "operational"),
    "locked":       ("locked", "operational"),
    "recovering":   ("recovering", "operational"),
    "dead":         ("terminated", "end_of_life"),
    "revoked":      ("archived", "end_of_life"),
}

# Maps resource types from harvester → (agent_type, agent_subtype)
RESOURCE_TYPE_MAP = {
    "worker":   ("compute", "edge_worker"),
    "d1":       ("tool", "browser_tool"),
    "r2":       ("tool", "browser_tool"),
    "kv":       ("tool", "browser_tool"),
    "gpu":      ("compute", "gpu_node"),
    "actions":  ("compute", "ci_runner"),
}


class PhantomOntologyBridge:
    """
    Bridge between the phantom infrastructure and the Universal Agent Ontology.

    Every phantom action (create, provision phase, health check, harvest)
    flows through this bridge to produce proper ontology records in the
    agents, agent_operations, agent_edges, event_log, and tool_registry tables.
    """

    def __init__(self, ontology: OntologyManager, phantom_mesh_id: Optional[str] = None):
        """
        Args:
            ontology: An initialized OntologyManager instance.
            phantom_mesh_id: The agent ID of the Phantom Mesh ecosystem agent.
                             If None, will be auto-discovered from the ontology.
        """
        self.ontology = ontology
        self._phantom_mesh_id = phantom_mesh_id
        self._tool_ids: Dict[str, str] = {}  # tool_name → tool_id cache

    @property
    def phantom_mesh_id(self) -> Optional[str]:
        """Lazily discover the Phantom Mesh ecosystem agent ID."""
        if self._phantom_mesh_id is None:
            agents = self.ontology.list_agents(agent_type="ecosystem")
            for agent in agents:
                if agent.get("agent_subtype") == "phantom_mesh":
                    self._phantom_mesh_id = agent["id"]
                    break
        return self._phantom_mesh_id

    # ═══════════════════════════════════════════════════════════════════════
    # AGENT REGISTRATION
    # ═══════════════════════════════════════════════════════════════════════

    def register_phantom_as_agent(
        self,
        phantom_id: str,
        identity_summary: Dict[str, Any],
        member_donor_id: str,
    ) -> str:
        """
        Register a new phantom as an Agent in the ontology.

        Creates:
          - Agent row (compute.phantom_node)
          - Edge: phantom_mesh --[manages]--> phantom
          - Edge: member_donor --[donates_to]--> phantom
          - Operation: provisioning started

        Args:
            phantom_id: The phantom's vault ID.
            identity_summary: Non-sensitive summary (locale, email domain, etc.)
            member_donor_id: Agent ID of the member who donated verification.

        Returns:
            The ontology agent ID for this phantom.
        """
        now = utcnow()

        # Create the phantom agent
        agent = Agent(
            id=phantom_id,  # Use vault ID as ontology ID for 1:1 mapping
            agent_type="compute",
            agent_subtype="phantom_node",
            role="mesh_node",
            alias=f"phantom-{phantom_id[:8]}",
            parent_id=self.phantom_mesh_id,
            state="provisioning",
            lifecycle_phase="birth",
            config={
                "locale": identity_summary.get("locale", "en-US"),
                "email_domain": identity_summary.get("email_domain"),
                "services_planned": identity_summary.get("services", []),
            },
            health_status="unknown",
            created_by=member_donor_id,
            created_at=now,
            metadata={
                "phantom_version": "1.0",
                "donor_id": member_donor_id,
            },
        )
        self.ontology.create_agent(agent)
        logger.info(f"Phantom registered as agent: {phantom_id[:8]} (compute.phantom_node)")

        # Edge: Phantom Mesh manages this phantom
        if self.phantom_mesh_id:
            self.ontology.create_edge(AgentEdge(
                source_id=self.phantom_mesh_id,
                target_id=phantom_id,
                edge_type="manages",
                created_at=now,
            ))

        # Edge: Member donated to this phantom
        if member_donor_id:
            self.ontology.create_edge(AgentEdge(
                source_id=member_donor_id,
                target_id=phantom_id,
                edge_type="donates_to",
                metadata={"donated_at": now.isoformat()},
                created_at=now,
            ))

        # Operation: provisioning started
        self.ontology.record_operation(AgentOperation(
            agent_id=phantom_id,
            operation="provisioning",
            from_state="proposed",
            to_state="provisioning",
            trigger="system",
            initiated_by=member_donor_id or "system",
            scope="agent",
            rationale="Phantom provisioning initiated",
            outcome="pending",
            started_at=now,
        ))

        # Event: phantom_provisioned
        self.ontology.log_event(Event(
            agent_id=phantom_id,
            event_type="phantom_provisioned",
            severity="info",
            summary=f"Phantom {phantom_id[:8]} provisioning started",
            payload=identity_summary,
            created_at=now,
        ))

        return phantom_id

    def register_child_resource(
        self,
        phantom_agent_id: str,
        resource_type: str,
        resource_data: Dict[str, Any],
    ) -> str:
        """
        Register a harvested resource as a child agent under a phantom.

        Creates:
          - Agent row (e.g., compute.edge_worker, compute.gpu_node)
          - Edge: phantom --[manages]--> child resource

        Args:
            phantom_agent_id: Parent phantom's agent ID.
            resource_type: Type key ("worker", "d1", "r2", "kv", "gpu", "actions").
            resource_data: Service-specific metadata (endpoint, limits, etc.)

        Returns:
            The ontology agent ID for this child resource.
        """
        now = utcnow()
        agent_type, agent_subtype = RESOURCE_TYPE_MAP.get(
            resource_type, ("tool", "browser_tool")
        )

        resource_id = resource_data.get("resource_id", uuid7())
        alias = resource_data.get("alias", f"{resource_type}-{resource_id[:8]}")

        child = Agent(
            id=resource_id if isinstance(resource_id, str) and len(resource_id) > 8 else uuid7(),
            agent_type=agent_type,
            agent_subtype=agent_subtype,
            role=f"{resource_type}_resource",
            alias=alias,
            parent_id=phantom_agent_id,
            state="active",
            lifecycle_phase="operational",
            config={
                "resource_type": resource_type,
                "endpoint": resource_data.get("endpoint"),
                "limits": resource_data.get("limits"),
            },
            health_status="healthy",
            created_by=phantom_agent_id,
            created_at=now,
            metadata=resource_data,
        )
        self.ontology.create_agent(child)

        # Edge: phantom manages child resource
        self.ontology.create_edge(AgentEdge(
            source_id=phantom_agent_id,
            target_id=child.id,
            edge_type="manages",
            metadata={"resource_type": resource_type},
            created_at=now,
        ))

        # Edge: child deployed_on phantom
        self.ontology.create_edge(AgentEdge(
            source_id=child.id,
            target_id=phantom_agent_id,
            edge_type="deployed_on",
            created_at=now,
        ))

        # Event
        self.ontology.log_event(Event(
            agent_id=phantom_agent_id,
            event_type="resource_harvested",
            severity="info",
            summary=f"Resource {resource_type} ({alias}) harvested for phantom {phantom_agent_id[:8]}",
            payload={"resource_id": child.id, "resource_type": resource_type},
            created_at=now,
        ))

        logger.info(f"Child resource registered: {alias} ({agent_type}.{agent_subtype}) → parent {phantom_agent_id[:8]}")
        return child.id

    # ═══════════════════════════════════════════════════════════════════════
    # LIFECYCLE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def record_provision_phase(
        self,
        phantom_agent_id: str,
        phase_name: str,
        from_state: str,
        to_state: str,
        outcome: str = "pending",
        rationale: str = "",
        parent_op_id: Optional[str] = None,
    ) -> str:
        """
        Log a provisioning pipeline phase as an AgentOperation.

        Returns the operation ID for chaining.
        """
        now = utcnow()

        # Map phantom states to ontology states
        onto_from = PHANTOM_STATE_MAP.get(from_state, (from_state, "birth"))[0]
        onto_to = PHANTOM_STATE_MAP.get(to_state, (to_state, "birth"))[0]

        op = AgentOperation(
            agent_id=phantom_agent_id,
            operation="provisioning",
            from_state=onto_from,
            to_state=onto_to,
            trigger="system",
            initiated_by="system",
            scope="agent",
            depth_level=1 if parent_op_id else 0,
            parent_operation_id=parent_op_id,
            rationale=rationale or f"Pipeline phase: {phase_name}",
            outcome=outcome,
            metadata={"phase": phase_name},
            started_at=now,
            completed_at=now if outcome in ("success", "failed") else None,
        )
        op_id = self.ontology.record_operation(op)
        logger.info(f"Phase recorded: {phase_name} ({onto_from} → {onto_to}) [{outcome}]")
        return op_id

    def update_phantom_state(
        self,
        phantom_agent_id: str,
        new_state: str,
        reason: str = "",
    ) -> bool:
        """
        Update a phantom's lifecycle state in the ontology.
        Maps PhantomState values to ontology lifecycle states.
        """
        state, phase = PHANTOM_STATE_MAP.get(new_state, (new_state, "operational"))
        return self.ontology.update_agent(
            phantom_agent_id,
            state=state,
            lifecycle_phase=phase,
            metadata={"state_reason": reason} if reason else None,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # HEALTH MONITORING
    # ═══════════════════════════════════════════════════════════════════════

    def update_phantom_health(
        self,
        phantom_agent_id: str,
        health_result: Dict[str, Any],
    ) -> None:
        """
        Map a HealthCheckResult to ontology Agent.health_status + Event.

        Maps overall_status:
          - healthy → "healthy"
          - degraded → "degraded"
          - locked → "offline"  (and triggers state change to "locked")
          - dead → "offline"    (and triggers state change to "terminated")
        """
        now = utcnow()
        status = health_result.get("overall_status", "unknown")

        # Map to ontology health_status
        health_map = {
            "healthy": "healthy",
            "degraded": "degraded",
            "locked": "offline",
            "dead": "offline",
        }
        ontology_health = health_map.get(status, "unknown")

        # Update agent
        self.ontology.update_agent(
            phantom_agent_id,
            health_status=ontology_health,
        )

        # If locked or dead, also update lifecycle state
        if status == "locked":
            self.update_phantom_state(phantom_agent_id, "locked", "Account locked during health check")
            self.ontology.log_event(Event(
                agent_id=phantom_agent_id,
                event_type="phantom_locked",
                severity="warn",
                summary=f"Phantom {phantom_agent_id[:8]} detected as locked",
                payload=health_result,
                created_at=now,
            ))
        elif status == "dead":
            self.update_phantom_state(phantom_agent_id, "dead", "Account dead during health check")

        # Log health check event
        self.ontology.log_event(Event(
            agent_id=phantom_agent_id,
            event_type="phantom_health_check",
            severity="info" if status in ("healthy", "degraded") else "warn",
            summary=f"Health check: {status} (issues: {len(health_result.get('issues', []))})",
            payload=health_result,
            created_at=now,
        ))

    def record_recovery(
        self,
        phantom_agent_id: str,
        recovery_result: Dict[str, Any],
    ) -> str:
        """Log a recovery attempt as an AgentOperation."""
        now = utcnow()
        success = recovery_result.get("success", False)

        op = AgentOperation(
            agent_id=phantom_agent_id,
            operation="recovery",
            from_state="locked",
            to_state="active" if success else "locked",
            trigger="auto",
            initiated_by="system",
            scope="agent",
            rationale=f"Auto-recovery: {len(recovery_result.get('actions', []))} actions attempted",
            outcome="success" if success else "failed",
            metadata=recovery_result,
            started_at=now,
            completed_at=now,
        )
        op_id = self.ontology.record_operation(op)

        if success:
            self.update_phantom_state(phantom_agent_id, "active", "Recovered from locked state")
            self.ontology.log_event(Event(
                agent_id=phantom_agent_id,
                event_type="phantom_recovered",
                severity="info",
                summary=f"Phantom {phantom_agent_id[:8]} recovered successfully",
                payload=recovery_result,
                created_at=now,
            ))

        return op_id

    # ═══════════════════════════════════════════════════════════════════════
    # DONOR EDGES
    # ═══════════════════════════════════════════════════════════════════════

    def create_donor_edge(
        self,
        member_agent_id: str,
        phantom_agent_id: str,
    ) -> str:
        """Create a donates_to edge from a member to a phantom."""
        edge = AgentEdge(
            source_id=member_agent_id,
            target_id=phantom_agent_id,
            edge_type="donates_to",
            metadata={"donated_at": utcnow().isoformat()},
            created_at=utcnow(),
        )
        return self.ontology.create_edge(edge)

    # ═══════════════════════════════════════════════════════════════════════
    # TOOL REGISTRATION
    # ═══════════════════════════════════════════════════════════════════════

    def register_phantom_tools(self) -> Dict[str, str]:
        """
        Register all phantom pipeline components as Tools in the ontology.
        Idempotent — checks if tools already exist before creating.

        Returns dict of {tool_name: tool_id}.
        """
        existing_tools = self.ontology.list_tools(state="active")
        existing_names = {t["name"] for t in existing_tools}

        tools_to_register = [
            Tool(
                name="IdentityForge",
                tool_type="system",
                version="1.0.0",
                description="Generates synthetic identities with locale-aware demographics",
                execution_mode="async",
                timeout_ms=60000,
            ),
            Tool(
                name="SanitizationPipeline",
                tool_type="system",
                version="1.0.0",
                description="Severs device linkage, rotates credentials, enables 2FA",
                execution_mode="async",
                timeout_ms=120000,
            ),
            Tool(
                name="SessionMigrator",
                tool_type="system",
                version="1.0.0",
                description="3-day gradual IP migration with travel-plausible country hops",
                execution_mode="async",
                timeout_ms=300000,
            ),
            Tool(
                name="ProfileAger",
                tool_type="system",
                version="1.0.0",
                description="30-day profile warm-up with organic browsing patterns",
                execution_mode="async",
                timeout_ms=600000,
            ),
            Tool(
                name="ResourceHarvester",
                tool_type="system",
                version="1.0.0",
                description="Deploys Node Agents, creates D1/R2/KV, generates GPU notebooks",
                execution_mode="async",
                timeout_ms=120000,
            ),
            Tool(
                name="PhantomOrchestrator",
                tool_type="system",
                version="1.0.0",
                description="End-to-end 9-phase provisioning pipeline",
                execution_mode="async",
                timeout_ms=86400000,  # 24h — lifecycle is long
            ),
        ]

        result = {}
        for tool in tools_to_register:
            if tool.name in existing_names:
                # Find existing tool ID
                for t in existing_tools:
                    if t["name"] == tool.name:
                        result[tool.name] = t["id"]
                        break
                logger.info(f"Tool already registered: {tool.name}")
            else:
                tool_id = self.ontology.register_tool(tool)
                result[tool.name] = tool_id
                logger.info(f"Tool registered: {tool.name} → {tool_id}")

                # Edge: Phantom Mesh provides this tool
                if self.phantom_mesh_id:
                    self.ontology.create_edge(AgentEdge(
                        source_id=self.phantom_mesh_id,
                        target_id=tool_id,
                        edge_type="provides_tool",
                        created_at=utcnow(),
                    ))

        self._tool_ids = result
        return result

    def grant_phantom_capabilities(
        self,
        phantom_agent_id: str,
        tool_names: Optional[List[str]] = None,
        granted_by: str = "system",
    ) -> List[str]:
        """
        Grant capability_grants so a phantom can use registered tools.

        Args:
            phantom_agent_id: The phantom's agent ID.
            tool_names: Which tools to grant. Defaults to all phantom tools.
            granted_by: Agent ID of the granter.

        Returns:
            List of grant IDs.
        """
        if not self._tool_ids:
            self.register_phantom_tools()

        if tool_names is None:
            tool_names = list(self._tool_ids.keys())

        grants = []
        for name in tool_names:
            tool_id = self._tool_ids.get(name)
            if not tool_id:
                continue

            grant = CapabilityGrant(
                agent_id=phantom_agent_id,
                tool_id=tool_id,
                granted_by=granted_by,
                scope="full",
                state="active",
            )
            grant_id = self.ontology.grant_capability(grant)
            grants.append(grant_id)

        return grants

    # ═══════════════════════════════════════════════════════════════════════
    # QUERY HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def list_phantoms(self, state: Optional[str] = None) -> List[Dict]:
        """List all phantom agents, optionally filtered by state."""
        agents = self.ontology.list_agents(agent_type="compute")
        phantoms = [a for a in agents if a.get("agent_subtype") == "phantom_node"]
        if state:
            onto_state = PHANTOM_STATE_MAP.get(state, (state, None))[0]
            phantoms = [p for p in phantoms if p.get("state") == onto_state]
        return phantoms

    def get_phantom_children(self, phantom_agent_id: str) -> List[Dict]:
        """Get all child resource agents under a phantom."""
        edges = self.ontology.get_edges(phantom_agent_id, direction="outgoing")
        child_ids = [e["target_id"] for e in edges if e.get("edge_type") == "manages"]
        children = []
        for cid in child_ids:
            agent = self.ontology.get_agent(cid)
            if agent:
                children.append(agent)
        return children

    def get_phantom_history(self, phantom_agent_id: str, limit: int = 50) -> List[Dict]:
        """Get the full operation history for a phantom."""
        return self.ontology.get_operations(phantom_agent_id, limit=limit)

    def get_fleet_stats(self) -> Dict[str, int]:
        """Get aggregate stats for the phantom fleet from ontology."""
        phantoms = self.list_phantoms()
        stats = {
            "total": len(phantoms),
            "provisioning": 0,
            "aging": 0,
            "active": 0,
            "locked": 0,
            "terminated": 0,
            "healthy": 0,
            "degraded": 0,
            "offline": 0,
        }
        for p in phantoms:
            state = p.get("state", "unknown")
            stats[state] = stats.get(state, 0) + 1
            health = p.get("health_status", "unknown")
            stats[health] = stats.get(health, 0) + 1
        return stats
