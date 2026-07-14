"""
Shared pytest fixtures for the XIOPATH test suite.
Provides isolated database, memory manager, and secret manager instances
that use temporary directories and are cleaned up after each test.
"""
import os
import shutil
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provides a temporary data directory for test isolation."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def db(tmp_data_dir):
    """Provides an isolated DatabaseManager instance."""
    from core.database import DatabaseManager
    return DatabaseManager(tmp_data_dir / "test_memory.db")


@pytest.fixture
def memory_mgr(tmp_data_dir):
    """Provides an isolated MemoryManager with no sync worker."""
    from core.memory_manager import MemoryManager
    mgr = MemoryManager(
        session_id="test_client",
        memory_dir=str(tmp_data_dir),
        start_sync=False
    )
    return mgr


@pytest.fixture
def secret_mgr(tmp_data_dir):
    """Provides an isolated SecretManager with its own vault key."""
    from core.secret_manager import SecretManager
    return SecretManager(
        secrets_file=str(tmp_data_dir / "test_secrets.json"),
        key_file=str(tmp_data_dir / ".vault_key")
    )


@pytest.fixture
def api_mgr(tmp_data_dir):
    """Provides an isolated ApiManager with its own vault key."""
    from core.api_manager import ApiManager
    return ApiManager(
        keys_file=str(tmp_data_dir / "test_api_keys.json"),
        key_file=str(tmp_data_dir / ".vault_key")
    )


# Default context for browser fingerprinting
DESKTOP_CTX = {
    "device_type": "desktop",
    "os_name": "macintel",
    "browser": "chromium",
    "viewport": "1280x800"
}

MOBILE_CTX = {
    "device_type": "mobile",
    "os_name": "ios",
    "browser": "safari",
    "viewport": "390x844"
}


# ── v5.0 Fixtures ─────────────────────────────────────────────

