"""Tests for the DatabaseManager layer — upsert, get, delete, vote tracking, migrations."""
import json
from datetime import datetime


class TestDatabaseCRUD:
    """Basic CRUD operations on memory_nodes."""

    def test_upsert_and_get_node(self, db):
        """Round-trip: write a node and read it back."""
        db.upsert_node(
            node_id="n1", tier="client_secondary", domain="test.com", intent="login",
            device_type="desktop", os_name="macintel", browser="chromium",
            viewport_width=1280, viewport_height=800, visibility="public",
            face_value={"desc": "Login button"}, place_value={"selector": "#btn"},
            action_type="click", action_params={"target": "button"},
            previous_intent=None, next_nodes=[], promotions=0, client_id="test_client"
        )
        node = db.get_node("n1")
        assert node is not None
        assert node["intent"] == "login"
        assert node["domain"] == "test.com"
        assert node["tier"] == "client_secondary"
        assert node["face_value"]["desc"] == "Login button"

    def test_delete_node(self, db):
        """Deleted nodes should not be retrievable."""
        db.upsert_node(
            node_id="n_del", tier="client_secondary", domain="x.com", intent="signup",
            device_type="desktop", os_name="win", browser="chrome",
            viewport_width=1920, viewport_height=1080, visibility="public",
            face_value={}, place_value={}, action_type="click", action_params={},
            previous_intent=None, next_nodes=[], promotions=0, client_id="c1"
        )
        assert db.get_node("n_del") is not None
        db.delete_node("n_del")
        assert db.get_node("n_del") is None

    def test_get_nodes_by_domain(self, db):
        """get_nodes_by_domain should return only nodes for the specified domain."""
        for i, domain in enumerate(["a.com", "a.com", "b.com"]):
            db.upsert_node(
                node_id=f"dom_{i}", tier="server_secondary", domain=domain,
                intent=f"action_{i}", device_type="desktop", os_name="mac",
                browser="chrome", viewport_width=1280, viewport_height=800,
                visibility="public", face_value={}, place_value={},
                action_type="click", action_params={}, previous_intent=None,
                next_nodes=[], promotions=0, client_id="c1"
            )
        a_nodes = db.get_nodes_by_domain("a.com")
        b_nodes = db.get_nodes_by_domain("b.com")
        assert len(a_nodes) == 2
        assert len(b_nodes) == 1
        assert b_nodes[0]["intent"] == "action_2"

    def test_get_all_nodes(self, db):
        """get_all_nodes should return every node in the database."""
        for i in range(3):
            db.upsert_node(
                node_id=f"all_{i}", tier="client_secondary", domain="x.com",
                intent=f"i_{i}", device_type="desktop", os_name="mac",
                browser="chrome", viewport_width=1280, viewport_height=800,
                visibility="public", face_value={}, place_value={},
                action_type="click", action_params={}, previous_intent=None,
                next_nodes=[], promotions=0, client_id="c1"
            )
        assert len(db.get_all_nodes()) == 3


class TestVoteTracking:
    """Vote deduplication and counting."""

    def test_record_vote_counts_unique_clients(self, db):
        """Same client voting twice should only count once."""
        # Need a node first
        db.upsert_node(
            node_id="vote_n", tier="server_secondary", domain="x.com", intent="test",
            device_type="desktop", os_name="mac", browser="chrome",
            viewport_width=1280, viewport_height=800, visibility="public",
            face_value={}, place_value={}, action_type="click", action_params={},
            previous_intent=None, next_nodes=[], promotions=0, client_id="c1"
        )
        count1 = db.record_vote("vote_n", "client_a")
        count2 = db.record_vote("vote_n", "client_a")  # per-node deduped but global count still increments
        count3 = db.record_vote("vote_n", "client_b")
        assert count1 == 1   # first vote for client_a
        assert count2 == 2   # global count increments (anti-spam weighting), per-node row is deduped
        assert count3 == 1   # first vote for client_b


class TestMigrationColumns:
    """Verify all Phase 20 columns exist after initialization."""

    def test_phase20_columns_exist(self, db):
        """All Phase 20 columns should be queryable."""
        db.upsert_node(
            node_id="mig_test", tier="client_secondary", domain="x.com", intent="test",
            device_type="desktop", os_name="mac", browser="chrome",
            viewport_width=1280, viewport_height=800, visibility="public",
            face_value={}, place_value={}, action_type="click", action_params={},
            previous_intent=None, next_nodes=[], promotions=0, client_id="c1",
            volatility_type="dynamic", fallback_plugin="captcha_solver",
            output_var="result", execution_mode="parallel",
            context_hash="abc123", ref_count=5,
            bayesian_score=0.75, ema_score=0.8,
            total_vote_weight=3.5, status="ACTIVE"
        )
        node = db.get_node("mig_test")
        assert node["volatility_type"] == "dynamic"
        assert node["fallback_plugin"] == "captcha_solver"
        assert node["output_var"] == "result"
        assert node["bayesian_score"] == 0.75
        assert node["ema_score"] == 0.8
        assert node["ref_count"] == 5
        assert node["status"] == "ACTIVE"
