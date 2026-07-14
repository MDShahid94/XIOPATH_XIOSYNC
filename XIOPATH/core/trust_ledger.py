"""
XIOPATH — Swarm Trust & Reputation Ledger (Phase S)
=====================================================
Manages the Trust Tiers and reputation scores for decentralized
volunteer compute nodes.

Trust Tiers:
0 - Untrusted (Sandboxed, heavily restricted, zero impact on global state)
1 - Verified (Passed basic captchas/PoW, can run basic inference)
2 - Trusted (Consistent success rate > 95%, can run standard workflows)
3 - Core (Long-term uptime, can participate in distributed state consensus)
4 - Admin (Owned by XIOPATH internal team, full bypass)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import text

logger = logging.getLogger("TrustLedger")

class TrustTier:
    UNTRUSTED = 0
    VERIFIED = 1
    TRUSTED = 2
    CORE = 3
    ADMIN = 4

class TrustLedger:
    def __init__(self, db):
        self.db = db
        self._ensure_table()

    def _ensure_table(self):
        """Ensure the trust_ledger table exists in the unified DB."""
        with self.db.safe_transaction() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS trust_ledger (
                    actor_id TEXT PRIMARY KEY,
                    tier INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    reputation_score REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

    def get_trust_tier(self, actor_id: str) -> int:
        """Get the current trust tier of a worker node."""
        with self.db.safe_transaction() as session:
            result = session.execute(
                text("SELECT tier FROM trust_ledger WHERE actor_id = :id"),
                {"id": actor_id}
            ).fetchone()
            return result[0] if result else TrustTier.UNTRUSTED

    def record_task_outcome(self, actor_id: str, success: bool):
        """Update reputation based on task outcome and dynamically promote/demote."""
        with self.db.safe_transaction() as session:
            # Upsert record
            session.execute(text("""
                INSERT INTO trust_ledger (actor_id, success_count, failure_count)
                VALUES (:id, :s, :f)
                ON CONFLICT(actor_id) DO UPDATE SET
                    success_count = trust_ledger.success_count + :s,
                    failure_count = trust_ledger.failure_count + :f,
                    last_updated = CURRENT_TIMESTAMP
            """), {"id": actor_id, "s": 1 if success else 0, "f": 0 if success else 1})

            # Recalculate score
            row = session.execute(
                text("SELECT success_count, failure_count, tier FROM trust_ledger WHERE actor_id = :id"),
                {"id": actor_id}
            ).fetchone()

            if row:
                total = row.success_count + row.failure_count
                if total > 0:
                    score = (row.success_count / total) * 100
                    
                    # Update score
                    session.execute(
                        text("UPDATE trust_ledger SET reputation_score = :score WHERE actor_id = :id"),
                        {"score": score, "id": actor_id}
                    )
                    
                    # Auto-promotion logic
                    current_tier = row.tier
                    new_tier = current_tier
                    
                    if total > 50 and score >= 95.0 and current_tier < TrustTier.TRUSTED:
                        new_tier = TrustTier.TRUSTED
                        logger.info(f"🏆 Actor {actor_id} promoted to TRUSTED.")
                    elif total > 10 and score >= 80.0 and current_tier < TrustTier.VERIFIED:
                        new_tier = TrustTier.VERIFIED
                        logger.info(f"✅ Actor {actor_id} promoted to VERIFIED.")
                    elif score < 60.0 and current_tier > TrustTier.UNTRUSTED:
                        new_tier = TrustTier.UNTRUSTED
                        logger.warning(f"⚠️ Actor {actor_id} demoted to UNTRUSTED due to poor performance.")

                    if new_tier != current_tier:
                        session.execute(
                            text("UPDATE trust_ledger SET tier = :tier WHERE actor_id = :id"),
                            {"tier": new_tier, "id": actor_id}
                        )
