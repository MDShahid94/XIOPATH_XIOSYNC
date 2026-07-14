import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages Database storage for Memory Nodes. Uses SQLAlchemy for connection pooling
    and supports both SQLite and PostgreSQL natively via the DATABASE_URL environment variable.
    """
    def __init__(self, db_path: Path):
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"
            
        # E-15: Use NullPool for SQLite (avoids connection pooling issues)
        if "postgresql" in db_url:
            engine_kwargs = {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_timeout": 30,
                "pool_recycle": 1800,
            }
        else:
            engine_kwargs = {"poolclass": NullPool}

        self.engine = create_engine(db_url, **engine_kwargs)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._init_db()



    @contextmanager
    def safe_transaction(self):
        """Context manager with automatic rollback on failure.
        
        Usage:
            with db.safe_transaction() as session:
                session.execute(text("INSERT ..."), params)
                # commit is automatic on success
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _init_db(self):
        # If the DB is Alembic-managed (has alembic_version table), skip legacy
        # CREATE TABLE statements — Alembic owns the schema in that case.
        with self.SessionLocal() as session:
            try:
                result = session.execute(text(
                    "SELECT 1 FROM alembic_version LIMIT 1"
                )).fetchone()
                if result:
                    logger.info("Alembic-managed database detected — skipping legacy _init_db()")
                    return
            except Exception:
                session.rollback()  # Table doesn't exist yet — proceed with legacy init
                logger.info("No Alembic version stamp found — running legacy _init_db()")

        # Legacy fallback: create tables directly (for tests and first-time setup)
        with self.SessionLocal() as session:
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS memory_nodes (
                    id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    device_type TEXT,
                    os_name TEXT,
                    browser TEXT,
                    viewport_width INTEGER,
                    viewport_height INTEGER,
                    visibility TEXT NOT NULL,
                    face_value TEXT NOT NULL,
                    place_value TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_params TEXT NOT NULL,
                    previous_intent TEXT,
                    next_nodes TEXT NOT NULL,
                    promotions INTEGER DEFAULT 0,
                    last_used TIMESTAMP NOT NULL,
                    client_id TEXT NOT NULL,
                    volatility_type TEXT DEFAULT 'static',
                    fallback_plugin TEXT,
                    output_var TEXT,
                    execution_mode TEXT DEFAULT 'sequential',
                    context_hash TEXT,
                    ref_count INTEGER DEFAULT 0,
                    bayesian_score REAL DEFAULT 0.5,
                    ema_score REAL DEFAULT 0.5,
                    total_vote_weight REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'ACTIVE',
                    lookup_key TEXT
                )
            '''))
            
            # For consensus tracking on the server
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS client_votes (
                    node_id TEXT,
                    client_id TEXT,
                    PRIMARY KEY (node_id, client_id)
                )
            '''))

            # E-12: Cumulative vote counting for anti-spam weighting
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS client_vote_counts (
                    client_id TEXT PRIMARY KEY,
                    vote_count INTEGER DEFAULT 0,
                    last_voted TIMESTAMP
                )
            '''))
            
            # Phase 15: Auth & RBAC
            # NOTE: Will be renamed to auth_identities in Phase 3 (v5.0)
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'client'
                )
            '''))

            # C8 Fix: Create scheduled_jobs table (was queried by schedule.py but never created)
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    cron TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP NOT NULL,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    run_count INTEGER DEFAULT 0
                )
            '''))
            # M.5: Marketplace tables
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS marketplace_listings (
                    id TEXT PRIMARY KEY,
                    environment_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT DEFAULT 'automation',
                    tags TEXT,
                    creator_id TEXT NOT NULL,
                    install_count INTEGER DEFAULT 0,
                    rating_sum REAL DEFAULT 0,
                    review_count INTEGER DEFAULT 0,
                    published_at TEXT NOT NULL,
                    updated_at TEXT,
                    state TEXT DEFAULT 'active',
                    UNIQUE(environment_id)
                )
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS marketplace_reviews (
                    id TEXT PRIMARY KEY,
                    listing_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(listing_id, reviewer_id)
                )
            '''))
            session.commit()

            # Attempt to add columns for existing databases (safe migrations)
            migration_columns = [
                "ALTER TABLE memory_nodes ADD COLUMN volatility_type TEXT DEFAULT 'static'",
                "ALTER TABLE memory_nodes ADD COLUMN fallback_plugin TEXT",
                "ALTER TABLE memory_nodes ADD COLUMN output_var TEXT",
                "ALTER TABLE memory_nodes ADD COLUMN execution_mode TEXT DEFAULT 'sequential'",
                "ALTER TABLE memory_nodes ADD COLUMN context_hash TEXT",
                "ALTER TABLE memory_nodes ADD COLUMN ref_count INTEGER DEFAULT 0",
                "ALTER TABLE memory_nodes ADD COLUMN bayesian_score REAL DEFAULT 0.5",
                "ALTER TABLE memory_nodes ADD COLUMN ema_score REAL DEFAULT 0.5",
                "ALTER TABLE memory_nodes ADD COLUMN total_vote_weight REAL DEFAULT 0.0",
                "ALTER TABLE memory_nodes ADD COLUMN status TEXT DEFAULT 'ACTIVE'",
                "ALTER TABLE memory_nodes ADD COLUMN lookup_key TEXT",
            ]
            for col_sql in migration_columns:
                try:
                    session.execute(text(col_sql))
                    session.commit()
                except Exception:
                    session.rollback()

    def upsert_node(self, node_id: str, tier: str, domain: str, intent: str, 
                    device_type: str, os_name: str, browser: str, viewport_width: int, viewport_height: int,
                    visibility: str, face_value: Dict, place_value: Dict, 
                    action_type: str, action_params: Dict, previous_intent: Optional[str], 
                    next_nodes: List[str], promotions: int, client_id: str, last_used: str = None,
                    volatility_type: str = 'static', fallback_plugin: str = None, output_var: str = None,
                    execution_mode: str = 'sequential', context_hash: str = None, ref_count: int = 0,
                    bayesian_score: float = 0.5, ema_score: float = 0.5, total_vote_weight: float = 0.0,
                    status: str = 'ACTIVE', lookup_key: str = None):
        
        if last_used is None:
            last_used = datetime.now().isoformat()
            
        with self.SessionLocal() as session:
            if "postgresql" in str(self.engine.url):
                query = text('''
                    INSERT INTO memory_nodes (
                        id, tier, domain, intent, device_type, os_name, browser, viewport_width, viewport_height, 
                        visibility, face_value, place_value, action_type, action_params, previous_intent, 
                        next_nodes, promotions, last_used, client_id, volatility_type, fallback_plugin, output_var, execution_mode,
                        context_hash, ref_count, bayesian_score, ema_score, total_vote_weight, status, lookup_key
                    ) VALUES (
                        :id, :tier, :domain, :intent, :device_type, :os_name, :browser, :viewport_width, :viewport_height, 
                        :visibility, :face_value, :place_value, :action_type, :action_params, :previous_intent, 
                        :next_nodes, :promotions, :last_used, :client_id, :volatility_type, :fallback_plugin, :output_var, :execution_mode,
                        :context_hash, :ref_count, :bayesian_score, :ema_score, :total_vote_weight, :status, :lookup_key
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        tier=EXCLUDED.tier, face_value=EXCLUDED.face_value, place_value=EXCLUDED.place_value,
                        action_type=EXCLUDED.action_type, action_params=EXCLUDED.action_params,
                        previous_intent=EXCLUDED.previous_intent, next_nodes=EXCLUDED.next_nodes,
                        promotions=EXCLUDED.promotions, last_used=EXCLUDED.last_used, client_id=EXCLUDED.client_id,
                        volatility_type=EXCLUDED.volatility_type, fallback_plugin=EXCLUDED.fallback_plugin,
                        output_var=EXCLUDED.output_var, execution_mode=EXCLUDED.execution_mode,
                        context_hash=EXCLUDED.context_hash, ref_count=EXCLUDED.ref_count,
                        bayesian_score=EXCLUDED.bayesian_score, ema_score=EXCLUDED.ema_score, 
                        total_vote_weight=EXCLUDED.total_vote_weight, status=EXCLUDED.status,
                        lookup_key=EXCLUDED.lookup_key
                ''')
            else:
                query = text('''
                    INSERT INTO memory_nodes (
                        id, tier, domain, intent, device_type, os_name, browser, viewport_width, viewport_height, 
                        visibility, face_value, place_value, action_type, action_params, previous_intent, 
                        next_nodes, promotions, last_used, client_id, volatility_type, fallback_plugin, output_var, execution_mode,
                        context_hash, ref_count, bayesian_score, ema_score, total_vote_weight, status, lookup_key
                    ) VALUES (
                        :id, :tier, :domain, :intent, :device_type, :os_name, :browser, :viewport_width, :viewport_height, 
                        :visibility, :face_value, :place_value, :action_type, :action_params, :previous_intent, 
                        :next_nodes, :promotions, :last_used, :client_id, :volatility_type, :fallback_plugin, :output_var, :execution_mode,
                        :context_hash, :ref_count, :bayesian_score, :ema_score, :total_vote_weight, :status, :lookup_key
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        tier=excluded.tier, face_value=excluded.face_value, place_value=excluded.place_value,
                        action_type=excluded.action_type, action_params=excluded.action_params,
                        previous_intent=excluded.previous_intent, next_nodes=excluded.next_nodes,
                        promotions=excluded.promotions, last_used=excluded.last_used, client_id=excluded.client_id,
                        volatility_type=excluded.volatility_type, fallback_plugin=excluded.fallback_plugin,
                        output_var=excluded.output_var, execution_mode=excluded.execution_mode,
                        context_hash=excluded.context_hash, ref_count=excluded.ref_count,
                        bayesian_score=excluded.bayesian_score, ema_score=excluded.ema_score,
                        total_vote_weight=excluded.total_vote_weight, status=excluded.status,
                        lookup_key=excluded.lookup_key
                ''')
            
            session.execute(query, {
                "id": node_id, "tier": tier, "domain": domain, "intent": intent, 
                "device_type": device_type, "os_name": os_name, "browser": browser, 
                "viewport_width": viewport_width, "viewport_height": viewport_height,
                "visibility": visibility, "face_value": json.dumps(face_value), 
                "place_value": json.dumps(place_value), "action_type": action_type, 
                "action_params": json.dumps(action_params), "previous_intent": previous_intent, 
                "next_nodes": json.dumps(next_nodes), "promotions": promotions, 
                "last_used": last_used, "client_id": client_id, "volatility_type": volatility_type, 
                "fallback_plugin": fallback_plugin, "output_var": output_var, "execution_mode": execution_mode,
                "context_hash": context_hash, "ref_count": ref_count, "bayesian_score": bayesian_score,
                "ema_score": ema_score, "total_vote_weight": total_vote_weight, "status": status,
                "lookup_key": lookup_key
            })
            session.commit()

    # E-08: Partial update method — eliminates 29-arg upsert duplication
    def update_node_fields(self, node_id: str, **updates):
        """Update only specified fields on an existing node."""
        if not updates:
            return
        if "last_used" not in updates:
            updates["last_used"] = datetime.now().isoformat()
        # Serialize dict/list fields
        for key in ("face_value", "place_value", "action_params", "next_nodes"):
            if key in updates and not isinstance(updates[key], str):
                updates[key] = json.dumps(updates[key])

        # C3 Fix: Allowlist valid column names to prevent SQL injection via key manipulation
        ALLOWED_COLUMNS = {
            'tier', 'domain', 'intent', 'device_type', 'os_name', 'browser',
            'viewport_width', 'viewport_height', 'visibility', 'face_value',
            'place_value', 'action_type', 'action_params', 'previous_intent',
            'next_nodes', 'promotions', 'last_used', 'client_id',
            'volatility_type', 'fallback_plugin', 'output_var', 'execution_mode',
            'context_hash', 'ref_count', 'bayesian_score', 'ema_score',
            'total_vote_weight', 'status', 'lookup_key',
            'owner_agent_id'  # O.3: Links memory nodes to owning agent
        }
        invalid_keys = set(updates.keys()) - ALLOWED_COLUMNS
        if invalid_keys:
            raise ValueError(f"Invalid column names in update: {invalid_keys}")

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["_node_id"] = node_id
        with self.SessionLocal() as session:
            session.execute(
                text(f"UPDATE memory_nodes SET {set_clause} WHERE id = :_node_id"),
                updates
            )
            session.commit()

    def get_node(self, node_id: str) -> Optional[Dict]:
        with self.SessionLocal() as session:
            row = session.execute(text("SELECT * FROM memory_nodes WHERE id = :id"), {"id": node_id}).fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    # E-09: Lookup by stable key (without timestamp)
    def get_node_by_lookup_key(self, lookup_key: str) -> Optional[Dict]:
        """Find the most recent node matching a stable lookup_key."""
        with self.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM memory_nodes WHERE lookup_key = :lk ORDER BY last_used DESC LIMIT 1"),
                {"lk": lookup_key}
            ).fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_available_intents(self, domain: str) -> List[str]:
        with self.SessionLocal() as session:
            rows = session.execute(text("SELECT DISTINCT intent FROM memory_nodes WHERE domain = :domain"), {"domain": domain}).fetchall()
            return [row.intent for row in rows]

    # E-16: Merged fallback query using UNION ALL (single DB round-trip)
    def get_node_fallback(self, domain: str, intent: str, context: Dict, max_fallback_tier: int = 2, client_id: str = None) -> List[Dict]:
        device = context.get('device_type')
        os_name = context.get('os_name')
        browser = context.get('browser')
        viewport_str = context.get('viewport', '1280x800')
        
        if 'x' in viewport_str:
            vw, vh = map(int, viewport_str.split('x'))
        else:
            vw, vh = 1280, 800
            
        if vw < 768:
            bp_min, bp_max = 0, 767
        elif vw <= 1024:
            bp_min, bp_max = 768, 1024
        else:
            bp_min, bp_max = 1025, 9999

        # Build UNION ALL of tiers with priority column
        sub_queries = []
        all_params = {
            "domain": domain, "intent": intent, "device": device,
            "os_name": os_name, "browser": browser, "vw": vw, "vh": vh,
            "bp_min": bp_min, "bp_max": bp_max,
        }
        if client_id:
            all_params["client_id"] = client_id

        isolation = (
            " AND (tier IN ('server_primary', 'server_secondary') OR (tier LIKE 'client_%' AND client_id = :client_id)) AND status != 'ARCHIVED'"
            if client_id else
            " AND tier IN ('server_primary', 'server_secondary') AND status != 'ARCHIVED'"
        )

        if max_fallback_tier >= 1:
            sub_queries.append(
                f"SELECT *, 1 AS tier_priority FROM memory_nodes "
                f"WHERE domain = :domain AND intent = :intent AND device_type = :device AND os_name = :os_name "
                f"AND browser = :browser AND viewport_width = :vw AND viewport_height = :vh{isolation}"
            )
        if max_fallback_tier >= 2:
            sub_queries.append(
                f"SELECT *, 2 AS tier_priority FROM memory_nodes "
                f"WHERE domain = :domain AND intent = :intent AND device_type = :device "
                f"AND browser = :browser AND viewport_width = :vw AND viewport_height = :vh{isolation}"
            )
        if max_fallback_tier >= 3:
            sub_queries.append(
                f"SELECT *, 3 AS tier_priority FROM memory_nodes "
                f"WHERE domain = :domain AND intent = :intent AND device_type = :device "
                f"AND viewport_width = :vw AND viewport_height = :vh{isolation}"
            )
        if max_fallback_tier >= 4:
            sub_queries.append(
                f"SELECT *, 4 AS tier_priority FROM memory_nodes "
                f"WHERE domain = :domain AND intent = :intent AND device_type = :device "
                f"AND viewport_width >= :bp_min AND viewport_width <= :bp_max{isolation}"
            )
        if max_fallback_tier >= 5:
            sub_queries.append(
                f"SELECT *, 5 AS tier_priority FROM memory_nodes "
                f"WHERE domain = :domain AND intent = :intent "
                f"AND viewport_width >= :bp_min AND viewport_width <= :bp_max{isolation}"
            )

        if not sub_queries:
            return []

        # Single round-trip: UNION ALL ordered by priority, take first tier's results
        combined = " UNION ALL ".join(sub_queries)
        final_sql = f"SELECT * FROM ({combined}) AS results ORDER BY tier_priority ASC LIMIT 20"

        with self.SessionLocal() as session:
            rows = session.execute(text(final_sql), all_params).fetchall()
            if rows:
                # Return only results from the best (lowest) tier_priority
                best_priority = rows[0].tier_priority
                return [self._row_to_dict(row) for row in rows if row.tier_priority == best_priority]

        return []

    def delete_node(self, node_id: str):
        with self.SessionLocal() as session:
            session.execute(text("DELETE FROM memory_nodes WHERE id = :id"), {"id": node_id})
            session.commit()

    # E-11: SQL-level GC — delete/archive expired nodes without full table scan
    def delete_expired_nodes(self, cutoff_date: str, min_ref_count: int = 0) -> int:
        """Delete expired nodes with ref_count <= min_ref_count. Archive others."""
        with self.SessionLocal() as session:
            # Archive nodes with references
            session.execute(text(
                "UPDATE memory_nodes SET status = 'ARCHIVED' "
                "WHERE last_used < :cutoff AND ref_count > :min_ref AND status != 'ARCHIVED'"
            ), {"cutoff": cutoff_date, "min_ref": min_ref_count})
            # Delete nodes with no references
            result = session.execute(text(
                "DELETE FROM memory_nodes "
                "WHERE last_used < :cutoff AND ref_count <= :min_ref AND status != 'ARCHIVED'"
            ), {"cutoff": cutoff_date, "min_ref": min_ref_count})
            session.commit()
            return result.rowcount

    # E-12: Fixed vote recording with cumulative client count
    def record_vote(self, node_id: str, client_id: str) -> int:
        """Record a vote and return the client's total historical vote count."""
        with self.SessionLocal() as session:
            # Per-node tracking (existing behavior)
            if "postgresql" in str(self.engine.url):
                session.execute(text(
                    "INSERT INTO client_votes (node_id, client_id) VALUES (:nid, :cid) ON CONFLICT DO NOTHING"
                ), {"nid": node_id, "cid": client_id})
            else:
                session.execute(text(
                    "INSERT OR IGNORE INTO client_votes (node_id, client_id) VALUES (:nid, :cid)"
                ), {"nid": node_id, "cid": client_id})

            # Increment global client vote count for anti-spam weighting
            now = datetime.now().isoformat()
            if "postgresql" in str(self.engine.url):
                session.execute(text(
                    "INSERT INTO client_vote_counts (client_id, vote_count, last_voted) "
                    "VALUES (:cid, 1, :now) "
                    "ON CONFLICT(client_id) DO UPDATE SET vote_count = client_vote_counts.vote_count + 1, last_voted = :now"
                ), {"cid": client_id, "now": now})
            else:
                session.execute(text(
                    "INSERT INTO client_vote_counts (client_id, vote_count, last_voted) "
                    "VALUES (:cid, 1, :now) "
                    "ON CONFLICT(client_id) DO UPDATE SET vote_count = vote_count + 1, last_voted = :now"
                ), {"cid": client_id, "now": now})

            # Return total vote count for this client
            row = session.execute(
                text("SELECT vote_count FROM client_vote_counts WHERE client_id = :cid"),
                {"cid": client_id}
            ).fetchone()
            count = row[0] if row else 1
            session.commit()
            return count

    def get_expired_nodes(self, threshold_date: str, tier: str) -> List[str]:
        with self.SessionLocal() as session:
            rows = session.execute(
                text("SELECT id FROM memory_nodes WHERE tier = :tier AND last_used < :date"), 
                {"tier": tier, "date": threshold_date}
            ).fetchall()
            return [r.id for r in rows]

    def get_nodes_by_domain(self, domain: str) -> List[Dict]:
        """Return all memory nodes for a given domain."""
        with self.SessionLocal() as session:
            rows = session.execute(
                text("SELECT * FROM memory_nodes WHERE domain = :domain"),
                {"domain": domain}
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_all_nodes(self) -> List[Dict]:
        with self.SessionLocal() as session:
            rows = session.execute(text("SELECT * FROM memory_nodes")).fetchall()
            return [self._row_to_dict(row) for row in rows]

    # E-17: Safe JSON parsing with fallback
    @staticmethod
    def _safe_json_load(value, default=None):
        """Parse JSON string safely, returning default on failure."""
        if value is None:
            return default if default is not None else {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid JSON in DB field: {str(value)[:100]}...")
            return default if default is not None else {}

    def _row_to_dict(self, getattr_row) -> Dict:
        # SQLAlchemy returns rows where columns are accessible via getattr
        return {
            "id": getattr_row.id,
            "tier": getattr_row.tier,
            "domain": getattr_row.domain,
            "intent": getattr_row.intent,
            "device_type": getattr_row.device_type,
            "os_name": getattr_row.os_name,
            "browser": getattr_row.browser,
            "viewport_width": getattr_row.viewport_width,
            "viewport_height": getattr_row.viewport_height,
            "visibility": getattr_row.visibility,
            "face_value": self._safe_json_load(getattr_row.face_value, {}),
            "place_value": self._safe_json_load(getattr_row.place_value, {}),
            "action_type": getattr_row.action_type,
            "action_params": self._safe_json_load(getattr_row.action_params, {}),
            "previous_intent": getattr_row.previous_intent,
            "next_nodes": self._safe_json_load(getattr_row.next_nodes, []),
            "promotions": getattr_row.promotions,
            "last_used": getattr_row.last_used,
            "client_id": getattr_row.client_id,
            "volatility_type": getattr(getattr_row, "volatility_type", "static"),
            "fallback_plugin": getattr(getattr_row, "fallback_plugin", None),
            "output_var": getattr(getattr_row, "output_var", None),
            "execution_mode": getattr(getattr_row, "execution_mode", "sequential"),
            "context_hash": getattr(getattr_row, "context_hash", None),
            "ref_count": getattr(getattr_row, "ref_count", 0),
            "bayesian_score": getattr(getattr_row, "bayesian_score", 0.5),
            "ema_score": getattr(getattr_row, "ema_score", 0.5),
            "total_vote_weight": getattr(getattr_row, "total_vote_weight", 0.0),
            "status": getattr(getattr_row, "status", "ACTIVE"),
            "lookup_key": getattr(getattr_row, "lookup_key", None),
        }
