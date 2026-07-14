"""Tests for FastAPI endpoints via TestClient (no server process needed)."""
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.fixture
def client():
    """Synchronous test client for FastAPI."""
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        yield c


class TestRootEndpoint:
    """Health check."""

    def test_root_returns_welcome(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "Welcome" in res.json()["message"]


class TestAuthFlow:
    """JWT signup + login."""

    def test_signup_and_login(self, client):
        """Should be able to sign up and get a JWT token."""
        import time
        unique_user = f"test_user_{int(time.time())}"
        pwd = "TestPass_1"

        signup = client.post("/api/v1/auth/signup", json={
            "username": unique_user,
            "password": pwd,
            "role": "client"
        })
        assert signup.status_code == 200, f"Signup failed: {signup.json()}"

        login = client.post("/api/v1/auth/login", json={
            "username": unique_user,
            "password": pwd
        })
        assert login.status_code == 200
        assert "token" in login.json()


class TestSyncEndpoints:
    """Sync push and pull via the consolidated router."""

    def _get_auth_header(self, client):
        """Helper to get an auth token."""
        client.post("/api/v1/auth/signup", json={
            "username": "sync_tester",
            "password": "Sync_pass_1",
            "role": "admin"
        })
        login = client.post("/api/v1/auth/login", json={
            "username": "sync_tester",
            "password": "Sync_pass_1"
        })
        return {"Authorization": f"Bearer {login.json()['token']}"}

    def test_sync_push(self, client):
        """POST /api/v1/sync/push should accept a node and return success."""
        headers = self._get_auth_header(client)
        res = client.post("/api/v1/sync/push", headers=headers, json={
            "id": "sync_test_node",
            "domain": "test.com",
            "intent": "sync_action",
            "action_type": "click",
            "action_params": {"target": "button"},
            "face_value": {"desc": "Sync test"},
            "place_value": {"selector": "#sync-btn"},
            "visibility": "public"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"

    def test_sync_pull(self, client):
        """GET /api/v1/sync/pull should return nodes for a domain."""
        headers = self._get_auth_header(client)
        # First push a node
        client.post("/api/v1/sync/push", headers=headers, json={
            "id": "pull_test_node",
            "domain": "pull-test.com",
            "intent": "pull_action",
            "action_type": "click",
            "action_params": {},
            "face_value": {},
            "place_value": {},
            "visibility": "public"
        })
        # Pull for that domain
        res = client.get("/api/v1/sync/pull", headers=headers, params={"domain": "pull-test.com"})
        assert res.status_code == 200
        assert "nodes" in res.json()

    def test_sync_push_rejects_private(self, client):
        """Private nodes should be rejected by the sync endpoint."""
        headers = self._get_auth_header(client)
        res = client.post("/api/v1/sync/push", headers=headers, json={
            "id": "private_node",
            "domain": "test.com",
            "intent": "secret_action",
            "action_type": "click",
            "action_params": {},
            "face_value": {},
            "place_value": {},
            "visibility": "private"
        })
        assert res.status_code == 400

    def test_sync_push_rejects_unauthenticated(self, client):
        """Unauthenticated requests should return 401."""
        res = client.post("/api/v1/sync/push", json={
            "id": "unauth_node",
            "domain": "test.com",
            "intent": "test",
            "action_type": "click",
            "action_params": {},
            "face_value": {},
            "place_value": {},
            "visibility": "public"
        })
        assert res.status_code == 401
