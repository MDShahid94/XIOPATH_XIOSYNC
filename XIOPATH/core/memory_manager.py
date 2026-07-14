import math
import hashlib
import json
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import chromadb

logger = logging.getLogger(__name__)

from core.database import DatabaseManager
from core.pii_scrubber import PIIScrubber

def calculate_bayesian_ema(existing_node, client_id, raw_vote, tier_confidence, settings, get_vote_count_fn=None):
    v_i = 0.5 + (raw_vote * 0.5 * tier_confidence)
    w_client = 1.0
    
    if settings.get("anti_spam_enabled", False) and get_vote_count_fn:
        client_vote_count = get_vote_count_fn(existing_node["id"], client_id)
        w_client = 1.0 / (1.0 + math.log(max(1, client_vote_count)))
        
    new_total_weight = existing_node.get("total_vote_weight", 0.0) + w_client
    ema = existing_node.get("ema_score", settings.get("prior_mean", 0.5))
    alpha = settings.get("ema_alpha", 0.15)
    
    new_ema = (1 - alpha) * ema + (alpha * v_i)
    
    k = settings.get("bayesian_prior_k", 20.0)
    m = settings.get("prior_mean", 0.5)
    
    bayesian_score = ((k * m) + (new_ema * new_total_weight)) / (k + new_total_weight)
    
    return bayesian_score, new_ema, new_total_weight

def load_settings(tier_type="local"):
    settings_path = Path(f"core/{tier_type}_memory_settings.json")
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            return json.load(f)
    return {
        "bayesian_prior_k": 3.0 if tier_type == "local" else 20.0,
        "prior_mean": 0.5,
        "ema_alpha": 0.15,
        "anti_spam_enabled": tier_type == "global",
        "promote_threshold": 0.80,
        "demote_threshold": 0.65,
        "archive_threshold": 0.30
    }

class ServerMemoryAPI:
    """
    Simulated API Layer for Server-side memory management.
    In production, this would be a standalone FastAPI/gRPC microservice.
    """
    def __init__(self, db: DatabaseManager):
        self.db = db

    def submit_vote(self, domain: str, node_id: str, action_data: Dict, client_id: str, raw_vote: float = 1.0, tier_confidence: float = 1.0):
        """
        Endpoint: POST /api/memory/vote
        Receives a vote from a client and updates the Global Consensus Engine.
        """
        scrubbed_place_value = PIIScrubber.redact_place_value(action_data.get("place_value", {}))
        action_data["place_value"] = scrubbed_place_value

        existing = self.db.get_node(node_id)
        if not existing:
            # First time seeing this node, insert it as server_secondary
            self.db.upsert_node(
                node_id=node_id, tier="server_secondary", domain=domain, intent=action_data["intent"],
                device_type=action_data.get("device_type"), os_name=action_data.get("os_name"),
                browser=action_data.get("browser"), viewport_width=action_data.get("viewport_width"),
                viewport_height=action_data.get("viewport_height"), visibility=action_data.get("visibility", "public"),
                face_value=action_data["face_value"], place_value=scrubbed_place_value,
                action_type=action_data["action_type"], action_params=action_data["action_params"],
                previous_intent=action_data.get("previous_intent"), next_nodes=action_data.get("next_nodes", []),
                promotions=0, client_id=client_id, volatility_type=action_data.get("volatility_type", "static"),
                fallback_plugin=action_data.get("fallback_plugin"), output_var=action_data.get("output_var"),
                execution_mode=action_data.get("execution_mode", "sequential"),
                context_hash=action_data.get("context_hash", "default"), ref_count=0,
                bayesian_score=0.5, ema_score=0.5, total_vote_weight=0.0, status="ACTIVE"
            )
            existing = self.db.get_node(node_id)
            logger.info(f"'{node_id}' mapped to [GS] Global Secondary.")
        
        # Record the vote to track client participation count (for anti-spam)
        self.db.record_vote(node_id, client_id)
        
        # Calculate new Bayesian EMA
        settings = load_settings("global")
        def get_vote_count(nid, cid):
            """Return the client's total historical vote count (E-12: across ALL nodes)."""
            with self.db.SessionLocal() as session:
                from sqlalchemy import text
                row = session.execute(
                    text("SELECT vote_count FROM client_vote_counts WHERE client_id = :cid"),
                    {"cid": cid}
                ).fetchone()
                return row[0] if row else 1

        bayesian, ema, weight = calculate_bayesian_ema(existing, client_id, raw_vote, tier_confidence, settings, get_vote_count)
        
        # Determine new tier based on score
        new_tier = existing["tier"]
        new_status = existing["status"]
        
        if bayesian > settings["promote_threshold"] and weight > 5.0:
            new_tier = "server_primary"
        elif bayesian < settings["demote_threshold"]:
            new_tier = "server_secondary"
            
        if bayesian < settings["archive_threshold"]:
            new_status = "ARCHIVED"
            
        if new_tier != existing["tier"] or new_status != existing["status"]:
            tag = "👑" if new_tier == "server_primary" else "📉"
            tag = "🗑️" if new_status == "ARCHIVED" else tag
            logger.info(f"{tag} '{node_id}' state changed: Tier={new_tier}, Status={new_status}, Score={bayesian:.2f}")

        # Update node
        self.db.upsert_node(
            node_id=existing["id"], tier=new_tier, domain=existing["domain"], intent=existing["intent"],
            device_type=existing["device_type"], os_name=existing["os_name"], browser=existing["browser"],
            viewport_width=existing["viewport_width"], viewport_height=existing["viewport_height"],
            visibility=existing["visibility"], face_value=existing["face_value"], place_value=existing["place_value"],
            action_type=existing["action_type"], action_params=existing["action_params"],
            previous_intent=existing["previous_intent"], next_nodes=existing["next_nodes"],
            promotions=existing["promotions"], client_id=existing["client_id"],
            volatility_type=existing["volatility_type"], fallback_plugin=existing["fallback_plugin"],
            output_var=existing["output_var"], execution_mode=existing["execution_mode"],
            context_hash=existing["context_hash"], ref_count=existing["ref_count"],
            bayesian_score=bayesian, ema_score=ema, total_vote_weight=weight, status=new_status
        )


