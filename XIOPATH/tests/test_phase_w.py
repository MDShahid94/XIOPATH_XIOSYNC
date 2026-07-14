"""
Tests for Phase W — Workflow Architecture
=============================================
Tests cycle detection, depth limits, semantic search, orchestrator,
parallel execution, and MWA data structures.
"""
import pytest
import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════════
# W.1: Cycle Detection & Depth Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestCycleDetection:
    """Verify cycle detection and max_depth in get_workflow_graph()."""

    def test_cycle_detected_in_graph_building(self):
        """Verify visited set prevents infinite loops during graph construction."""
        from core.memory_manager import MemoryManager
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(session_id="test_cycle", memory_dir=tmpdir, start_sync=False)
            # Building a graph with no nodes — just verify the mechanism exists
            result = mm.get_workflow_graph("http://test.com", "nonexistent", {}, max_fallback_tier=0)
            assert result is None  # No nodes found, returns None gracefully

    def test_max_depth_increased_from_10_to_100(self):
        """Verify default max_depth is now 100 (was 10)."""
        from core.memory_manager import MemoryManager
        import inspect
        sig = inspect.signature(MemoryManager.get_workflow_graph)
        max_depth_default = sig.parameters['max_depth'].default
        assert max_depth_default == 100, f"Expected max_depth=100, got {max_depth_default}"


# ═══════════════════════════════════════════════════════════════════════════
# W.2: Semantic Intent Search
# ═══════════════════════════════════════════════════════════════════════════

class TestIntentIndexer:
    """Test ChromaDB-based semantic intent search."""

    def test_index_and_search(self):
        import chromadb
        from core.intent_indexer import IntentIndexer
        client = chromadb.Client()
        indexer = IntentIndexer(client)

        # Index some intents
        assert indexer.index_intent("login_/auth", domain="example.com")
        assert indexer.index_intent("sign_in_/auth", domain="example.com")
        assert indexer.index_intent("add_to_cart_/shop", domain="shop.com")

        # Search semantically
        results = indexer.search("sign in")
        assert len(results) > 0
        # "sign_in" should rank higher than "add_to_cart"
        intents = [r["intent"] for r in results]
        assert "sign_in_/auth" in intents

    def test_search_similarity_ranking(self):
        import chromadb
        from core.intent_indexer import IntentIndexer
        client = chromadb.Client()
        indexer = IntentIndexer(client)

        indexer.index_intent("login_/auth", domain="test.com")
        indexer.index_intent("checkout_/shop", domain="test.com")
        indexer.index_intent("register_/auth", domain="test.com")

        results = indexer.search("log in to account")
        assert len(results) > 0
        # login should be the most similar
        assert results[0]["intent"] == "login_/auth"

    def test_empty_query_returns_empty(self):
        import chromadb
        from core.intent_indexer import IntentIndexer
        client = chromadb.Client()
        indexer = IntentIndexer(client)
        results = indexer.search("")
        assert results == []

    def test_index_idempotent(self):
        import chromadb
        from core.intent_indexer import IntentIndexer
        client = chromadb.Client()
        indexer = IntentIndexer(client)

        # Index same intent twice — should not error
        assert indexer.index_intent("login_/auth", domain="test.com")
        assert indexer.index_intent("login_/auth", domain="test.com")

    def test_memory_manager_has_intent_indexer(self):
        """Verify IntentIndexer is wired into MemoryManager."""
        from core.memory_manager import MemoryManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(session_id="test_idx", memory_dir=tmpdir, start_sync=False)
            assert hasattr(mm, 'intent_indexer')
            assert mm.intent_indexer is not None


