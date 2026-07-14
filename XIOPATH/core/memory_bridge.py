"""
XIOPATH — Memory Bridge (v5.0)
================================
Adapts the new KnowledgeManager to the old MemoryManager interface,
enabling ActorLoop to use the v5.0 knowledge system without changing
its call sites.

The bridge translates:
  MemoryManager.lookup_action()         → KnowledgeManager.find()
  MemoryManager.save_new_action()       → KnowledgeManager.store()
  MemoryManager.promote_client_secondary() → KnowledgeManager.update(tier=...)
  MemoryManager.demote_client_secondary()  → KnowledgeManager.update(tier=...)
  MemoryManager.get_workflow_graph()    → KnowledgeManager.find() with DAG traversal
  MemoryManager.search_intents()        → SQL query on knowledge_nodes
  MemoryManager.get_available_intents() → SQL query on knowledge_nodes
"""
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import text

logger = logging.getLogger("MemoryBridge")


class MemoryBridge:
    """
    Drop-in replacement for MemoryManager in ActorLoop.

    Routes all memory operations through KnowledgeManager (knowledge_nodes table)
    while preserving the exact method signatures the ActorLoop expects.
    Falls back to the legacy MemoryManager if knowledge_nodes table is unavailable.
    """

    def __init__(self, session_id: str, knowledge_manager=None, db=None):
        self.session_id = session_id
        self.km = knowledge_manager
        self.db = db or (knowledge_manager.db if knowledge_manager else None)

        # TTL config (same as MemoryManager)
        self.ttl = {
            "client_secondary": 7,
            "client_primary": 30,
            "server_secondary": 45,
            "server_primary": 90,
        }

    def _get_domain_and_path(self, url: str):
        clean = url.replace("https://", "").replace("http://", "")
        parts = clean.split("/", 1)
        domain = parts[0]
        path = parts[1] if len(parts) > 1 else ""
        if domain.startswith("www."):
            domain = domain[4:]
        return domain, path

    def _generate_context_hash(self, device_type: str, os_name: str, browser: str, viewport: str) -> str:
        key = f"{device_type}_{os_name}_{browser}_{viewport}"
        return hashlib.md5(key.encode()).hexdigest()[:8]

    # ═══════════════════════════════════════════════════════════════════════
    # LOOKUP
    # ═══════════════════════════════════════════════════════════════════════

    def lookup_action(self, url: str, intent: str, context: Dict, max_fallback_tier: int = 2) -> Optional[Dict]:
        """Find a cached action matching domain + intent."""
        if intent.startswith("#"):
            intent = intent[1:]

        domain, path = self._get_domain_and_path(url)

        # Use KnowledgeManager.find() with tier ordering
        results = self.km.find(domain=domain, intent=intent, owner_actor_id=self.session_id, limit=5)

        # Also check public/org nodes
        if not results:
            results = self.km.find(domain=domain, intent=intent, limit=5)

        for node in results:
            # Convert knowledge_node to legacy format
            return self._to_legacy_format(node)

        return None

    def _to_legacy_format(self, node: dict) -> dict:
        """Convert a knowledge_node row to the legacy memory_node dict format."""
        action_spec = node.get("action_spec", "{}")
        if isinstance(action_spec, str):
            action_spec = json.loads(action_spec)

        place_value = node.get("place_value", "{}")
        if isinstance(place_value, str):
            try:
                place_value = json.loads(place_value)
            except (json.JSONDecodeError, TypeError):
                place_value = {}

        # Extract action_type and action_params from action_spec
        steps = action_spec.get("steps", [])
        if steps:
            legacy_action_type = steps[0].get("action", "click")
            legacy_params = {k: v for k, v in steps[0].items() if k != "action"}
        else:
            legacy_action_type = node.get("action_type", "click")
            legacy_params = {}

        face_value = node.get("face_value", "")
        if isinstance(face_value, str):
            try:
                face_value = json.loads(face_value)
            except (json.JSONDecodeError, TypeError):
                face_value = {"description": face_value}

        return {
            "id": node["id"],
            "tier": node.get("tier", "client_secondary"),
            "domain": node.get("domain"),
            "intent": node.get("intent"),
            "action_type": legacy_action_type,
            "action_params": legacy_params,
            "face_value": face_value,
            "place_value": place_value,
            "previous_intent": node.get("previous_intent"),
            "next_nodes": json.loads(node["next_nodes"]) if isinstance(node.get("next_nodes"), str) else node.get("next_nodes", []),
            "visibility": node.get("visibility", "private"),
            "volatility_type": node.get("volatility_type", "static"),
            "bayesian_score": node.get("bayesian_score", 0.5),
            "last_used": node.get("last_used"),
            "status": node.get("status", "active"),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # SAVE
    # ═══════════════════════════════════════════════════════════════════════

    def save_new_action(
        self,
        url: str,
        intent: str,
        face_value: Dict,
        place_value: Dict,
        action_type: str,
        action_params: Dict,
        previous_intent: Optional[str] = None,
        context_hash: str = "default",
        visibility: str = "public",
        volatility_type: str = "static",
        fallback_plugin: str = None,
        output_var: str = None,
        previous_node_id: Optional[str] = None,
        execution_mode: str = "sequential",
    ):
        """Save a new action, converting legacy format to knowledge_node action_spec."""
        if intent.startswith("#"):
            intent = intent[1:]

        domain, path = self._get_domain_and_path(url)

        # Convert legacy action_type + action_params to action_spec
        action_spec = {
            "steps": [{
                "action": action_type,
                **action_params,
            }]
        }

        self.km.store(
            domain=domain,
            intent=intent,
            action_type="browser",
            action_spec=action_spec,
            owner_actor_id=self.session_id,
            face_value=json.dumps(face_value) if isinstance(face_value, dict) else face_value,
            place_value=place_value,
            visibility=visibility,
            volatility_type=volatility_type,
            fallback_plugin=fallback_plugin,
            output_var=output_var,
            execution_mode=execution_mode,
            previous_intent=previous_intent,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # TIER PROMOTION/DEMOTION
    # ═══════════════════════════════════════════════════════════════════════

    def promote_client_secondary(self, node_id: str):
        """Promote a node from client_secondary to client_primary."""
        node = self.km.get(node_id)
        if node and node.get("tier") == "client_secondary":
            self.km.update(node_id, tier="client_primary", promotions=(node.get("promotions", 0) + 1))
            logger.info(f"👑 Promoted {node_id} → client_primary")

    def demote_client_secondary(self, node_id: str):
        """Demote a node's score (keeps tier but lowers bayesian_score)."""
        node = self.km.get(node_id)
        if node:
            new_score = max(0.0, (node.get("bayesian_score", 0.5) - 0.1))
            self.km.update(node_id, bayesian_score=new_score)
            logger.info(f"📉 Demoted {node_id} score → {new_score:.2f}")

    # ═══════════════════════════════════════════════════════════════════════
    # INTENT SEARCH
    # ═══════════════════════════════════════════════════════════════════════

    def get_available_intents(self, url: str) -> List[str]:
        """Get all known intents for a domain."""
        domain, _ = self._get_domain_and_path(url)
        with self.db.SessionLocal() as session:
            rows = session.execute(
                text("SELECT DISTINCT intent FROM knowledge_nodes WHERE domain = :domain AND status = 'active'"),
                {"domain": domain}
            ).fetchall()
            return [r[0] for r in rows]

    def search_intents(self, query: str = "") -> List[Dict]:
        """Search intents across all domains (semantic search placeholder)."""
        with self.db.SessionLocal() as session:
            if query:
                rows = session.execute(
                    text("SELECT DISTINCT domain, intent FROM knowledge_nodes WHERE intent LIKE :q AND status = 'active' LIMIT 20"),
                    {"q": f"%{query}%"}
                ).fetchall()
            else:
                rows = session.execute(
                    text("SELECT DISTINCT domain, intent FROM knowledge_nodes WHERE status = 'active' LIMIT 20")
                ).fetchall()
            return [{"domain": r[0], "intent": r[1]} for r in rows]

    # ═══════════════════════════════════════════════════════════════════════
    # WORKFLOW GRAPH
    # ═══════════════════════════════════════════════════════════════════════

    def get_workflow_graph(self, url: str, start_intent: str, context: Dict, max_fallback_tier: int = 2, max_depth: int = 100) -> Dict:
        """Build a workflow DAG from linked knowledge nodes."""
        domain, path = self._get_domain_and_path(url)
        visited = set()
        nodes = []

        def _traverse(intent: str, depth: int = 0):
            if depth >= max_depth or intent in visited:
                return
            visited.add(intent)

            results = self.km.find(domain=domain, intent=intent, limit=1)
            if not results:
                return

            node = results[0]
            nodes.append(self._to_legacy_format(node))

            next_nodes = node.get("next_nodes", "[]")
            if isinstance(next_nodes, str):
                next_nodes = json.loads(next_nodes)

            for next_intent in next_nodes:
                _traverse(next_intent, depth + 1)

        _traverse(start_intent)

        return {
            "domain": domain,
            "start_intent": start_intent,
            "nodes": nodes,
            "total": len(nodes),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # GC
    # ═══════════════════════════════════════════════════════════════════════

    def run_garbage_collection(self):
        """Delegate GC to KnowledgeManager."""
        return self.km.run_garbage_collection()