from core.sync_worker import SyncWorker

class MemoryManager:
    """
    Tiered Memory Manager (Client-side).
    Orchestrates the 5 levels of Memory and interacts with the Local SQLite/Vector DBs,
    as well as the global Federated Sync Worker.
    """
    def __init__(self, session_id: str = "default_client", memory_dir: str = "data", db=None, chroma_client=None, start_sync: bool = True):
        self.session_id = session_id
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self.db = db if db else DatabaseManager(self.memory_dir / "memory.db")
        
        # Start background sync worker
        if start_sync:
            self.sync_worker = SyncWorker(self)
            self.sync_worker.start()
        else:
            self.sync_worker = None
        
        self.vector_dir = self.memory_dir / "vector_db"
        self.vector_dir.mkdir(parents=True, exist_ok=True)
            
        self.chroma_client = chroma_client if chroma_client else chromadb.PersistentClient(path=str(self.vector_dir))
        self.col_lp = self.chroma_client.get_or_create_collection(name="client_primary")
        self.col_ls = self.chroma_client.get_or_create_collection(name="client_secondary")
        self.col_gp = self.chroma_client.get_or_create_collection(name="server_primary")
        self.col_gs = self.chroma_client.get_or_create_collection(name="server_secondary")
        
        # W.2: Semantic intent indexer for vector search
        from core.intent_indexer import IntentIndexer
        self.intent_indexer = IntentIndexer(self.chroma_client, self.db)

        self.ttl = {
            "client_secondary": 7,
            "client_primary": 30,
            "server_secondary": 45,
            "server_primary": 90
        }

    def run_garbage_collection(self):
        """
        Runs periodic Garbage Collection (TTL check).
        E-11: Uses SQL-level filtering instead of full table scan.
        """
        total_removed = 0
        for tier, ttl_days in self.ttl.items():
            cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
            count = self.db.delete_expired_nodes(cutoff)
            if count:
                total_removed += count
                logger.info(f"GC: removed/archived {count} expired nodes from tier '{tier}'")
        if total_removed:
            logger.info(f"GC complete: {total_removed} nodes processed")

    def _get_domain_and_path(self, url: str) -> (str, str):
        clean = url.replace("https://", "").replace("http://", "")
        parts = clean.split("/", 1)
        domain = parts[0]
        path = parts[1] if len(parts) > 1 else ""
        if domain.startswith("www."):
            domain = domain[4:]
        return domain, path

    def _generate_context_hash(self, device_type: str, os_name: str, browser: str, viewport: str) -> str:
        s = f"{device_type}|{os_name}|{browser}|{viewport}"
        return hashlib.sha256(s.encode()).hexdigest()[:16]

    def _is_expired(self, last_used: str, tier: str) -> bool:
        try:
            last_dt = datetime.fromisoformat(last_used)
            ttl_days = self.ttl.get(tier, 7)
            return datetime.now() > last_dt + timedelta(days=ttl_days)
        except Exception:
            return False

    def get_available_intents(self, url: str) -> List[str]:
        # Extract domain from url (simplified)
        domain = url.split("/")[2] if "://" in url else url.split("/")[0]
        return self.db.get_available_intents(domain)

    def lookup_action(self, url: str, intent: str, context: Dict, max_fallback_tier: int = 2) -> Optional[Dict]:
        if intent.startswith("#"):
            intent = intent[1:] 
            
        domain, path = self._get_domain_and_path(url)
        
        # 5-Tier Cascading Fallback Search
        nodes = self.db.get_node_fallback(domain, intent, context, max_fallback_tier, client_id=self.session_id)
        
        for node in nodes:
            if not self._is_expired(node["last_used"], node["tier"]):
                # Reset TTL for the matched node while preserving all Bayesian state
                node["last_used"] = datetime.now().isoformat()
                self.db.upsert_node(
                    node["id"], node["tier"], node["domain"], node["intent"], 
                    node["device_type"], node["os_name"], node["browser"], node["viewport_width"], node["viewport_height"],
                    node["visibility"], node["face_value"], node["place_value"], node["action_type"],
                    node["action_params"], node["previous_intent"], node["next_nodes"], node["promotions"],
                    node["client_id"], node["last_used"],
                    volatility_type=node.get("volatility_type", "static"),
                    fallback_plugin=node.get("fallback_plugin"),
                    output_var=node.get("output_var"),
                    execution_mode=node.get("execution_mode", "sequential"),
                    context_hash=node.get("context_hash", "default"),
                    ref_count=node.get("ref_count", 0),
                    bayesian_score=node.get("bayesian_score", 0.5),
                    ema_score=node.get("ema_score", 0.5),
                    total_vote_weight=node.get("total_vote_weight", 0.0),
                    status=node.get("status", "ACTIVE")
                )
                return node
                
        return None

    def semantic_lookup(self, url: str, query: str, context_hash: str = "default", top_k: int = 3) -> List[Dict]:
        domain, path = self._get_domain_and_path(url)
        results = []
        
        collections = [
            (self.col_lp, "[LP] Local Primary"),
            (self.col_gp, "[GP] Global Primary"),
            (self.col_ls, "[LS] Local Secondary"),
            (self.col_gs, "[GS] Global Secondary")
        ]
        
        for col, tier_tag in collections:
            if len(results) >= top_k:
                break
                
            res = col.query(
                query_texts=[query],
                n_results=top_k - len(results),
                where={"$and": [{"domain": domain}, {"context_hash": context_hash}]}
            )
            
            if res and res.get('metadatas') and len(res['metadatas']) > 0 and len(res['metadatas'][0]) > 0:
                for i in range(len(res['metadatas'][0])):
                    meta = res['metadatas'][0][i]
                    results.append({
                        "tier": tier_tag,
                        "intent": meta["intent"],
                        "face_value": json.loads(meta.get("face_value", "{}")),
                        "place_value": json.loads(meta["place_value"]),
                        "action_type": meta["action_type"],
                        "distance": res['distances'][0][i] if 'distances' in res and res['distances'] else 0
                    })
                    
        return results

    def save_new_action(self, url: str, intent: str, face_value: Dict, place_value: Dict, 
                        action_type: str, action_params: Dict, previous_intent: Optional[str] = None, 
                        context_hash: str = "default", visibility: str = "public",
                        volatility_type: str = "static", fallback_plugin: str = None, output_var: str = None,
                        previous_node_id: Optional[str] = None, execution_mode: str = "sequential"):
        if intent.startswith("#"):
            intent = intent[1:]
            
        domain, path = self._get_domain_and_path(url)
        import time
        timestamp = int(time.time() * 1000)
        # Unique storage key (with timestamp for deduplication)
        memory_key = f"{self.session_id}_{intent}_{domain}_{context_hash}_{timestamp}"
        # Stable lookup key (without timestamp for graph linking — E-09)
        lookup_key = f"{self.session_id}_{intent}_{domain}_{context_hash}"
        
        existing = self.db.get_node(memory_key)
        next_nodes = existing.get("next_nodes", []) if existing else []
        promotions = existing.get("promotions", 0) if existing else 0
        
        # Ensure Deterministic I/O Data Scopes (Quest 2)
        source_type = "none"
        if fallback_plugin:
            source_type = "runtime_plugin"
        elif action_params:
            if action_params.get('text', '').startswith('vault://'):
                source_type = "vault"
            elif '{{' in action_params.get('text', ''):
                source_type = "workflow_var"
            else:
                source_type = "literal"
                
        destination_type = "workflow_var" if output_var else "none"
        
        # Semantic Input/Output (FACE Value Scope)
        face_value["semantic_input"] = {
            "volatility": volatility_type,
            "requires_data": len(action_params) > 0 or fallback_plugin is not None,
            "execution_mode": execution_mode
        }
        face_value["semantic_output"] = {
            "produces_data": action_type == "extract_data" or output_var is not None
        }
        
        # Structural Input/Output (PLACE Value Scope)
        place_value["structural_input"] = {
            "source_type": source_type,
            "plugin_name": fallback_plugin,
            "params": action_params
        }
        place_value["structural_output"] = {
            "destination_type": destination_type,
            "destination_key": output_var
        }
        
        self.db.upsert_node(
            node_id=memory_key,
            tier="client_secondary",
            domain=domain,
            intent=intent,
            device_type="desktop",
            os_name="macintel",
            browser="chromium",
            viewport_width=1280,
            viewport_height=800,
            visibility=visibility,
            face_value=face_value,
            place_value=place_value,
            action_type=action_type,
            action_params=action_params,
            previous_intent=previous_intent,
            next_nodes=next_nodes,
            promotions=promotions,
            client_id=self.session_id,
            volatility_type=volatility_type,
            fallback_plugin=fallback_plugin,
            output_var=output_var,
            execution_mode=execution_mode,
            context_hash=context_hash,
            ref_count=existing.get("ref_count", 0) if existing else 0,
            bayesian_score=existing.get("bayesian_score", 0.5) if existing else 0.5,
            ema_score=existing.get("ema_score", 0.5) if existing else 0.5,
            total_vote_weight=existing.get("total_vote_weight", 0.0) if existing else 0.0,
            status=existing.get("status", "ACTIVE") if existing else "ACTIVE",
            lookup_key=lookup_key,
        )
        
        # Link from previous node
        if previous_node_id:
            prev_node = self.db.get_node(previous_node_id)
            if prev_node:
                next_list = prev_node.get("next_nodes", [])
                if memory_key not in [n['id'] if isinstance(n, dict) else n for n in next_list]:
                    next_list.append({"intent": intent, "id": memory_key})
                    self.db.upsert_node(
                        node_id=previous_node_id,
                        tier=prev_node.get("tier", "client_secondary"),
                        domain=prev_node.get("domain"),
                        intent=prev_node.get("intent"),
                        device_type=prev_node.get("device_type"),
                        os_name=prev_node.get("os_name"),
                        browser=prev_node.get("browser"),
                        viewport_width=prev_node.get("viewport_width", 1280),
                        viewport_height=prev_node.get("viewport_height", 800),
                        visibility=prev_node.get("visibility", "public"),
                        face_value=prev_node.get("face_value"),
                        place_value=prev_node.get("place_value"),
                        action_type=prev_node.get("action_type"),
                        action_params=prev_node.get("action_params"),
                        previous_intent=prev_node.get("previous_intent"),
                        next_nodes=next_list,
                        promotions=prev_node.get("promotions", 0),
                        client_id=prev_node.get("client_id", self.session_id),
                        last_used=prev_node.get("last_used"),
                        volatility_type=prev_node.get("volatility_type", "static"),
                        fallback_plugin=prev_node.get("fallback_plugin"),
                        output_var=prev_node.get("output_var"),
                        execution_mode=prev_node.get("execution_mode", "sequential"),
                        context_hash=prev_node.get("context_hash", "default"),
                        ref_count=prev_node.get("ref_count", 0),
                        bayesian_score=prev_node.get("bayesian_score", 0.5),
                        ema_score=prev_node.get("ema_score", 0.5),
                        total_vote_weight=prev_node.get("total_vote_weight", 0.0),
                        status=prev_node.get("status", "ACTIVE")
                    )

        # Save to Vector DB
        doc = f"Intent: {intent}. Action: {action_type} on {face_value.get('description', '')}. Text: {face_value.get('text', '')}. Input Source: {source_type}. Output Destination: {destination_type}."
        meta = {
            "domain": domain, "intent": intent, "path": path, "context_hash": context_hash,
            "face_value": json.dumps(face_value), "place_value": json.dumps(place_value),
            "action_type": action_type, "visibility": visibility
        }
        self.col_ls.upsert(ids=[memory_key], documents=[doc], metadatas=[meta])
        logger.info(f"Saved action '{intent}' to [LS] Local Secondary.")
        
        # E-09: Link using stable lookup_key (not timestamped memory_key)
        if previous_intent and not previous_node_id:
            if "@" in previous_intent:
                prev_intent_name, prev_domain = previous_intent.split("@", 1)
                prev_lookup = f"{self.session_id}_{prev_intent_name}_{prev_domain}_{context_hash}"
            else:
                prev_lookup = f"{self.session_id}_{previous_intent}_{domain}_{context_hash}"
            self._link_previous_intent_by_lookup(prev_lookup, intent, domain, memory_key)
        
        # W.2: Index intent for semantic vector search
        try:
            self.intent_indexer.index_intent(intent, domain=domain, tier="client_secondary")
        except Exception as e:
            logger.debug(f"Intent indexing failed (non-critical): {e}")
            
        return memory_key

    def _link_previous_intent_by_lookup(self, prev_lookup_key: str, current_intent: str, domain: str, current_node_id: str):
        """Link using lookup_key instead of exact node_id (fixes E-09)."""
        node = self.db.get_node_by_lookup_key(prev_lookup_key)
        if node:
            next_list = node.get("next_nodes", [])
            link_entry = {"intent": current_intent, "id": current_node_id}
            existing_ids = [n["id"] if isinstance(n, dict) else n for n in next_list]
            if current_node_id not in existing_ids:
                next_list.append(link_entry)
                # E-08: Use update_node_fields instead of full 29-arg upsert
                self.db.update_node_fields(node["id"], next_nodes=next_list)
        else:
            logger.debug(f"No previous node found for lookup_key: {prev_lookup_key}")

    def submit_local_vote(self, node_id: str, raw_vote: float = 1.0, tier_confidence: float = 1.0):
        node = self.db.get_node(node_id)
        if not node:
            return
            
        settings = load_settings("local")
        bayesian, ema, weight = calculate_bayesian_ema(node, self.session_id, raw_vote, tier_confidence, settings, None)
        
        node["last_used"] = datetime.now().isoformat()
        
        new_tier = node["tier"]
        new_status = node["status"]
        
        if bayesian > settings["promote_threshold"]:
            if new_tier == "client_secondary":
                new_tier = "client_primary"
                v_data = self.col_ls.get(ids=[node_id], include=['documents', 'metadatas'])
                if v_data and v_data.get('ids'):
                    self.col_lp.upsert(ids=[node_id], documents=v_data['documents'], metadatas=v_data['metadatas'])
                    self.col_ls.delete(ids=[node_id])
                logger.info(f"'{node['intent']}' elevated to [LP] Local Primary.")
                
                # Push to global sync if public
                if node["visibility"] == "public" and "localhost" not in node["domain"]:
                    node_data = {
                        "id": node_id, "domain": node["domain"], "intent": node["intent"],
                        "action_type": node["action_type"], "action_params": node["action_params"],
                        "face_value": node["face_value"], "place_value": node["place_value"],
                        "visibility": node["visibility"], "previous_intent": node["previous_intent"],
                        "next_nodes": node["next_nodes"]
                    }
                    if self.sync_worker:
                        self.sync_worker.queue_push(node_data)
                        
        elif bayesian < settings["demote_threshold"]:
            if new_tier == "client_primary":
                new_tier = "client_secondary"
                v_data = self.col_lp.get(ids=[node_id], include=['documents', 'metadatas'])
                if v_data and v_data.get('ids'):
                    self.col_ls.upsert(ids=[node_id], documents=v_data['documents'], metadatas=v_data['metadatas'])
                    self.col_lp.delete(ids=[node_id])
                logger.info(f"'{node['intent']}' demoted to [LS] Local Secondary.")
                
        if bayesian < settings["archive_threshold"]:
            if node["ref_count"] == 0:
                self.db.delete_node(node_id)
                try:
                    self.col_ls.delete(ids=[node_id])
                except Exception: pass
                try:
                    self.col_lp.delete(ids=[node_id])
                except Exception: pass
                logger.info(f"'{node['intent']}' deleted due to failed validation (ref_count=0).")
                return
            else:
                new_status = "ARCHIVED"
                logger.warning(f"'{node['intent']}' archived due to failed validation (ref_count={node['ref_count']}).")

        self.db.upsert_node(
            node_id=node["id"], tier=new_tier, domain=node["domain"], intent=node["intent"],
            device_type=node["device_type"], os_name=node["os_name"], browser=node["browser"],
            viewport_width=node["viewport_width"], viewport_height=node["viewport_height"],
            visibility=node["visibility"], face_value=node["face_value"], place_value=node["place_value"],
            action_type=node["action_type"], action_params=node["action_params"],
            previous_intent=node["previous_intent"], next_nodes=node["next_nodes"],
            promotions=node["promotions"], client_id=node["client_id"],
            volatility_type=node.get("volatility_type", "static"), fallback_plugin=node.get("fallback_plugin"),
            output_var=node.get("output_var"), execution_mode=node.get("execution_mode", "sequential"),
            context_hash=node.get("context_hash", "default"), ref_count=node.get("ref_count", 0),
            bayesian_score=bayesian, ema_score=ema, total_vote_weight=weight, status=new_status
        )

    def promote_client_secondary(self, node_id: str):
        """Convenience wrapper: casts a positive vote to promote a node in the local tier hierarchy."""
        self.submit_local_vote(node_id, raw_vote=1.0, tier_confidence=1.0)

    def demote_client_secondary(self, node_id: str):
        """Convenience wrapper: casts a negative vote to demote a node in the local tier hierarchy."""
        self.submit_local_vote(node_id, raw_vote=-1.0, tier_confidence=1.0)

    def update_axes_stability(self, node_id: str, winning_strategy: str = None):
        """AxesXPath stability auto-repair.

        When an axes_xpath strategy succeeds during element resolution,
        boost its stability score. Decay scores of strategies that didn't win.
        Over time, the system learns which relational strategies work best per site.

        Args:
            node_id: The memory node ID.
            winning_strategy: The strategy name that resolved successfully
                              (e.g., 'ancestor_id', 'sibling_text'). If None, all are decayed.
        """
        node = self.db.get_node(node_id)
        if not node:
            return

        place_value = node.get("place_value", {})
        axes = place_value.get("axes_xpath", [])
        if not axes or not isinstance(axes, list):
            return

        changed = False
        for axe in axes:
            if not isinstance(axe, dict):
                continue
            if winning_strategy and axe.get("strategy") == winning_strategy:
                old = axe.get("stability", 0.5)
                axe["stability"] = min(1.0, old + 0.02)
                changed = True
            else:
                old = axe.get("stability", 0.5)
                axe["stability"] = max(0.0, old - 0.01)
                changed = True

        if changed:
            # Re-sort by stability (highest first)
            axes.sort(key=lambda a: a.get("stability", 0), reverse=True)
            place_value["axes_xpath"] = axes
            self.db.update_node_fields(node_id, place_value=place_value)

    def get_workflow_graph(self, url: str, start_intent: str, context: Dict, max_fallback_tier: int = 2, max_depth: int = 100) -> Dict:
        if start_intent.startswith("#"):
            start_intent = start_intent[1:]
            
        domain, path = self._get_domain_and_path(url)
        visited = set()
        
        def traverse(intent: str, depth: int) -> Optional[Dict]:
            if depth > max_depth:
                logger.warning(f"get_workflow_graph: max_depth {max_depth} exceeded at intent '{intent}'")
                return None
            if intent in visited:
                logger.warning(f"get_workflow_graph: cycle detected at intent '{intent}'")
                return None
            visited.add(intent)
            
            if "@" in intent:
                actual_intent, next_domain = intent.split("@", 1)
                action = self.lookup_action(f"https://{next_domain}", actual_intent, context, max_fallback_tier)
                save_intent = actual_intent
            else:
                action = self.lookup_action(url, intent, context, max_fallback_tier)
                save_intent = intent
                
            logger.debug(f"lookup_action for {intent} returned: {action is not None}")
            if not action:
                return None
                
            node_data = {
                "id": action.get("id"),
                "intent": save_intent,
                "domain": action.get("domain"),
                "tier": action.get("tier"),
                "face_value": action.get("face_value"),
                "place_value": action.get("place_value"),
                "action_type": action.get("action_type"),
                "action_params": action.get("action_params"),
                "device_type": action.get("device_type"),
                "os_name": action.get("os_name"),
                "browser": action.get("browser"),
                "viewport_width": action.get("viewport_width"),
                "viewport_height": action.get("viewport_height"),
                "visibility": action.get("visibility", 1),
                "previous_intent": action.get("previous_intent"),
                "volatility_type": action.get("volatility_type", "static"),
                "fallback_plugin": action.get("fallback_plugin"),
                "output_var": action.get("output_var"),
                "next_nodes": []
            }
            
            for next_entry in action.get("next_nodes", []):
                # next_nodes can be strings ("intent") or dicts ({"intent": "...", "id": "..."})
                if isinstance(next_entry, dict):
                    next_intent = next_entry.get("intent", "")
                else:
                    next_intent = next_entry
                if not next_intent:
                    continue
                next_branch = traverse(next_intent, depth + 1)
                if next_branch:
                    node_data["next_nodes"].append(next_branch)
                    
            return node_data
            
        return traverse(start_intent, 0)

    def search_intents(self, query: str = "") -> List[Dict]:
        """
        W.2: Semantic intent search — ChromaDB vector similarity first, SQL LIKE fallback.
        Returns a deduplicated list of workflows grouped by intent, 
        ordered strictly by: client_primary -> client_secondary -> server_primary -> server_secondary
        """
        # W.2 Tier 1: Try semantic vector search via IntentIndexer
        try:
            vector_results = self.intent_indexer.search(query, n_results=10)
            if vector_results:
                logger.debug(f"search_intents: Vector search returned {len(vector_results)} results for '{query}'")
                return vector_results
        except Exception as e:
            logger.debug(f"search_intents: Vector search failed, falling back to SQL: {e}")
        
        # W.2 Tier 2: Fallback to SQL LIKE search (original logic)
        with self.db.SessionLocal() as session:
            from sqlalchemy import text
            sql = text("""
                SELECT intent, tier, domain 
                FROM memory_nodes 
                WHERE intent LIKE :query 
                  AND previous_intent IS NULL 
                  AND (tier IN ('server_primary', 'server_secondary') OR (tier LIKE 'client_%' AND client_id = :client_id))
            """)
            rows = session.execute(sql, {"query": f"%{query}%", "client_id": self.session_id}).fetchall()
            
            tier_weights = {
                "client_primary": 1,
                "client_secondary": 2,
                "server_primary": 3,
                "server_secondary": 4
            }
            
            results = []
            for r in rows:
                results.append({
                    "intent": r.intent,
                    "tier": r.tier,
                    "domain": r.domain,
                    "weight": tier_weights.get(r.tier, 99)
                })
                
            results.sort(key=lambda x: x["weight"])
            
            seen = set()
            deduped = []
            for r in results:
                if r["intent"] not in seen:
                    seen.add(r["intent"])
                    deduped.append({"intent": r["intent"], "tier": r["tier"], "domain": r["domain"]})
                    
            return deduped
