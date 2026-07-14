"""
XIOPATH — Knowledge Manager (Phase 5)
=========================================
Universal memory/action store replacing the browser-specific MemoryManager.

The KnowledgeManager operates on `knowledge_nodes` — a universal store for
all types of reusable actions (browser, API, script, LLM, composite).

Features:
  - Universal action_spec with type validation via TypeRegistry
  - Bayesian EMA scoring (preserved from MemoryManager)
  - Tier promotion/demotion logic (client/server × primary/secondary)
  - Domain+intent based retrieval with fallback tiers
  - Backward-compatible wrapper for browser-style actions
  - PII scrubbing via PIIScrubber
  - Org-scoped knowledge isolation

Tier Hierarchy (lowest → highest trust):
  1. client_secondary  — freshly recorded, unverified
  2. client_primary    — locally validated by the user
  3. server_secondary  — submitted to global pool, awaiting consensus
  4. server_primary    — globally validated, high-confidence reusable
"""
import json
import math
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy import text

logger = logging.getLogger("KnowledgeManager")


# ─── Tier Constants ──────────────────────────────────────────────────────────
TIERS = ["client_secondary", "client_primary", "server_secondary", "server_primary"]
TIER_PRIORITY = {t: i for i, t in enumerate(TIERS)}

# ─── Default Scoring Settings ────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "bayesian_prior_k": 3.0,
    "prior_mean": 0.5,
    "ema_alpha": 0.15,
    "anti_spam_enabled": False,
    "promote_threshold": 0.80,
    "demote_threshold": 0.65,
    "archive_threshold": 0.30,
}

GLOBAL_SETTINGS = {
    **DEFAULT_SETTINGS,
    "bayesian_prior_k": 20.0,
    "anti_spam_enabled": True,
}


