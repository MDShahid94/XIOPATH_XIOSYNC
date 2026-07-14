"""
XIOPATH — Phantom API Client (Phase 10)
==========================================
Decoupled client that phantom modules use to interact with the core platform.

Instead of importing core modules directly, phantom components use this
client which wraps the platform's public interfaces. This enables:
  - Phantom to be extracted as a standalone project
  - Clean dependency boundary between core and phantom
  - Testability via mock client injection

Usage:
    from phantom.api_client import PhantomPlatformClient
    client = PhantomPlatformClient(db)
    client.register_actor(actor_type="compute", actor_subtype="phantom_node", ...)
    client.register_custom_types([...])
    client.store_knowledge(domain="...", intent="...", action_spec={...})
"""
import json
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger("PhantomPlatformClient")


class PhantomPlatformClient:
    """
    Facade providing phantom modules with access to core platform capabilities.

    This is the ONLY approved interface between phantom/ and core/.
    Direct imports of core modules from phantom code should be replaced
    with calls through this client.
    """

    def __init__(self, db, type_registry=None, knowledge_manager=None, workflow_manager=None):
        self.db = db
        self._type_registry = type_registry
        self._knowledge_manager = knowledge_manager
        self._workflow_manager = workflow_manager

    # ─── Lazy accessors ──────────────────────────────────────────────────

    @property
    def type_registry(self):
        if self._type_registry is None:
            from core.type_registry import TypeRegistry
            self._type_registry = TypeRegistry(self.db)
        return self._type_registry

    @property
    def knowledge_manager(self):
        if self._knowledge_manager is None:
            from core.knowledge_manager import KnowledgeManager
            self._knowledge_manager = KnowledgeManager(self.db, type_registry=self.type_registry)
        return self._knowledge_manager

    @property
    def workflow_manager(self):
        if self._workflow_manager is None:
            from core.workflow_manager import WorkflowManager
            self._workflow_manager = WorkflowManager(self.db, knowledge_manager=self.knowledge_manager)
        return self._workflow_manager

    # ═══════════════════════════════════════════════════════════════════════
    # ACTOR OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def register_actor(
        self,
        actor_type: str,
        actor_subtype: str,
        role: str,
        alias: Optional[str] = None,
        parent_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> Optional[str]:
        """Register an actor in the ontology. Returns actor_id."""
        try:
            from core.ontology_ops import OntologyManager
            from core.ontology_models import Actor
            ontology = OntologyManager(self.db)
            actor = Actor(
                actor_type=actor_type,
                actor_subtype=actor_subtype,
                role=role,
                alias=alias,
                parent_id=parent_id,
                config=config,
            )
            return ontology.create_actor(actor)
        except Exception as e:
            logger.warning(f"Failed to register actor: {e}")
            return None

    def create_edge(self, source_id: str, target_id: str, edge_type: str, strength: float = 1.0) -> Optional[str]:
        """Create an edge between two actors."""
        try:
            from core.ontology_ops import OntologyManager
            from core.ontology_models import ActorEdge
            ontology = OntologyManager(self.db)
            edge = ActorEdge(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                strength=strength,
            )
            return ontology.create_edge(edge)
        except Exception as e:
            logger.warning(f"Failed to create edge: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE REGISTRATION
    # ═══════════════════════════════════════════════════════════════════════

    def register_custom_types(self, types: List[Dict[str, Any]]) -> int:
        """
        Register phantom-specific custom types in the type registry.

        Each type dict should have: category, name, description, is_builtin=False
        Returns count of successfully registered types.
        """
        count = 0
        for t in types:
            try:
                self.type_registry.register_type(
                    category=t["category"],
                    name=t["name"],
                    description=t.get("description"),
                    is_builtin=False,
                    metadata=t.get("metadata"),
                )
                count += 1
            except Exception as e:
                logger.debug(f"Type '{t.get('name')}' registration skipped: {e}")
        return count

    def is_valid_type(self, category: str, name: str) -> bool:
        """Check if a type is valid."""
        return self.type_registry.is_valid(category, name)

    # ═══════════════════════════════════════════════════════════════════════
    # KNOWLEDGE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def store_knowledge(
        self,
        domain: str,
        intent: str,
        action_type: str,
        action_spec: dict,
        owner_actor_id: Optional[str] = None,
        **kwargs,
    ) -> Optional[str]:
        """Store a knowledge node. Returns node_id."""
        try:
            return self.knowledge_manager.store(
                domain=domain,
                intent=intent,
                action_type=action_type,
                action_spec=action_spec,
                owner_actor_id=owner_actor_id,
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"Failed to store knowledge: {e}")
            return None

    def find_knowledge(self, domain: str, intent: str, **kwargs) -> List[dict]:
        """Find knowledge nodes."""
        return self.knowledge_manager.find(domain=domain, intent=intent, **kwargs)

    # ═══════════════════════════════════════════════════════════════════════
    # WORKFLOW OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def create_workflow(self, name: str, steps: list, creator_id: str, **kwargs) -> Optional[str]:
        """Create a workflow. Returns workflow_id."""
        try:
            return self.workflow_manager.create_workflow(
                name=name, steps=steps, creator_id=creator_id, **kwargs
            )
        except Exception as e:
            logger.warning(f"Failed to create workflow: {e}")
            return None

    def execute_workflow(self, workflow_id: str, executor_id: str, input_data: Optional[dict] = None) -> Optional[str]:
        """Start a workflow execution. Returns execution_id."""
        try:
            return self.workflow_manager.start_execution(
                workflow_id=workflow_id, executor_id=executor_id, input_data=input_data
            )
        except Exception as e:
            logger.warning(f"Failed to execute workflow: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LOGGING
    # ═══════════════════════════════════════════════════════════════════════

    def log_event(self, actor_id: str, event_type: str, severity: str = "info", payload: Optional[dict] = None) -> Optional[str]:
        """Log an event to the ontology event store."""
        try:
            from core.ontology_ops import OntologyManager
            from core.ontology_models import Event
            ontology = OntologyManager(self.db)
            event = Event(
                actor_id=actor_id,
                event_type=event_type,
                severity=severity,
                payload=payload or {},
            )
            return ontology.log_event(event)
        except Exception as e:
            logger.warning(f"Failed to log event: {e}")
            return None
