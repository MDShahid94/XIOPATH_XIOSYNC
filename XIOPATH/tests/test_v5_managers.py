"""
XIOPATH v5.0 — Test Suite
============================
Tests for all v5.0 managers: TypeRegistry, KnowledgeManager,
WorkflowManager, PolicyManager, and MemoryBridge.
"""
import json
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# TYPE REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestTypeRegistry:
    """Tests for the dynamic type system."""

    def test_seed_creates_types(self, type_registry):
        names = type_registry.get_types("actor_type")
        assert "human" in names
        assert "ai" in names
        assert "compute" in names

    def test_validate_valid_type(self, type_registry):
        assert type_registry.is_valid("actor_type", "human") is True

    def test_validate_invalid_type(self, type_registry):
        assert type_registry.is_valid("actor_type", "phantom") is False

    def test_register_custom_type(self, type_registry):
        type_registry.register_type(
            category="actor_subtype",
            name="custom_bot",
            description="A custom bot type",
        )
        assert type_registry.is_valid("actor_subtype", "custom_bot") is True

    def test_list_categories(self, type_registry):
        names = type_registry.get_types("action_type")
        assert "browser" in names
        assert "api_call" in names
        assert "script" in names

    def test_duplicate_registration_ignored(self, type_registry):
        # Re-seeding should not duplicate
        type_registry.seed_builtins()
        names = type_registry.get_types("actor_type")
        human_count = names.count("human")
        assert human_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class TestKnowledgeManager:
    """Tests for universal knowledge/action store."""

    def test_store_and_retrieve(self, knowledge_mgr):
        node_id = knowledge_mgr.store(
            domain="example.com", intent="click_login",
            action_type="browser",
            action_spec={"steps": [{"action": "click", "selector": "#btn"}]},
        )
        assert node_id is not None
        node = knowledge_mgr.get(node_id)
        assert node["domain"] == "example.com"
        assert node["intent"] == "click_login"

    def test_find_by_domain_intent(self, knowledge_mgr):
        knowledge_mgr.store(
            domain="github.com", intent="star_repo",
            action_type="browser",
            action_spec={"steps": [{"action": "click", "selector": ".star-btn"}]},
        )
        results = knowledge_mgr.find("github.com", "star_repo")
        assert len(results) >= 1
        assert results[0]["intent"] == "star_repo"

    def test_deduplication(self, knowledge_mgr):
        id1 = knowledge_mgr.store(
            domain="test.com", intent="dedup_test",
            action_type="browser",
            action_spec={"steps": [{"action": "click"}]},
            owner_actor_id="user1",
        )
        id2 = knowledge_mgr.store(
            domain="test.com", intent="dedup_test",
            action_type="browser",
            action_spec={"steps": [{"action": "click"}]},
            owner_actor_id="user1",
        )
        assert id1 == id2  # Same context_hash → reuse

    def test_soft_delete(self, knowledge_mgr):
        node_id = knowledge_mgr.store(
            domain="del.com", intent="to_delete",
            action_type="browser", action_spec={"steps": []},
        )
        knowledge_mgr.delete(node_id)
        node = knowledge_mgr.get(node_id)
        assert node["status"] == "archived"

    def test_update_fields(self, knowledge_mgr):
        node_id = knowledge_mgr.store(
            domain="upd.com", intent="to_update",
            action_type="browser", action_spec={"steps": []},
        )
        knowledge_mgr.update(node_id, face_value="updated description")
        node = knowledge_mgr.get(node_id)
        assert node["face_value"] == "updated description"

    def test_find_by_lookup_key(self, knowledge_mgr):
        knowledge_mgr.store(
            domain="lookup.com", intent="fast_find",
            action_type="api_call", action_spec={"url": "https://api.test.com"},
        )
        result = knowledge_mgr.find_by_lookup_key("lookup.com::fast_find::api_call")
        assert result is not None
        assert result["intent"] == "fast_find"

    def test_voting_changes_score(self, knowledge_mgr):
        node_id = knowledge_mgr.store(
            domain="vote.com", intent="vote_test",
            action_type="browser", action_spec={"steps": []},
        )
        before = knowledge_mgr.get(node_id)
        result = knowledge_mgr.submit_vote(node_id, voter_actor_id="voter1", raw_vote=1.0)
        assert result["bayesian_score"] != before["bayesian_score"]

    def test_stats(self, knowledge_mgr):
        knowledge_mgr.store(
            domain="stats.com", intent="stat_test",
            action_type="browser", action_spec={"steps": []},
        )
        stats = knowledge_mgr.get_stats()
        assert stats["total_nodes"] >= 1
        assert "browser" in stats["by_action_type"]

    def test_gc_archives_old_nodes(self, knowledge_mgr):
        # GC should not crash on empty DB
        count = knowledge_mgr.run_garbage_collection()
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# WORKFLOW MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowManager:
    """Tests for persistent workflow definitions and executions."""

    def test_create_workflow(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Test WF", creator_id="actor1",
            steps=[{"order": 1, "action": "navigate"}],
        )
        assert wf_id is not None
        wf = workflow_mgr.get_workflow(wf_id)
        assert wf["name"] == "Test WF"
        assert wf["state"] == "draft"

    def test_activate_workflow(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Activate Me", creator_id="actor1",
            steps=[{"order": 1}],
        )
        workflow_mgr.activate_workflow(wf_id)
        wf = workflow_mgr.get_workflow(wf_id)
        assert wf["state"] == "active"

    def test_fork_workflow(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Original", creator_id="actor1",
            steps=[{"order": 1, "action": "click"}],
        )
        forked_id = workflow_mgr.fork_workflow(wf_id, "actor2", "My Fork")
        assert forked_id is not None
        forked = workflow_mgr.get_workflow(forked_id)
        assert "My Fork" in forked["name"]

    def test_execution_lifecycle(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Lifecycle", creator_id="actor1",
            steps=[{"order": 1}, {"order": 2}],
        )
        exec_id = workflow_mgr.start_execution(wf_id, "actor1")
        ex = workflow_mgr.get_execution(exec_id)
        assert ex["status"] == "running"
        assert ex["total_steps"] == 2

        # Record step
        workflow_mgr.record_step_result(exec_id, 0, {"ok": True})
        ex = workflow_mgr.get_execution(exec_id)
        assert ex["current_step"] == 1

        # Complete
        workflow_mgr.complete_execution(exec_id, {"result": "done"})
        ex = workflow_mgr.get_execution(exec_id)
        assert ex["status"] == "completed"

    def test_fail_execution(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Fail WF", creator_id="a1", steps=[{"order": 1}],
        )
        exec_id = workflow_mgr.start_execution(wf_id, "a1")
        workflow_mgr.fail_execution(exec_id, "timeout")
        ex = workflow_mgr.get_execution(exec_id)
        assert ex["status"] == "failed"
        assert ex["error"] == "timeout"

    def test_pause_resume(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Pause WF", creator_id="a1", steps=[{"order": 1}],
        )
        exec_id = workflow_mgr.start_execution(wf_id, "a1")
        workflow_mgr.pause_execution(exec_id)
        assert workflow_mgr.get_execution(exec_id)["status"] == "paused"
        workflow_mgr.resume_execution(exec_id)
        assert workflow_mgr.get_execution(exec_id)["status"] == "running"

    def test_workflow_stats(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(
            name="Stats WF", creator_id="a1", steps=[{"order": 1}],
        )
        exec_id = workflow_mgr.start_execution(wf_id, "a1")
        workflow_mgr.complete_execution(exec_id)
        stats = workflow_mgr.get_workflow_stats(wf_id)
        assert stats["total_executions"] == 1
        assert stats["by_status"]["completed"] == 1

    def test_list_workflows(self, workflow_mgr):
        workflow_mgr.create_workflow(name="WF A", creator_id="a1", steps=[{}])
        workflow_mgr.create_workflow(name="WF B", creator_id="a1", steps=[{}])
        wfs = workflow_mgr.list_workflows(creator_id="a1")
        assert len(wfs) >= 2

    def test_delete_workflow(self, workflow_mgr):
        wf_id = workflow_mgr.create_workflow(name="Del WF", creator_id="a1", steps=[{}])
        workflow_mgr.delete_workflow(wf_id)
        wf = workflow_mgr.get_workflow(wf_id)
        assert wf["state"] == "archived"


# ═══════════════════════════════════════════════════════════════════════════
# POLICY MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class TestPolicyManager:
    """Tests for execution sandboxing."""

    def test_create_and_get_policy(self, policy_mgr):
        pid = policy_mgr.create_policy(
            name="test_policy",
            allow_browser=True, allow_network=False,
            max_steps=50,
        )
        policy = policy_mgr.get_policy(pid)
        assert policy["name"] == "test_policy"
        assert policy["allow_browser"] == 1
        assert policy["allow_network"] == 0

    def test_check_permission(self, policy_mgr):
        pid = policy_mgr.create_policy(
            name="perm_check", allow_browser=True, allow_llm=False,
        )
        assert policy_mgr.check_permission(pid, "browser") is True
        assert policy_mgr.check_permission(pid, "llm") is False

    def test_validate_execution_allowed(self, policy_mgr):
        pid = policy_mgr.create_policy(
            name="val_allow", allow_browser=True, max_steps=100,
        )
        result = policy_mgr.validate_execution(pid, "browser", step_count=5)
        assert result["allowed"] is True

    def test_validate_execution_step_exceeded(self, policy_mgr):
        pid = policy_mgr.create_policy(name="val_steps", max_steps=10)
        result = policy_mgr.validate_execution(pid, "browser", step_count=15)
        assert result["allowed"] is False
        assert "Step limit" in result["reason"]

    def test_validate_execution_action_blocked(self, policy_mgr):
        pid = policy_mgr.create_policy(
            name="val_blocked", allow_subprocess=False,
        )
        result = policy_mgr.validate_execution(pid, "script", step_count=1)
        assert result["allowed"] is False

    def test_domain_blocking(self, policy_mgr):
        pid = policy_mgr.create_policy(
            name="domain_block",
            blocked_domains=["localhost", "*.internal"],
        )
        assert policy_mgr.check_domain(pid, "google.com") is True
        assert policy_mgr.check_domain(pid, "localhost") is False
        assert policy_mgr.check_domain(pid, "db.internal") is False

    def test_list_policies(self, policy_mgr):
        policy_mgr.create_policy(name="list_test_1")
        policy_mgr.create_policy(name="list_test_2")
        policies = policy_mgr.list_policies()
        assert len(policies) >= 2


# ═══════════════════════════════════════════════════════════════════════════
# MEMORY BRIDGE (backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════

class TestMemoryBridge:
    """Tests for MemoryManager → KnowledgeManager adapter."""

    def test_save_and_lookup(self, memory_bridge):
        memory_bridge.save_new_action(
            url="https://github.com/login",
            intent="gh_login",
            face_value={"description": "Click login"},
            place_value={"selector": "#btn"},
            action_type="click",
            action_params={"node_id": 42},
        )
        result = memory_bridge.lookup_action("https://github.com/login", "gh_login", {})
        assert result is not None
        assert result["action_type"] == "click"
        assert result["action_params"]["node_id"] == 42

    def test_promote(self, memory_bridge, knowledge_mgr):
        memory_bridge.save_new_action(
            url="https://test.com", intent="promote_test",
            face_value={}, place_value={},
            action_type="click", action_params={},
        )
        result = memory_bridge.lookup_action("https://test.com", "promote_test", {})
        memory_bridge.promote_client_secondary(result["id"])
        node = knowledge_mgr.get(result["id"])
        assert node["tier"] == "client_primary"

    def test_demote(self, memory_bridge, knowledge_mgr):
        memory_bridge.save_new_action(
            url="https://test.com", intent="demote_test",
            face_value={}, place_value={},
            action_type="click", action_params={},
        )
        result = memory_bridge.lookup_action("https://test.com", "demote_test", {})
        original_score = knowledge_mgr.get(result["id"])["bayesian_score"]
        memory_bridge.demote_client_secondary(result["id"])
        new_score = knowledge_mgr.get(result["id"])["bayesian_score"]
        assert new_score < original_score

    def test_get_available_intents(self, memory_bridge):
        memory_bridge.save_new_action(
            url="https://intents.com", intent="intent_a",
            face_value={}, place_value={},
            action_type="click", action_params={},
        )
        intents = memory_bridge.get_available_intents("https://intents.com")
        assert "intent_a" in intents

    def test_context_hash(self, memory_bridge):
        h = memory_bridge._generate_context_hash("desktop", "mac", "Chrome", "1920x1080")
        assert isinstance(h, str) and len(h) == 8

    def test_workflow_graph(self, memory_bridge):
        memory_bridge.save_new_action(
            url="https://graph.com", intent="step1",
            face_value={}, place_value={},
            action_type="click", action_params={},
        )
        graph = memory_bridge.get_workflow_graph("https://graph.com", "step1", {})
        assert graph["total"] >= 1
        assert graph["nodes"][0]["intent"] == "step1"
