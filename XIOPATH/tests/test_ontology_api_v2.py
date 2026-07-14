"""
Tests for API v2 — Ontology Endpoints
=============================================
Tests the full CRUD lifecycle for actors, operations, edges, capabilities,
capability grants, versions, connections, profiles, and bundles.
"""
import pytest
import os
import sys
from pathlib import Path

# Ensure the project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# NOTE: No env var overrides here — we use the actual SECRET_KEY from auth.py
# to avoid import-order issues when running with the full test suite.


class TestActorsV2:
    """Test the /api/v2/actors endpoints (and /api/v2/agents backward-compat)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Create a test app with ontology tables matching v5.0 schema."""
        from core.database import DatabaseManager
        from core.ontology_ops import OntologyManager

        # Create temp DB and manually create ontology tables
        db_path = tmp_path / "test_ontology.db"
        self.db = DatabaseManager(db_path)

        # Create ontology tables with v5.0 naming
        from sqlalchemy import text
        with self.db.SessionLocal() as session:
            # actors (was: agents)
            session.execute(text("""CREATE TABLE IF NOT EXISTS actors (
                id TEXT PRIMARY KEY, actor_type TEXT NOT NULL, actor_subtype TEXT,
                role TEXT, alias TEXT, parent_id TEXT,
                state TEXT DEFAULT 'proposed', lifecycle_phase TEXT DEFAULT 'pre_birth',
                trust_tier TEXT DEFAULT 'standard',
                config TEXT, runtime_state TEXT,
                last_heartbeat TIMESTAMP, health_status TEXT DEFAULT 'unknown',
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP,
                created_by TEXT, metadata TEXT
            )"""))
            # operations (was: agent_operations)
            session.execute(text("""CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, operation TEXT NOT NULL,
                from_state TEXT, to_state TEXT, trigger TEXT,
                initiated_by TEXT NOT NULL, collaborators TEXT,
                scope TEXT, depth_level INTEGER DEFAULT 0, parent_operation_id TEXT,
                artifacts TEXT, rationale TEXT, outcome TEXT,
                metadata TEXT, started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP, duration_ms INTEGER
            )"""))
            # actor_edges (was: agent_edges)
            session.execute(text("""CREATE TABLE IF NOT EXISTS actor_edges (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL, config TEXT, weight REAL DEFAULT 1.0,
                bidirectional BOOLEAN DEFAULT 0, state TEXT DEFAULT 'active',
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP, metadata TEXT
            )"""))
            # capabilities (was: tool_registry)
            session.execute(text("""CREATE TABLE IF NOT EXISTS capabilities (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, capability_type TEXT NOT NULL,
                version TEXT, description TEXT, input_schema TEXT, output_schema TEXT,
                config TEXT, execution_mode TEXT DEFAULT 'sync',
                timeout_ms INTEGER DEFAULT 30000, retry_policy TEXT,
                state TEXT DEFAULT 'active', created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP, metadata TEXT
            )"""))
            # capability_grants
            session.execute(text("""CREATE TABLE IF NOT EXISTS capability_grants (
                id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                granted_by TEXT NOT NULL, scope TEXT DEFAULT 'full',
                constraints TEXT, expires_at TIMESTAMP, state TEXT DEFAULT 'active',
                created_at TIMESTAMP NOT NULL, revoked_at TIMESTAMP,
                revoked_by TEXT, metadata TEXT
            )"""))
            # events (was: event_log)
            session.execute(text("""CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'info', summary TEXT, payload TEXT,
                correlation_id TEXT, operation_id TEXT,
                source_ip TEXT, user_agent TEXT,
                created_at TIMESTAMP NOT NULL, metadata TEXT
            )"""))
            # connections (was: runtime_connections)
            session.execute(text("""CREATE TABLE IF NOT EXISTS connections (
                id TEXT PRIMARY KEY, source_actor_id TEXT NOT NULL,
                target_actor_id TEXT NOT NULL, protocol TEXT NOT NULL,
                transport TEXT NOT NULL, source_endpoint TEXT, target_endpoint TEXT,
                current_exit_node_ip TEXT, default_exit_node_ip TEXT,
                exit_node_actor_id TEXT, proxy_config TEXT, routing_rule TEXT,
                pinned_services TEXT, auth_state_path TEXT,
                auth_state_storage TEXT, auth_persistence TEXT,
                state TEXT DEFAULT 'pending', last_ping_ms INTEGER,
                last_verified_at TIMESTAMP, exit_node_switched_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL, metadata TEXT
            )"""))
            # actor_profiles (was: agent_profiles)
            session.execute(text("""CREATE TABLE IF NOT EXISTS actor_profiles (
                id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
                profile_type TEXT NOT NULL, account_identity TEXT,
                storage_backend TEXT NOT NULL, storage_path TEXT NOT NULL,
                storage_folder_id TEXT, encryption_method TEXT DEFAULT 'fernet',
                encryption_key_ref TEXT, persistence_mode TEXT NOT NULL,
                save_interval_seconds INTEGER, last_saved_at TIMESTAMP,
                save_count INTEGER DEFAULT 0, state TEXT DEFAULT 'fresh',
                checksum TEXT, size_bytes INTEGER,
                created_at TIMESTAMP NOT NULL, expires_at TIMESTAMP, metadata TEXT
            )"""))
            # bundles (was: agent_environments)
            session.execute(text("""CREATE TABLE IF NOT EXISTS bundles (
                id TEXT PRIMARY KEY, creator_id TEXT,
                bundle_type TEXT NOT NULL, manifest TEXT NOT NULL,
                storage_backend TEXT NOT NULL, storage_path TEXT NOT NULL,
                bundle_checksum TEXT, bundle_size_bytes INTEGER,
                is_portable BOOLEAN DEFAULT 0, visibility TEXT DEFAULT 'private',
                compatible_runtimes TEXT, created_at TIMESTAMP NOT NULL,
                last_serialized_at TIMESTAMP, version TEXT DEFAULT '1.0.0',
                state TEXT DEFAULT 'active'
            )"""))
            # actor_versions (was: agent_versions)
            session.execute(text("""CREATE TABLE IF NOT EXISTS actor_versions (
                id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
                version_tag TEXT NOT NULL, version_hash TEXT NOT NULL,
                parent_version_id TEXT, branch TEXT DEFAULT 'main',
                config_snapshot TEXT NOT NULL, runtime_state_snapshot TEXT,
                capability_grants_snapshot TEXT, bundle_id TEXT,
                change_type TEXT NOT NULL, change_summary TEXT,
                diff_from_parent TEXT, authored_by TEXT NOT NULL,
                reviewed_by TEXT, operation_id TEXT,
                requires_human_approval BOOLEAN DEFAULT 0,
                approval_status TEXT, approved_by TEXT, approved_at TIMESTAMP,
                git_repo_url TEXT, git_commit_hash TEXT, git_branch TEXT,
                ci_pipeline_status TEXT, ci_pipeline_url TEXT,
                state TEXT DEFAULT 'active', is_current BOOLEAN DEFAULT 0,
                created_at TIMESTAMP NOT NULL
            )"""))
            session.commit()

        # Seed actors
        self.ontology = OntologyManager(self.db)
        self.seed_result = self.ontology.seed_initial_actors()

        # Create FastAPI test client
        from api.main import app
        app.state.db = self.db
        app.state.ontology = self.ontology

        from starlette.testclient import TestClient
        self.client = TestClient(app)

        # Use the ACTUAL SECRET_KEY from auth.py (already imported at module level)
        # This avoids mismatch when running with the full test suite where import
        # order means the env var may not have been set before auth.py loaded.
        from api.routers.auth import SECRET_KEY
        import jwt
        self.admin_token = jwt.encode(
            {"sub": "test_admin", "role": "admin"},
            SECRET_KEY,
            algorithm="HS256",
        )
        self.auth_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Get a client JWT for read-only requests
        self.client_token = jwt.encode(
            {"sub": "test_client", "role": "client"},
            SECRET_KEY,
            algorithm="HS256",
        )
        self.client_headers = {"Authorization": f"Bearer {self.client_token}"}

    # ─── ACTOR CRUD ───────────────────────────────────────────────────────

    def test_list_actors(self):
        res = self.client.get("/api/v2/actors", headers=self.client_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 3  # 3 seeded actors
        assert any(a["alias"] == "Super Admin" for a in data["actors"])

    def test_get_actor(self):
        sa_id = self.seed_result["super_admin"]
        res = self.client.get(f"/api/v2/actors/{sa_id}", headers=self.client_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["actor"]["actor_type"] == "human"
        assert isinstance(data["edges"], list)
        assert isinstance(data["recent_operations"], list)

    def test_create_actor(self):
        res = self.client.post("/api/v2/actors", headers=self.auth_headers, json={
            "actor_type": "compute",
            "actor_subtype": "colab_runtime",
            "alias": "Test Colab Worker",
            "role": "worker",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["alias"] == "Test Colab Worker"
        # Verify it exists
        res2 = self.client.get(f"/api/v2/actors/{data['id']}", headers=self.client_headers)
        assert res2.status_code == 200
        assert res2.json()["actor"]["alias"] == "Test Colab Worker"

    def test_create_actor_invalid_type(self):
        res = self.client.post("/api/v2/actors", headers=self.auth_headers, json={
            "actor_type": "invalid_type",
        })
        assert res.status_code == 400

    def test_update_actor(self):
        sa_id = self.seed_result["super_admin"]
        res = self.client.patch(f"/api/v2/actors/{sa_id}", headers=self.auth_headers, json={
            "runtime_state": {"current_task": "ontology migration"},
        })
        assert res.status_code == 200
        assert "runtime_state" in res.json()["updated_fields"]

    def test_update_actor_requires_admin(self):
        sa_id = self.seed_result["super_admin"]
        res = self.client.patch(f"/api/v2/actors/{sa_id}", headers=self.client_headers, json={
            "alias": "Hacked",
        })
        assert res.status_code == 403

    def test_get_nonexistent_actor(self):
        res = self.client.get("/api/v2/actors/does-not-exist", headers=self.client_headers)
        assert res.status_code == 404

    # ─── OPERATIONS ───────────────────────────────────────────────────────

    def test_record_operation(self):
        api_id = self.seed_result["api_server"]
        res = self.client.post(f"/api/v2/actors/{api_id}/operations", headers=self.auth_headers, json={
            "operation": "updation",
            "to_state": "updating",
            "trigger": "user_command",
            "rationale": "Testing operation recording",
            "outcome": "success",
        })
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_get_operations(self):
        api_id = self.seed_result["api_server"]
        res = self.client.get(f"/api/v2/actors/{api_id}/operations", headers=self.client_headers)
        assert res.status_code == 200
        assert res.json()["total"] >= 1  # At least the seed operation

    # ─── EDGES ────────────────────────────────────────────────────────────

    def test_create_edge(self):
        res = self.client.post("/api/v2/actors/edges", headers=self.auth_headers, json={
            "source_id": self.seed_result["api_server"],
            "target_id": self.seed_result["llm_engine"],
            "edge_type": "delegates_to",
        })
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_get_edges(self):
        sa_id = self.seed_result["super_admin"]
        res = self.client.get(f"/api/v2/actors/{sa_id}/edges", headers=self.client_headers)
        assert res.status_code == 200
        assert res.json()["total"] >= 2  # manages + collaborates_with

    # ─── CAPABILITIES ─────────────────────────────────────────────────────

    def test_register_capability(self):
        res = self.client.post("/api/v2/actors/capabilities", headers=self.auth_headers, json={
            "name": "playwright_click",
            "capability_type": "browser",
            "description": "Click on a web element",
            "version": "1.0.0",
        })
        assert res.status_code == 200
        self.capability_id = res.json()["capability_id"]

    def test_list_capabilities(self):
        # Register one first
        self.client.post("/api/v2/actors/capabilities", headers=self.auth_headers, json={
            "name": "test_capability", "capability_type": "system",
        })
        res = self.client.get("/api/v2/actors/capabilities", headers=self.client_headers)
        assert res.status_code == 200
        assert res.json()["total"] >= 1

    def test_grant_capability(self):
        # Register capability
        cap_res = self.client.post("/api/v2/actors/capabilities", headers=self.auth_headers, json={
            "name": "cap_test_cap", "capability_type": "browser",
        })
        capability_id = cap_res.json()["capability_id"]
        # Grant it
        res = self.client.post("/api/v2/actors/grants", headers=self.auth_headers, json={
            "actor_id": self.seed_result["api_server"],
            "capability_id": capability_id,
        })
        assert res.status_code == 200

    def test_get_actor_capabilities(self):
        # Setup
        cap_res = self.client.post("/api/v2/actors/capabilities", headers=self.auth_headers, json={
            "name": "get_cap_test", "capability_type": "llm",
        })
        self.client.post("/api/v2/actors/grants", headers=self.auth_headers, json={
            "actor_id": self.seed_result["llm_engine"],
            "capability_id": cap_res.json()["capability_id"],
        })
        res = self.client.get(
            f"/api/v2/actors/{self.seed_result['llm_engine']}/capabilities",
            headers=self.client_headers
        )
        assert res.status_code == 200
        assert res.json()["total"] >= 1

    # ─── CONNECTIONS ──────────────────────────────────────────────────────

    def test_create_connection(self):
        res = self.client.post("/api/v2/actors/connections", headers=self.auth_headers, json={
            "source_actor_id": self.seed_result["api_server"],
            "target_actor_id": self.seed_result["llm_engine"],
            "protocol": "tailnet_ws",
            "transport": "tailscale",
            "routing_rule": "direct",
        })
        assert res.status_code == 200

    def test_list_connections(self):
        res = self.client.get("/api/v2/actors/connections", headers=self.client_headers)
        assert res.status_code == 200

    # ─── PROFILES ─────────────────────────────────────────────────────────

    def test_create_profile(self):
        res = self.client.post("/api/v2/actors/profiles", headers=self.auth_headers, json={
            "actor_id": self.seed_result["api_server"],
            "profile_type": "browser_chrome",
            "storage_backend": "google_drive",
            "storage_path": "/drive/MyDrive/profiles/chrome_1.xio",
            "persistence_mode": "periodic",
            "save_interval_seconds": 600,
        })
        assert res.status_code == 200

    def test_get_profiles(self):
        self.client.post("/api/v2/actors/profiles", headers=self.auth_headers, json={
            "actor_id": self.seed_result["llm_engine"],
            "profile_type": "tailscale",
            "storage_backend": "google_drive",
            "storage_path": "/drive/MyDrive/tailscale.state",
            "persistence_mode": "once_per_account",
        })
        res = self.client.get(
            f"/api/v2/actors/{self.seed_result['llm_engine']}/profiles",
            headers=self.client_headers
        )
        assert res.status_code == 200
        assert res.json()["total"] >= 1

    # ─── BUNDLES ──────────────────────────────────────────────────────────

    def test_create_bundle(self):
        res = self.client.post("/api/v2/actors/bundles", headers=self.auth_headers, json={
            "actor_id": self.seed_result["api_server"],
            "bundle_type": "workflow_bundle",
            "manifest": {"capabilities": ["dom_inspector"], "services": []},
            "storage_backend": "google_drive",
            "storage_path": "/drive/MyDrive/bundles/bundle_1.xio-env",
            "visibility": "marketplace",
        })
        assert res.status_code == 200

    # ─── EVENTS ──────────────────────────────────────────────────────────

    def test_get_events(self):
        sa_id = self.seed_result["super_admin"]
        res = self.client.get(f"/api/v2/actors/{sa_id}/events", headers=self.client_headers)
        assert res.status_code == 200
        assert res.json()["total"] >= 1  # At least the seed event

    # ─── RBAC ────────────────────────────────────────────────────────────

    def test_create_actor_requires_admin(self):
        res = self.client.post("/api/v2/actors", headers=self.client_headers, json={
            "actor_type": "compute",
        })
        assert res.status_code == 403

    def test_list_actors_allows_client(self):
        res = self.client.get("/api/v2/actors", headers=self.client_headers)
        assert res.status_code == 200

    def test_no_auth_rejected(self):
        res = self.client.get("/api/v2/actors")
        assert res.status_code in (401, 403)

    # ─── BACKWARD COMPAT ─────────────────────────────────────────────────

    def test_legacy_agents_endpoint_still_works(self):
        """The /agents endpoint should still respond via the backward-compat router."""
        res = self.client.get("/api/v2/agents", headers=self.client_headers)
        assert res.status_code == 200
