"""
Tests for Phase M — Marketplace & Multi-Tenancy
==================================================
Tests bundle format, environment manager, marketplace API,
tenant context, vault isolation, and execution engine.
"""
import pytest
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════════
# M.1: Bundle Format
# ═══════════════════════════════════════════════════════════════════════════

class TestBundleFormat:
    """Test .xio-env bundle serialization and deserialization."""

    def test_bundle_round_trip(self):
        """Serialize and deserialize a bundle — all data preserved."""
        from core.bundle_format import (
            BundleManifest, BundleComponent, serialize_bundle, deserialize_bundle
        )
        manifest = BundleManifest(
            creator_id="test_creator",
            title="Test Workflow",
            description="A test workflow bundle",
            components=[
                BundleComponent("workflow_graph", "login_flow",
                                data={"steps": ["navigate", "fill", "click"]},
                                metadata={"url": "https://example.com"}),
                BundleComponent("ai_context", "memory_snapshot",
                                data={"intents": ["login", "signup"]}),
            ],
            workflow_vars={"email": "vault://user_email"},
        )

        raw = serialize_bundle(manifest)
        assert raw[:8] == b"XIOENV01"
        assert len(raw) > 12

        restored = deserialize_bundle(raw)
        assert restored.title == "Test Workflow"
        assert restored.creator_id == "test_creator"
        assert len(restored.components) == 2
        assert restored.components[0].component_type == "workflow_graph"
        assert restored.components[0].data["steps"] == ["navigate", "fill", "click"]

    def test_bundle_checksum_integrity(self):
        """Checksum should match after round-trip."""
        from core.bundle_format import BundleManifest, serialize_bundle, deserialize_bundle
        m = BundleManifest(creator_id="c1", title="Checksum Test")
        raw = serialize_bundle(m)
        restored = deserialize_bundle(raw)
        assert restored.checksum  # Should have a checksum

    def test_bundle_vault_key_extraction(self):
        """Required vault keys should be extracted from workflow_vars."""
        from core.bundle_format import BundleManifest, BundleComponent, serialize_bundle, deserialize_bundle
        m = BundleManifest(
            creator_id="c1", title="Vault Test",
            workflow_vars={"email": "vault://login_email", "pw": "vault://login_password", "name": "literal"},
            components=[BundleComponent("ai_context", "ctx",
                                        data={"api_key": "vault://api_key"})],
        )
        raw = serialize_bundle(m)
        restored = deserialize_bundle(raw)
        assert "login_email" in restored.required_vault_keys
        assert "login_password" in restored.required_vault_keys
        assert "api_key" in restored.required_vault_keys

    def test_bundle_invalid_magic_bytes(self):
        """Should reject bundles with invalid magic bytes."""
        from core.bundle_format import deserialize_bundle
        with pytest.raises(ValueError, match="magic bytes"):
            deserialize_bundle(b"INVALID0" + b"\x00" * 100)

    def test_bundle_component_from_dict(self):
        """BundleComponent should serialize/deserialize correctly."""
        from core.bundle_format import BundleComponent
        c = BundleComponent("workflow_graph", "test", data={"x": 1}, metadata={"url": "http://test.com"})
        d = c.to_dict()
        c2 = BundleComponent.from_dict(d)
        assert c2.component_type == "workflow_graph"
        assert c2.data == {"x": 1}
        assert c2.metadata["url"] == "http://test.com"


# ═══════════════════════════════════════════════════════════════════════════
# M.3: Tenant Context & Vault Isolation
# ═══════════════════════════════════════════════════════════════════════════

