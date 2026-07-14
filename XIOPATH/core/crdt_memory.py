"""
XIOPATH — CRDT Memory Graph Merger (Phase X)
==============================================
Provides Conflict-Free Replicated Data Type (CRDT) logic for the
Universal Memory Graph.

This allows Swarm Edge Nodes to maintain localized memory graphs
and merge them asynchronously into the Master Control Plane without
causing data loss or locking collisions.

We use an LWW (Last-Write-Wins) Element Set approach combined with 
semantic edge timestamps.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import text

logger = logging.getLogger("CRDTMemory")

class CRDTMemoryMerger:
    def __init__(self, db):
        self.db = db

    def merge_graph_payload(self, worker_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes a partial graph payload from an edge worker and merges it
        using LWW semantics.
        
        Payload format:
        {
            "nodes": [ { "id": "...", "data": {...}, "timestamp": "..." } ],
            "edges": [ { "source": "...", "target": "...", "timestamp": "..." } ]
        }
        """
        nodes_received = len(payload.get("nodes", []))
        edges_received = len(payload.get("edges", []))
        logger.info(f"CRDT Merge initiated by {worker_id}: {nodes_received} nodes, {edges_received} edges.")

        merged_nodes = 0
        merged_edges = 0

        with self.db.safe_transaction() as session:
            # 1. Merge Nodes (LWW based on `updated_at`)
            for node in payload.get("nodes", []):
                # Using SQLite UPSERT logic
                session.execute(text("""
                    INSERT INTO knowledge_nodes (id, node_type, intent, data_payload, embedding_id, updated_at)
                    VALUES (:id, :type, :intent, :data, :embed, :ts)
                    ON CONFLICT(id) DO UPDATE SET
                        node_type = excluded.node_type,
                        intent = excluded.intent,
                        data_payload = excluded.data_payload,
                        updated_at = excluded.updated_at
                    WHERE knowledge_nodes.updated_at < excluded.updated_at
                """), {
                    "id": node.get("id"),
                    "type": node.get("node_type", "observation"),
                    "intent": node.get("intent", ""),
                    "data": node.get("data_payload", "{}"),
                    "embed": node.get("embedding_id"),
                    "ts": node.get("timestamp", datetime.now(timezone.utc).isoformat())
                })
                merged_nodes += 1

            # 2. Merge Edges (LWW)
            for edge in payload.get("edges", []):
                session.execute(text("""
                    INSERT INTO knowledge_edges (source_id, target_id, relation, weight, updated_at)
                    VALUES (:src, :tgt, :rel, :w, :ts)
                    ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
                        weight = excluded.weight,
                        updated_at = excluded.updated_at
                    WHERE knowledge_edges.updated_at < excluded.updated_at
                """), {
                    "src": edge.get("source"),
                    "tgt": edge.get("target"),
                    "rel": edge.get("relation", "leads_to"),
                    "w": edge.get("weight", 1.0),
                    "ts": edge.get("timestamp", datetime.now(timezone.utc).isoformat())
                })
                merged_edges += 1

        logger.info(f"CRDT Merge complete: {merged_nodes} nodes, {merged_edges} edges integrated.")
        return {
            "status": "success",
            "merged_nodes": merged_nodes,
            "merged_edges": merged_edges
        }