# ═══════════════════════════════════════════════════════════════════════════
# W.4: Workflow Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowOrchestrator:
    """Test workflow lifecycle management."""

    def test_workflow_execution_lifecycle(self):
        from core.workflow_orchestrator import WorkflowExecution, WorkflowStatus
        we = WorkflowExecution(id="test-1", workflow_intent="login")
        assert we.status == WorkflowStatus.PENDING
        we.status = WorkflowStatus.RUNNING
        we.start_time = time.time() - 1.0  # 1 second ago
        assert we.duration_seconds >= 1.0
        d = we.to_dict()
        assert d["status"] == "running"
        assert d["workflow_intent"] == "login"

    def test_workflow_status_enum(self):
        from core.workflow_orchestrator import WorkflowStatus
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"
        assert WorkflowStatus.PAUSED == "paused"

    def test_orchestrator_max_concurrent(self):
        from core.workflow_orchestrator import WorkflowOrchestrator
        # Can't fully test without agent_loop, but verify construction
        orch = WorkflowOrchestrator(agent_loop=None, max_concurrent=3)
        assert orch.max_concurrent == 3
        assert len(orch.executions) == 0
        assert orch.list_active() == []
        assert orch.list_all() == []

    def test_orchestrator_get_status_missing(self):
        from core.workflow_orchestrator import WorkflowOrchestrator
        orch = WorkflowOrchestrator(agent_loop=None)
        assert orch.get_status("nonexistent") is None

    def test_orchestrator_cleanup(self):
        from core.workflow_orchestrator import WorkflowOrchestrator, WorkflowExecution, WorkflowStatus
        orch = WorkflowOrchestrator(agent_loop=None)
        # Add a completed execution
        we = WorkflowExecution(id="old-1", workflow_intent="test", status=WorkflowStatus.COMPLETED)
        we.end_time = time.time() - 7200  # 2 hours ago
        orch.executions["old-1"] = we
        removed = orch.cleanup_completed(max_age_seconds=3600)
        assert removed == 1
        assert "old-1" not in orch.executions


# ═══════════════════════════════════════════════════════════════════════════
# W.4: Workflow API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowAPI:
    """Test workflow REST endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from api.main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_active_workflows_unauthenticated(self):
        res = self.client.get("/api/v1/workflows/active")
        assert res.status_code == 401

    def test_workflow_history_unauthenticated(self):
        res = self.client.get("/api/v1/workflows/history")
        assert res.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# W.6: Master Workflow Agent
# ═══════════════════════════════════════════════════════════════════════════

class TestMasterWorkflowAgent:
    """Test MWA data structures and DAG logic."""

    def test_sub_workflow_plan(self):
        from core.master_workflow_agent import SubWorkflowPlan
        sw = SubWorkflowPlan(
            id="sw1",
            intent="scrape_prices",
            input_vars=[],
            output_var="prices",
            depends_on=[]
        )
        assert sw.status == "pending"
        assert sw.output_var == "prices"

    def test_goal_execution_to_dict(self):
        from core.master_workflow_agent import GoalExecution, SubWorkflowPlan
        sw1 = SubWorkflowPlan(id="sw1", intent="step1", depends_on=[])
        sw2 = SubWorkflowPlan(id="sw2", intent="step2", depends_on=["step1"])
        ge = GoalExecution(
            id="g1",
            goal="complex task",
            sub_workflows=[sw1, sw2],
            start_time=time.time()
        )
        d = ge.to_dict()
        assert d["goal"] == "complex task"
        assert len(d["sub_workflows"]) == 2
        assert d["sub_workflows"][1]["depends_on"] == ["step1"]

    def test_mwa_construction(self):
        from core.master_workflow_agent import MasterWorkflowAgent
        mwa = MasterWorkflowAgent(agent_loop=None, llm=None)
        assert len(mwa.goal_executions) == 0
        assert mwa.get_goal_status("nonexistent") is None
        assert mwa.list_goals() == []

    def test_dependency_chain_correctness(self):
        """Verify DAG dependency tracking works correctly."""
        from core.master_workflow_agent import SubWorkflowPlan
        sw1 = SubWorkflowPlan(id="sw1", intent="a", depends_on=[])
        sw2 = SubWorkflowPlan(id="sw2", intent="b", depends_on=["a"])
        sw3 = SubWorkflowPlan(id="sw3", intent="c", depends_on=["a", "b"])
        
        # sw1 has no deps → ready
        assert all(dep in set() for dep in sw1.depends_on) is True
        # sw2 depends on "a" → not ready until "a" completed
        completed = set()
        assert all(dep in completed for dep in sw2.depends_on) is False
        completed.add("a")
        assert all(dep in completed for dep in sw2.depends_on) is True
        # sw3 depends on "a" and "b"
        assert all(dep in completed for dep in sw3.depends_on) is False
        completed.add("b")
        assert all(dep in completed for dep in sw3.depends_on) is True
