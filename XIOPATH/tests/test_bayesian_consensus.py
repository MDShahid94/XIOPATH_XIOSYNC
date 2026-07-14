"""Tests for the Bayesian EMA consensus engine and ServerMemoryAPI."""
from tests.conftest import DESKTOP_CTX
from core.memory_manager import ServerMemoryAPI
from core.database import DatabaseManager


def _save(mgr, url, intent, place_value=None, **kwargs):
    """Helper to call save_new_action with correct signature."""
    return mgr.save_new_action(
        url=url, intent=intent,
        face_value=kwargs.get("face_value", {}),
        place_value=place_value or {},
        action_type=kwargs.get("action_type", "click"),
        action_params=kwargs.get("action_params", {}),
        context_hash=kwargs.get("context_hash", "default"),
    )


class TestBayesianScoring:
    """Local Bayesian voting via submit_local_vote."""

    def test_repeated_promotes_increase_score(self, memory_mgr):
        """Multiple positive votes should increase the bayesian_score monotonically."""
        _save(memory_mgr, "https://test.com", "bayes_up",
              place_value={"selector": "#b"})
        node = memory_mgr.lookup_action("https://test.com", "bayes_up", DESKTOP_CTX)
        scores = [memory_mgr.db.get_node(node["id"])["bayesian_score"]]

        for _ in range(5):
            memory_mgr.promote_client_secondary(node["id"])
            scores.append(memory_mgr.db.get_node(node["id"])["bayesian_score"])

        # Each score should be >= the previous one
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i - 1], f"Score dropped: {scores[i-1]} -> {scores[i]}"

    def test_repeated_demotes_decrease_score(self, memory_mgr):
        """Multiple negative votes should decrease the bayesian_score."""
        _save(memory_mgr, "https://test.com", "bayes_down",
              place_value={"selector": "#d"})
        node = memory_mgr.lookup_action("https://test.com", "bayes_down", DESKTOP_CTX)
        initial = memory_mgr.db.get_node(node["id"])["bayesian_score"]

        for _ in range(5):
            memory_mgr.demote_client_secondary(node["id"])

        final = memory_mgr.db.get_node(node["id"])["bayesian_score"]
        assert final < initial

    def test_promotion_threshold_triggers_tier_change(self, memory_mgr):
        """Enough positive votes should elevate a node from client_secondary to client_primary."""
        _save(memory_mgr, "https://test.com", "tier_change",
              place_value={"selector": "#t"})
        node = memory_mgr.lookup_action("https://test.com", "tier_change", DESKTOP_CTX)
        assert memory_mgr.db.get_node(node["id"])["tier"] == "client_secondary"

        # Promote many times to cross the threshold (default: 0.70)
        for _ in range(20):
            memory_mgr.promote_client_secondary(node["id"])

        final_node = memory_mgr.db.get_node(node["id"])
        assert final_node["tier"] == "client_primary", \
            f"Expected client_primary, got {final_node['tier']} (score={final_node['bayesian_score']:.3f})"


class TestServerConsensus:
    """ServerMemoryAPI vote-based consensus using its own isolated DB."""

    def test_server_api_creates_node_on_first_vote(self, tmp_data_dir):
        """First vote to ServerMemoryAPI should create the node as server_secondary."""
        db = DatabaseManager(tmp_data_dir / "server_test.db")
        server = ServerMemoryAPI(db)
        action_data = {
            "intent": "server_test",
            "action_type": "click",
            "action_params": {},
            "face_value": {"desc": "test"},
            "place_value": {"selector": "#s"},
        }
        server.submit_vote("test.com", "srv_node_1", action_data, "client_a")
        node = db.get_node("srv_node_1")
        assert node is not None
        assert node["tier"] == "server_secondary"

    def test_multi_client_votes_increase_score(self, tmp_data_dir):
        """Votes from multiple clients should increase the bayesian_score."""
        db = DatabaseManager(tmp_data_dir / "multi_vote.db")
        server = ServerMemoryAPI(db)
        action_data = {
            "intent": "multi_vote",
            "action_type": "click",
            "action_params": {},
            "face_value": {},
            "place_value": {},
        }
        server.submit_vote("test.com", "mv_node", action_data, "client_a")
        score_after_1 = db.get_node("mv_node")["bayesian_score"]

        server.submit_vote("test.com", "mv_node", action_data, "client_b")
        score_after_2 = db.get_node("mv_node")["bayesian_score"]

        server.submit_vote("test.com", "mv_node", action_data, "client_c")
        score_after_3 = db.get_node("mv_node")["bayesian_score"]

        assert score_after_2 >= score_after_1
        assert score_after_3 >= score_after_2
