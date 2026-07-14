"""
XIOPATH — Intent Indexer (Phase W.2)
=======================================
Keeps ChromaDB in sync with memory_nodes intents for semantic vector search.
Enables "sign in" to match "login", "add to basket" to match "add to cart", etc.
"""

import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class IntentIndexer:
    """
    Indexes workflow intents into ChromaDB for semantic vector search.
    
    Each unique intent string gets embedded and stored with metadata
    (domain, tier) so that semantic_lookup() can find semantically
    similar intents even when the exact text differs.
    """
    
    COLLECTION_NAME = "intent_index"
    
    def __init__(self, chroma_client, db=None):
        self.chroma_client = chroma_client
        self.db = db
        self._collection = None
    
    @property
    def collection(self):
        """Lazy-init the ChromaDB collection."""
        if self._collection is None:
            try:
                self._collection = self.chroma_client.get_or_create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                logger.warning(f"IntentIndexer: Failed to init ChromaDB collection: {e}")
        return self._collection
    
    def index_intent(self, intent: str, domain: str = "", tier: str = "unknown") -> bool:
        """
        Index a single intent into ChromaDB.
        
        Uses the intent string as both the document and the ID (hashed)
        to ensure idempotency — indexing the same intent twice is a no-op.
        
        Args:
            intent: The canonical intent string (e.g., "login_/auth")
            domain: The domain this intent belongs to
            tier: Memory tier (client_primary, server_primary, etc.)
            
        Returns:
            True if indexed successfully, False on error.
        """
        if not intent or not self.collection:
            return False
        
        try:
            # Use a stable ID based on intent + domain
            doc_id = f"intent_{hash(f'{domain}:{intent}') & 0xFFFFFFFF:08x}"
            
            # Extract the human-readable intent (strip URL path suffix)
            clean_intent = intent.split("_/")[0] if "_/" in intent else intent
            
            self.collection.upsert(
                ids=[doc_id],
                documents=[clean_intent],
                metadatas=[{
                    "intent": intent,
                    "domain": domain,
                    "tier": tier,
                    "type": "intent",
                    "clean_intent": clean_intent,
                }]
            )
            return True
        except Exception as e:
            logger.debug(f"IntentIndexer: Failed to index intent '{intent}': {e}")
            return False
    
    def search(self, query: str, n_results: int = 10, domain_filter: str = None) -> List[Dict]:
        """
        Semantic search for intents matching a natural language query.
        
        Args:
            query: Natural language search query (e.g., "sign in", "add to cart")
            n_results: Maximum number of results
            domain_filter: Optional domain filter
            
        Returns:
            List of dicts with 'intent', 'domain', 'tier', 'similarity' keys,
            sorted by similarity (best first).
        """
        if not query or not self.collection:
            return []
        
        try:
            where_filter = {"type": "intent"}
            if domain_filter:
                where_filter["domain"] = domain_filter
            
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
            )
            
            if not results or not results.get("metadatas") or not results["metadatas"][0]:
                return []
            
            search_results = []
            for i, meta in enumerate(results["metadatas"][0]):
                distance = results["distances"][0][i] if results.get("distances") else 0
                search_results.append({
                    "intent": meta.get("intent", ""),
                    "domain": meta.get("domain", ""),
                    "tier": meta.get("tier", "unknown"),
                    "clean_intent": meta.get("clean_intent", ""),
                    "similarity": round(1 - distance, 4),  # Convert distance to similarity
                })
            
            return search_results
        except Exception as e:
            logger.debug(f"IntentIndexer: Semantic search failed for '{query}': {e}")
            return []
    
    def reindex_all(self) -> int:
        """
        Bulk reindex all unique intents from the database.
        
        Returns:
            Number of intents indexed.
        """
        if not self.db or not self.collection:
            return 0
        
        try:
            from sqlalchemy import text
            with self.db.SessionLocal() as session:
                rows = session.execute(text(
                    "SELECT DISTINCT intent, domain, tier FROM memory_nodes WHERE intent IS NOT NULL"
                )).fetchall()
            
            count = 0
            for row in rows:
                if self.index_intent(row.intent, row.domain or "", row.tier or "unknown"):
                    count += 1
            
            logger.info(f"IntentIndexer: Reindexed {count} intents from database")
            return count
        except Exception as e:
            logger.warning(f"IntentIndexer: Bulk reindex failed: {e}")
            return 0