@pytest.fixture
def xiopath_db(tmp_data_dir):
    """Provides a fully migrated v5.0 DatabaseManager."""
    from core.database import DatabaseManager
    db = DatabaseManager(tmp_data_dir / "test_xiopath.db")

    # Create all v5.0 tables using exact DDLs from the live migrated database
    from sqlalchemy import text
    with db.SessionLocal() as session:
        for ddl in [
            """CREATE TABLE IF NOT EXISTS type_registry (
                id TEXT NOT NULL PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL,
                parent_name TEXT, display_name TEXT, description TEXT, schema TEXT,
                is_builtin BOOLEAN DEFAULT '1', org_id TEXT,
                state TEXT DEFAULT 'active', sort_order INTEGER DEFAULT '0',
                created_at DATETIME NOT NULL, created_by TEXT, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS actors (
                id TEXT NOT NULL PRIMARY KEY, actor_type TEXT NOT NULL, actor_subtype TEXT,
                role TEXT, alias TEXT, parent_id TEXT,
                state TEXT DEFAULT 'proposed', lifecycle_phase TEXT DEFAULT 'pre_birth',
                config TEXT, runtime_state TEXT, last_heartbeat DATETIME,
                health_status TEXT DEFAULT 'unknown',
                created_at DATETIME NOT NULL, updated_at DATETIME,
                created_by TEXT, metadata TEXT,
                trust_tier TEXT DEFAULT 'standard', org_id TEXT)""",
            """CREATE TABLE IF NOT EXISTS actor_edges (
                id TEXT NOT NULL PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL, config TEXT, weight FLOAT DEFAULT '1.0',
                bidirectional BOOLEAN DEFAULT '0', state TEXT DEFAULT 'active',
                created_at DATETIME NOT NULL, updated_at DATETIME, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id TEXT NOT NULL PRIMARY KEY, owner_actor_id TEXT, org_id TEXT,
                domain TEXT NOT NULL, intent TEXT NOT NULL,
                tier TEXT DEFAULT 'client_secondary' NOT NULL,
                status TEXT DEFAULT 'active' NOT NULL,
                action_type TEXT NOT NULL, action_spec TEXT NOT NULL,
                execution_mode TEXT DEFAULT 'sequential',
                face_value TEXT, place_value TEXT, context_hash TEXT, lookup_key TEXT,
                previous_intent TEXT, next_nodes TEXT,
                device_type TEXT, os_name TEXT, browser TEXT,
                viewport_width INTEGER, viewport_height INTEGER,
                bayesian_score FLOAT DEFAULT '0.5', ema_score FLOAT DEFAULT '0.5',
                total_vote_weight FLOAT DEFAULT '0.0', promotions INTEGER DEFAULT '0',
                ref_count INTEGER DEFAULT '0', visibility TEXT DEFAULT 'private',
                volatility_type TEXT DEFAULT 'static', fallback_plugin TEXT,
                output_var TEXT, created_at DATETIME NOT NULL, last_used DATETIME NOT NULL,
                updated_at DATETIME, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS workflows (
                id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                version TEXT DEFAULT '1.0.0', creator_id TEXT NOT NULL, org_id TEXT,
                steps TEXT NOT NULL, input_schema TEXT, output_schema TEXT,
                trigger_type TEXT DEFAULT 'manual', trigger_config TEXT,
                execution_mode TEXT DEFAULT 'sequential', max_retries INTEGER DEFAULT '0',
                timeout_ms INTEGER DEFAULT '300000', policy_id TEXT,
                state TEXT DEFAULT 'draft', visibility TEXT DEFAULT 'private',
                tags TEXT, total_executions INTEGER DEFAULT '0',
                success_rate FLOAT DEFAULT '0.0',
                created_at DATETIME NOT NULL, updated_at DATETIME, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS workflow_executions (
                id TEXT NOT NULL PRIMARY KEY, workflow_id TEXT NOT NULL,
                executor_id TEXT NOT NULL, org_id TEXT,
                status TEXT DEFAULT 'pending' NOT NULL,
                current_step INTEGER DEFAULT '0', total_steps INTEGER DEFAULT '0',
                input_data TEXT, output_data TEXT, step_results TEXT, error TEXT,
                started_at DATETIME, completed_at DATETIME, duration_ms INTEGER,
                environment TEXT, retry_count INTEGER DEFAULT '0',
                parent_execution_id TEXT,
                created_at DATETIME NOT NULL, updated_at DATETIME, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS execution_policies (
                id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT,
                allow_network BOOLEAN DEFAULT '0', allow_filesystem BOOLEAN DEFAULT '0',
                allow_subprocess BOOLEAN DEFAULT '0', allow_browser BOOLEAN DEFAULT '1',
                allow_llm BOOLEAN DEFAULT '1', max_steps INTEGER DEFAULT '100',
                max_duration_ms INTEGER DEFAULT '600000', max_memory_mb INTEGER DEFAULT '512',
                max_retries INTEGER DEFAULT '3', allowed_domains TEXT,
                blocked_domains TEXT, allowed_action_types TEXT,
                is_builtin BOOLEAN DEFAULT '1', org_id TEXT,
                state TEXT DEFAULT 'active', created_at DATETIME NOT NULL, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS organizations (
                id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                display_name TEXT, slug TEXT UNIQUE,
                plan TEXT DEFAULT 'free', state TEXT DEFAULT 'active',
                owner_actor_id TEXT, max_actors INTEGER DEFAULT '50',
                max_custom_types INTEGER DEFAULT '100',
                max_knowledge_nodes INTEGER DEFAULT '10000',
                billing_email TEXT,
                created_at DATETIME NOT NULL, updated_at DATETIME, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS org_memberships (
                id TEXT NOT NULL PRIMARY KEY, org_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                role TEXT DEFAULT 'member' NOT NULL, state TEXT DEFAULT 'active',
                invited_by TEXT, joined_at DATETIME,
                created_at DATETIME NOT NULL, metadata TEXT)""",
            """CREATE TABLE IF NOT EXISTS client_vote_counts (
                client_id TEXT NOT NULL PRIMARY KEY,
                vote_count INTEGER DEFAULT '0', last_voted DATETIME)""",
        ]:
            session.execute(text(ddl))
        session.commit()
    return db


@pytest.fixture
def type_registry(xiopath_db):
    """Provides a seeded TypeRegistry."""
    from core.type_registry import TypeRegistry
    tr = TypeRegistry(xiopath_db)
    tr.seed_builtins()
    return tr


@pytest.fixture
def knowledge_mgr(xiopath_db, type_registry):
    """Provides a KnowledgeManager."""
    from core.knowledge_manager import KnowledgeManager
    return KnowledgeManager(xiopath_db, type_registry=type_registry)


@pytest.fixture
def workflow_mgr(xiopath_db, knowledge_mgr):
    """Provides a WorkflowManager."""
    from core.workflow_manager import WorkflowManager
    return WorkflowManager(xiopath_db, knowledge_manager=knowledge_mgr)


@pytest.fixture
def policy_mgr(xiopath_db):
    """Provides a PolicyManager."""
    from core.policy_manager import PolicyManager
    return PolicyManager(xiopath_db)


@pytest.fixture
def memory_bridge(xiopath_db, knowledge_mgr):
    """Provides a MemoryBridge for backward-compat testing."""
    from core.memory_bridge import MemoryBridge
    return MemoryBridge(session_id="test_session", knowledge_manager=knowledge_mgr, db=xiopath_db)