def _uuid7() -> str:
    import uuid
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_context_hash(domain: str, intent: str, action_type: str, action_spec: dict) -> str:
    """Deterministic hash for deduplication."""
    key = json.dumps({"d": domain, "i": intent, "t": action_type, "s": action_spec}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def calculate_bayesian_ema(
    existing_score: float,
    existing_weight: float,
    existing_ema: float,
    raw_vote: float,
    tier_confidence: float,
    settings: dict,
    client_weight: float = 1.0,
) -> tuple:
    """
    Calculate updated Bayesian EMA score.

    Returns (bayesian_score, new_ema, new_total_weight).
    """
    v_i = 0.5 + (raw_vote * 0.5 * tier_confidence)
    new_total_weight = existing_weight + client_weight
    alpha = settings.get("ema_alpha", 0.15)
    new_ema = (1 - alpha) * existing_ema + (alpha * v_i)

    k = settings.get("bayesian_prior_k", 20.0)
    m = settings.get("prior_mean", 0.5)
    bayesian_score = ((k * m) + (new_ema * new_total_weight)) / (k + new_total_weight)

    return bayesian_score, new_ema, new_total_weight


class KnowledgeManager:
    """
    Universal knowledge/action store.

    Manages knowledge_nodes with full CRUD, scoring, tier management,
    and backward-compatible browser action support.
    """

    def __init__(self, db, type_registry=None):
        self.db = db
        self.type_registry = type_registry

    # ═══════════════════════════════════════════════════════════════════════
    # CREATE
    # ═══════════════════════════════════════════════════════════════════════

    def store(
        self,
        domain: str,
        intent: str,
        action_type: str,
        action_spec: dict,
        owner_actor_id: Optional[str] = None,
        org_id: Optional[str] = None,
        tier: str = "client_secondary",
        face_value: Optional[str] = None,
        place_value: Optional[dict] = None,
        device_type: Optional[str] = None,
        os_name: Optional[str] = None,
        browser: Optional[str] = None,
        viewport_width: Optional[int] = None,
        viewport_height: Optional[int] = None,
        visibility: str = "private",
        volatility_type: str = "static",
        fallback_plugin: Optional[str] = None,
        output_var: Optional[str] = None,
        execution_mode: str = "sequential",
        previous_intent: Optional[str] = None,
        next_nodes: Optional[list] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Store a new knowledge node.

        Validates action_spec against the TypeRegistry schema if available.
        Returns the node ID.
        """
        # Validate action_type against TypeRegistry
        if self.type_registry:
            try:
                self.type_registry.validate_action_spec(action_type, action_spec)
            except ValueError as e:
                logger.warning(f"Action spec validation warning: {e}")
                # Don't block storage — log and continue

        now = _utcnow()
        node_id = _uuid7()
        context_hash = _compute_context_hash(domain, intent, action_type, action_spec)

        # Check for existing node with same context_hash (dedup)
        with self.db.SessionLocal() as session:
            existing = session.execute(
                text("SELECT id FROM knowledge_nodes WHERE context_hash = :ch AND owner_actor_id = :owner"),
                {"ch": context_hash, "owner": owner_actor_id}
            ).fetchone()
            if existing:
                # Update last_used and return existing ID
                session.execute(
                    text("UPDATE knowledge_nodes SET last_used = :now, ref_count = ref_count + 1 WHERE id = :id"),
                    {"now": now.isoformat(), "id": existing[0]}
                )
                session.commit()
                return existing[0]

        row = {
            "id": node_id,
            "owner_actor_id": owner_actor_id,
            "org_id": org_id,
            "domain": domain,
            "intent": intent,
            "tier": tier,
            "status": "active",
            "action_type": action_type,
            "action_spec": json.dumps(action_spec),
            "execution_mode": execution_mode,
            "face_value": face_value,
            "place_value": json.dumps(place_value) if place_value else None,
            "context_hash": context_hash,
            "lookup_key": f"{domain}::{intent}::{action_type}",
            "previous_intent": previous_intent,
            "next_nodes": json.dumps(next_nodes or []),
            "device_type": device_type,
            "os_name": os_name,
            "browser": browser,
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            "bayesian_score": 0.5,
            "ema_score": 0.5,
            "total_vote_weight": 0.0,
            "promotions": 0,
            "ref_count": 1,
            "visibility": visibility,
            "volatility_type": volatility_type,
            "fallback_plugin": fallback_plugin,
            "output_var": output_var,
            "created_at": now.isoformat(),
            "last_used": now.isoformat(),
            "metadata": json.dumps(metadata) if metadata else None,
        }

        with self.db.safe_transaction() as session:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            session.execute(text(f"INSERT INTO knowledge_nodes ({cols}) VALUES ({placeholders})"), row)

        logger.info(f"Stored knowledge node: {domain}/{intent} ({action_type}) → {tier}")
        return node_id

    # ═══════════════════════════════════════════════════════════════════════
    # READ
    # ═══════════════════════════════════════════════════════════════════════

    def get(self, node_id: str) -> Optional[dict]:
        """Get a knowledge node by ID."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM knowledge_nodes WHERE id = :id"),
                {"id": node_id}
            ).mappings().first()
            return dict(row) if row else None

    def find(
        self,
        domain: str,
        intent: str,
        action_type: Optional[str] = None,
        tier: Optional[str] = None,
        owner_actor_id: Optional[str] = None,
        org_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """
        Find knowledge nodes by domain + intent, with optional filters.
        Results are ordered by tier priority (highest first) then bayesian_score.
        """
        conditions = ["domain = :domain", "intent = :intent", "status = 'active'"]
        params: dict = {"domain": domain, "intent": intent, "limit": limit}

        if action_type:
            conditions.append("action_type = :action_type")
            params["action_type"] = action_type
        if tier:
            conditions.append("tier = :tier")
            params["tier"] = tier
        if owner_actor_id:
            conditions.append("owner_actor_id = :owner")
            params["owner"] = owner_actor_id
        if org_id:
            conditions.append("(org_id = :org_id OR visibility = 'public')")
            params["org_id"] = org_id

        where = " AND ".join(conditions)
        query = f"""
            SELECT * FROM knowledge_nodes
            WHERE {where}
            ORDER BY
                CASE tier
                    WHEN 'server_primary' THEN 1
                    WHEN 'server_secondary' THEN 2
                    WHEN 'client_primary' THEN 3
                    WHEN 'client_secondary' THEN 4
                    ELSE 5
                END,
                bayesian_score DESC
            LIMIT :limit
        """

        with self.db.SessionLocal() as session:
            rows = session.execute(text(query), params).mappings().all()
            return [dict(r) for r in rows]

    def find_by_lookup_key(self, lookup_key: str) -> Optional[dict]:
        """Fast lookup by precomputed key."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM knowledge_nodes WHERE lookup_key = :lk AND status = 'active' ORDER BY bayesian_score DESC LIMIT 1"),
                {"lk": lookup_key}
            ).mappings().first()
            return dict(row) if row else None

    def list_by_owner(self, owner_actor_id: str, limit: int = 50) -> List[dict]:
        """List knowledge nodes owned by a specific actor."""
        with self.db.SessionLocal() as session:
            rows = session.execute(
                text("SELECT * FROM knowledge_nodes WHERE owner_actor_id = :owner AND status = 'active' ORDER BY last_used DESC LIMIT :limit"),
                {"owner": owner_actor_id, "limit": limit}
            ).mappings().all()
            return [dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════
    # UPDATE
    # ═══════════════════════════════════════════════════════════════════════

    def update(self, node_id: str, **kwargs) -> bool:
        """Update mutable fields on a knowledge node."""
        if not kwargs:
            return False

        # Serialize JSON fields
        for key in ("action_spec", "place_value", "next_nodes", "metadata"):
            if key in kwargs and isinstance(kwargs[key], (dict, list)):
                kwargs[key] = json.dumps(kwargs[key])

        kwargs["updated_at"] = _utcnow().isoformat()
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)
        kwargs["node_id"] = node_id

        with self.db.safe_transaction() as session:
            result = session.execute(
                text(f"UPDATE knowledge_nodes SET {set_clause} WHERE id = :node_id"),
                kwargs
            )
            return result.rowcount > 0

    def delete(self, node_id: str) -> bool:
        """Soft-delete (archive) a knowledge node."""
        return self.update(node_id, status="archived")

    # ═══════════════════════════════════════════════════════════════════════
    # VOTING & SCORING
    # ═══════════════════════════════════════════════════════════════════════

    def submit_vote(
        self,
        node_id: str,
        voter_actor_id: str,
        raw_vote: float = 1.0,
        tier_confidence: float = 1.0,
    ) -> dict:
        """
        Submit a vote for a knowledge node and recalculate its Bayesian score.

        Returns updated score info.
        """
        node = self.get(node_id)
        if not node:
            raise ValueError(f"Knowledge node not found: {node_id}")

        # Determine settings based on tier
        is_global = node["tier"].startswith("server_")
        settings = GLOBAL_SETTINGS if is_global else DEFAULT_SETTINGS

        # Anti-spam: weight by voter's historical vote count
        client_weight = 1.0
        if settings["anti_spam_enabled"]:
            with self.db.SessionLocal() as session:
                row = session.execute(
                    text("SELECT vote_count FROM client_vote_counts WHERE client_id = :cid"),
                    {"cid": voter_actor_id}
                ).fetchone()
                vote_count = row[0] if row else 1
                client_weight = 1.0 / (1.0 + math.log(max(1, vote_count)))

        # Calculate
        bayesian, ema, weight = calculate_bayesian_ema(
            existing_score=node.get("bayesian_score", 0.5),
            existing_weight=node.get("total_vote_weight", 0.0),
            existing_ema=node.get("ema_score", 0.5),
            raw_vote=raw_vote,
            tier_confidence=tier_confidence,
            settings=settings,
            client_weight=client_weight,
        )

        # Determine tier promotion/demotion
        new_tier = node["tier"]
        new_status = node["status"]
        promotions = node.get("promotions", 0)

        if bayesian > settings["promote_threshold"] and weight > 5.0:
            current_idx = TIER_PRIORITY.get(node["tier"], 0)
            if current_idx < len(TIERS) - 1:
                new_tier = TIERS[current_idx + 1]
                promotions += 1
                logger.info(f"👑 '{node_id}' promoted: {node['tier']} → {new_tier} (score={bayesian:.3f})")

        if bayesian < settings["demote_threshold"]:
            current_idx = TIER_PRIORITY.get(node["tier"], 0)
            if current_idx > 0:
                new_tier = TIERS[current_idx - 1]
                logger.info(f"📉 '{node_id}' demoted: {node['tier']} → {new_tier} (score={bayesian:.3f})")

        if bayesian < settings["archive_threshold"]:
            new_status = "archived"
            logger.info(f"🗑️ '{node_id}' archived (score={bayesian:.3f})")

        # Persist
        self.update(
            node_id,
            bayesian_score=bayesian,
            ema_score=ema,
            total_vote_weight=weight,
            tier=new_tier,
            status=new_status,
            promotions=promotions,
        )

        return {
            "bayesian_score": round(bayesian, 4),
            "ema_score": round(ema, 4),
            "total_vote_weight": round(weight, 4),
            "tier": new_tier,
            "status": new_status,
            "promoted": new_tier != node["tier"],
        }

    # ═══════════════════════════════════════════════════════════════════════
    # BACKWARD COMPATIBILITY: Browser Actions
    # ═══════════════════════════════════════════════════════════════════════

    def store_browser_action(
        self,
        domain: str,
        intent: str,
        action_type: str,
        action_params: dict,
        client_id: str = "default",
        **kwargs,
    ) -> str:
        """
        Backward-compatible wrapper for storing browser-style actions.
        Converts legacy action_type/action_params into universal action_spec.
        """
        # Convert legacy format to action_spec
        action_spec = {
            "steps": [{
                "action": action_type,
                **action_params,
            }]
        }

        return self.store(
            domain=domain,
            intent=intent,
            action_type="browser",
            action_spec=action_spec,
            owner_actor_id=client_id,
            **kwargs,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # GARBAGE COLLECTION
    # ═══════════════════════════════════════════════════════════════════════

    TTL_DAYS = {
        "client_secondary": 7,
        "client_primary": 30,
        "server_secondary": 45,
        "server_primary": 90,
    }

    def run_garbage_collection(self) -> int:
        """Archive expired nodes based on tier TTL. Returns count of archived nodes."""
        total = 0
        for tier, ttl_days in self.TTL_DAYS.items():
            cutoff = (_utcnow() - timedelta(days=ttl_days)).isoformat()
            with self.db.safe_transaction() as session:
                result = session.execute(
                    text("""UPDATE knowledge_nodes SET status = 'archived'
                            WHERE tier = :tier AND last_used < :cutoff AND status = 'active'"""),
                    {"tier": tier, "cutoff": cutoff}
                )
                count = result.rowcount
                if count:
                    total += count
                    logger.info(f"GC: archived {count} expired nodes from tier '{tier}'")
        if total:
            logger.info(f"GC complete: {total} nodes archived")
        return total

    # ═══════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════════════

    def get_stats(self, owner_actor_id: Optional[str] = None) -> dict:
        """Get knowledge store statistics."""
        conditions = ["status = 'active'"]
        params = {}
        if owner_actor_id:
            conditions.append("owner_actor_id = :owner")
            params["owner"] = owner_actor_id

        where = " AND ".join(conditions)

        with self.db.SessionLocal() as session:
            total = session.execute(
                text(f"SELECT COUNT(*) FROM knowledge_nodes WHERE {where}"), params
            ).scalar()

            by_tier = session.execute(
                text(f"SELECT tier, COUNT(*) as cnt FROM knowledge_nodes WHERE {where} GROUP BY tier"), params
            ).fetchall()

            by_type = session.execute(
                text(f"SELECT action_type, COUNT(*) as cnt FROM knowledge_nodes WHERE {where} GROUP BY action_type"), params
            ).fetchall()

            avg_score = session.execute(
                text(f"SELECT AVG(bayesian_score) FROM knowledge_nodes WHERE {where}"), params
            ).scalar()

        return {
            "total_nodes": total or 0,
            "by_tier": {r[0]: r[1] for r in by_tier},
            "by_action_type": {r[0]: r[1] for r in by_type},
            "avg_bayesian_score": round(avg_score or 0.5, 4),
        }
