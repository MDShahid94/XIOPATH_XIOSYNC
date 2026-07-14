"""Tests for the full memory pipeline: save → lookup → promote → demote → GC → graph."""
from tests.conftest import DESKTOP_CTX, MOBILE_CTX


def _save(mgr, url, intent, place_value=None, **kwargs):
    """Helper to call save_new_action with correct signature."""
    return mgr.save_new_action(
        url=url, intent=intent,
        face_value=kwargs.get("face_value", {}),
        place_value=place_value or {},
        action_type=kwargs.get("action_type", "click"),
        action_params=kwargs.get("action_params", {}),
        context_hash=kwargs.get("context_hash", "default"),
        previous_node_id=kwargs.get("previous_node_id", None),
        visibility=kwargs.get("visibility", "public"),
    )


class TestSaveAndLookup:
    """Core save/lookup cycle."""

    def test_save_and_lookup_round_trip(self, memory_mgr):
        """Save an action and retrieve it via lookup."""
        _save(memory_mgr, "https://test.com/home", "click_login",
              place_value={"selector": "#login-btn"})
        result = memory_mgr.lookup_action("https://test.com/home", "click_login", DESKTOP_CTX)
        assert result is not None
        assert result["intent"] == "click_login"
        assert result["place_value"]["selector"] == "#login-btn"

    def test_contextual_scoping_via_context_hash(self, memory_mgr):
        """Different context_hash values should produce distinct nodes."""
        url = "https://test.com/nav"
        _save(memory_mgr, url, "open_menu",
              place_value={"selector": ".mobile-menu"},
              context_hash="mobile_ios_safari")
        _save(memory_mgr, url, "open_menu",
              place_value={"selector": ".desktop-menu"},
              context_hash="desktop_mac_chrome")

        # Both nodes should exist in the database
        all_nodes = memory_mgr.db.get_all_nodes()
        menu_nodes = [n for n in all_nodes if n["intent"] == "open_menu"]
        assert len(menu_nodes) == 2

    def test_lookup_nonexistent_returns_none(self, memory_mgr):
        """Lookup of a non-existent action should return None."""
        result = memory_mgr.lookup_action("https://nothing.com", "no_such_intent", DESKTOP_CTX)
        assert result is None


class TestTTLAndBayesian:
    """TTL reset should preserve Bayesian scores."""

    def test_ttl_reset_preserves_bayesian_scores(self, memory_mgr):
        """When lookup resets TTL via upsert, Bayesian fields must not be reset to defaults."""
        _save(memory_mgr, "https://test.com", "preserved",
              place_value={"selector": "#x"})
        # First lookup to get the node
        node1 = memory_mgr.lookup_action("https://test.com", "preserved", DESKTOP_CTX)
        node_id = node1["id"]

        # Manually set bayesian score high via direct DB access
        db_node = memory_mgr.db.get_node(node_id)
        memory_mgr.db.upsert_node(
            node_id=db_node["id"], tier=db_node["tier"], domain=db_node["domain"],
            intent=db_node["intent"], device_type=db_node["device_type"],
            os_name=db_node["os_name"], browser=db_node["browser"],
            viewport_width=db_node["viewport_width"], viewport_height=db_node["viewport_height"],
            visibility=db_node["visibility"], face_value=db_node["face_value"],
            place_value=db_node["place_value"], action_type=db_node["action_type"],
            action_params=db_node["action_params"], previous_intent=db_node["previous_intent"],
            next_nodes=db_node["next_nodes"], promotions=db_node["promotions"],
            client_id=db_node["client_id"], bayesian_score=0.95, ema_score=0.9
        )

        # Second lookup triggers TTL reset
        memory_mgr.lookup_action("https://test.com", "preserved", DESKTOP_CTX)
        refreshed = memory_mgr.db.get_node(node_id)
        # Bayesian score should NOT be reset to 0.5 default
        assert refreshed["bayesian_score"] == 0.95
        assert refreshed["ema_score"] == 0.9


class TestPromoteDemote:
    """Promote/demote convenience wrappers."""

    def test_promote_increases_score(self, memory_mgr):
        """promote_client_secondary should increase bayesian_score."""
        _save(memory_mgr, "https://test.com", "promote_test",
              place_value={"selector": "#p"})
        node = memory_mgr.lookup_action("https://test.com", "promote_test", DESKTOP_CTX)
        initial_score = memory_mgr.db.get_node(node["id"])["bayesian_score"]

        memory_mgr.promote_client_secondary(node["id"])
        after_promote = memory_mgr.db.get_node(node["id"])["bayesian_score"]
        assert after_promote > initial_score

    def test_demote_decreases_score(self, memory_mgr):
        """demote_client_secondary should decrease bayesian_score."""
        _save(memory_mgr, "https://test.com", "demote_test",
              place_value={"selector": "#d"})
        node = memory_mgr.lookup_action("https://test.com", "demote_test", DESKTOP_CTX)
        initial_score = memory_mgr.db.get_node(node["id"])["bayesian_score"]

        memory_mgr.demote_client_secondary(node["id"])
        after_demote = memory_mgr.db.get_node(node["id"])["bayesian_score"]
        assert after_demote < initial_score


class TestSearchIntents:
    """search_intents using SQLAlchemy."""

    def test_search_returns_matching_intents(self, memory_mgr):
        """search_intents should find intents matching the query."""
        _save(memory_mgr, "https://shop.com", "add_to_cart")
        _save(memory_mgr, "https://shop.com", "checkout")

        results = memory_mgr.search_intents("cart")
        intents = [r["intent"] for r in results]
        assert "add_to_cart" in intents
        # W.2: Semantic search may also return 'checkout' as related —
        # the important assertion is that 'add_to_cart' ranks first
        if len(results) > 1:
            assert results[0]["intent"] == "add_to_cart"


class TestWorkflowGraph:
    """Workflow graph traversal."""

    def test_linked_graph_builds_correctly(self, memory_mgr):
        """A chain of linked actions should produce a traversable graph."""
        url = "https://shop.com"
        # Save step 1
        node1_id = _save(memory_mgr, url, "step_1",
                         place_value={"selector": "#s1"},
                         face_value={"step": 1})
        # Save step 2 linked to step 1
        node2_id = _save(memory_mgr, url, "step_2",
                         place_value={"selector": "#s2"},
                         face_value={"step": 2},
                         previous_node_id=node1_id)

        graph = memory_mgr.get_workflow_graph(url, "step_1", context=DESKTOP_CTX)
        assert graph is not None
        assert graph["intent"] == "step_1"
        # The graph traversal follows next_nodes
        assert len(graph.get("next_nodes", [])) >= 1