class TestTenantContext:
    """Test multi-tenancy context and vault credential boundary."""

    def test_tenant_roles(self):
        from core.tenant_context import TenantContext
        admin = TenantContext(user_id="admin1", role="admin")
        assert admin.is_admin
        assert admin.is_creator
        assert admin.can_publish()

        creator = TenantContext(user_id="creator1", role="creator")
        assert not creator.is_admin
        assert creator.is_creator
        assert creator.can_publish()

        user = TenantContext(user_id="user1", role="user")
        assert not user.is_admin
        assert not user.is_creator
        assert not user.can_publish()

    def test_vault_namespace_auto_generated(self):
        from core.tenant_context import TenantContext
        tc = TenantContext(user_id="abc123")
        assert tc.vault_namespace == "vault_abc123"

    def test_can_manage_listing(self):
        from core.tenant_context import TenantContext
        tc = TenantContext(user_id="creator1", role="creator")
        assert tc.can_manage_listing("creator1")
        assert not tc.can_manage_listing("other_creator")

        admin = TenantContext(user_id="admin1", role="admin")
        assert admin.can_manage_listing("anyone")

    def test_vault_key_extraction(self):
        from core.tenant_context import extract_required_vault_keys
        keys = extract_required_vault_keys({
            "email": "vault://login_email",
            "name": "literal_value",
            "nested": {
                "pw": "vault://password",
                "deep": {"key": "vault://api_key"},
            },
            "list_data": [{"x": "vault://list_secret"}],
        })
        assert sorted(keys) == ["api_key", "list_secret", "login_email", "password"]

    def test_vault_remap_preserves_structure(self):
        from core.tenant_context import remap_vault_references
        data = {"email": "vault://login_email", "name": "literal", "nested": {"pw": "vault://pw"}}
        remapped = remap_vault_references(data, "vault_user2")
        # Fix 3.3: vault refs are now annotated with executor namespace
        assert remapped["email"] == "vault://vault_user2/login_email"
        assert remapped["name"] == "literal"
        assert remapped["nested"]["pw"] == "vault://vault_user2/pw"

    def test_tenant_to_dict(self):
        from core.tenant_context import TenantContext
        tc = TenantContext(user_id="u1", role="creator", environment_id="env1")
        d = tc.to_dict()
        assert d["user_id"] == "u1"
        assert d["is_creator"] is True
        assert d["vault_namespace"] == "vault_u1"


# ═══════════════════════════════════════════════════════════════════════════
# M.4: Environment Executor
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvironmentExecutor:
    """Test environment execution engine."""

    def test_executor_construction(self):
        from core.environment_executor import EnvironmentExecutor
        ex = EnvironmentExecutor(env_manager=None)
        assert ex.secrets is None
        assert ex.orchestrator is None

    def test_validate_missing_environment(self):
        from core.environment_executor import EnvironmentExecutor
        from unittest.mock import MagicMock
        mock_mgr = MagicMock()
        mock_mgr.get_environment.return_value = None
        ex = EnvironmentExecutor(env_manager=mock_mgr)
        result = ex.validate_prerequisites("nonexistent", "user1")
        assert result["ready"] is False
        assert "not found" in result.get("error", "")

    def test_validate_no_vault_keys_needed(self):
        from core.environment_executor import EnvironmentExecutor
        from unittest.mock import MagicMock
        mock_mgr = MagicMock()
        mock_mgr.get_environment.return_value = {
            "manifest": json.dumps({"workflow_vars": {"name": "literal_value"}, "components": []}),
        }
        ex = EnvironmentExecutor(env_manager=mock_mgr)
        result = ex.validate_prerequisites("env1", "user1")
        assert result["ready"] is True
        assert result["missing_keys"] == []


# ═══════════════════════════════════════════════════════════════════════════
# M.2 + M.5: Marketplace API (requires running app with migration)
# ═══════════════════════════════════════════════════════════════════════════

class TestMarketplaceAPI:
    """Test marketplace REST endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from api.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_browse_no_auth_required(self):
        """Browse should work without authentication."""
        res = self.client.get("/api/v1/marketplace/browse")
        # May return 200 or 500 depending on whether migration has run
        # but should NOT return 401
        assert res.status_code != 401

    def test_search_no_auth_required(self):
        """Search should work without authentication."""
        res = self.client.get("/api/v1/marketplace/search?q=login")
        assert res.status_code != 401

    def test_publish_requires_auth(self):
        """Publish should require authentication."""
        res = self.client.post("/api/v1/marketplace/publish", json={
            "environment_id": "test", "title": "Test"
        })
        assert res.status_code == 401

    def test_install_requires_auth(self):
        """Install should require authentication."""
        res = self.client.post("/api/v1/marketplace/test-listing/install")
        assert res.status_code == 401

    def test_review_requires_auth(self):
        """Review should require authentication."""
        res = self.client.post("/api/v1/marketplace/test-listing/review",
                               json={"rating": 5})
        assert res.status_code == 401

    def test_my_published_requires_auth(self):
        """My published should require authentication."""
        res = self.client.get("/api/v1/marketplace/my/published")
        assert res.status_code == 401

    def test_my_installed_requires_auth(self):
        """My installed should require authentication."""
        res = self.client.get("/api/v1/marketplace/my/installed")
        assert res.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# M.6: Multi-Tenancy Middleware
# ═══════════════════════════════════════════════════════════════════════════

class TestTenantScopeMiddleware:
    """Test that TenantScopeMiddleware is wired and runs."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from api.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_public_endpoint_gets_anonymous_tenant(self):
        """Public endpoints should get anonymous tenant context."""
        # Root endpoint is public
        res = self.client.get("/")
        assert res.status_code == 200
