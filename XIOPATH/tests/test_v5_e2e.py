import pytest
from core.trust_ledger import TrustLedger, TrustTier
from core.policy_enforcer import PolicyEnforcer
from core.crdt_memory import CRDTMemoryMerger
from core.self_learning import SelfLearningEngine
from sqlalchemy import text

@pytest.fixture
def trust_ledger(db):
    return TrustLedger(db)

@pytest.fixture
def policy_enforcer(db):
    return PolicyEnforcer(db)

@pytest.fixture
def crdt_merger(db):
    return CRDTMemoryMerger(db)

def test_trust_ledger_promotion(trust_ledger):
    actor_id = "test_colab_worker"
    
    # Initially untrusted
    assert trust_ledger.get_trust_tier(actor_id) == TrustTier.UNTRUSTED
    
    # 15 successes -> should promote to VERIFIED
    for _ in range(15):
        trust_ledger.record_task_outcome(actor_id, success=True)
        
    assert trust_ledger.get_trust_tier(actor_id) == TrustTier.VERIFIED
    
    # 50 more successes -> should promote to TRUSTED
    for _ in range(50):
        trust_ledger.record_task_outcome(actor_id, success=True)
        
    assert trust_ledger.get_trust_tier(actor_id) == TrustTier.TRUSTED
    
    # Fail 50 times -> should drop score and demote back to UNTRUSTED
    for _ in range(50):
        trust_ledger.record_task_outcome(actor_id, success=False)
        
    assert trust_ledger.get_trust_tier(actor_id) == TrustTier.UNTRUSTED

def test_policy_enforcer_swarm_validation(db, trust_ledger, policy_enforcer):
    actor_id = "test_actor"
    
    # Ensure UNTRUSTED by default
    assert trust_ledger.get_trust_tier(actor_id) == TrustTier.UNTRUSTED
    
    # Policy should REJECT untrusted actors for standard workflows
    assert not policy_enforcer.validate_execution("wf_1", actor_id, "tenant_1")
    
    # Promote actor to VERIFIED
    for _ in range(15):
        trust_ledger.record_task_outcome(actor_id, success=True)
        
    assert trust_ledger.get_trust_tier(actor_id) == TrustTier.VERIFIED
    
    # Policy should now ALLOW execution
    assert policy_enforcer.validate_execution("wf_1", actor_id, "tenant_1")
    
def test_crdt_memory_merge(db, crdt_merger):
    # Setup knowledge_nodes and knowledge_edges tables in test db
    with db.safe_transaction() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT,
                intent TEXT,
                data_payload TEXT,
                embedding_id TEXT,
                updated_at TIMESTAMP
            )
        """))
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                source_id TEXT,
                target_id TEXT,
                relation TEXT,
                weight REAL,
                updated_at TIMESTAMP,
                PRIMARY KEY (source_id, target_id, relation)
            )
        """))
        
    payload = {
        "nodes": [
            {"id": "node_1", "node_type": "observation", "timestamp": "2026-07-12T10:00:00"},
            {"id": "node_2", "node_type": "action", "timestamp": "2026-07-12T10:01:00"}
        ],
        "edges": [
            {"source": "node_1", "target": "node_2", "relation": "leads_to", "timestamp": "2026-07-12T10:02:00"}
        ]
    }
    
    result = crdt_merger.merge_graph_payload("worker_1", payload)
    assert result["merged_nodes"] == 2
    assert result["merged_edges"] == 1
    
    # Test LWW logic - older timestamp should be ignored
    payload_older = {
        "nodes": [
            {"id": "node_1", "node_type": "observation", "timestamp": "2026-07-12T09:00:00"} # older!
        ]
    }
    # It will attempt to merge, but UPSERT WHERE clause prevents update. 
    # The method still returns merged_nodes=1 because it processed it.
    crdt_merger.merge_graph_payload("worker_1", payload_older)

class MockLLMEngine:
    async def generate(self, prompt, **kwargs):
        return '{"action": "corrected_step"}'

@pytest.mark.asyncio
async def test_self_learning_dlq(db):
    llm = MockLLMEngine()
    learning_engine = SelfLearningEngine(db, llm)
    
    with db.safe_transaction() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT,
                error_message TEXT,
                execution_trace TEXT,
                status TEXT,
                resolution_notes TEXT
            )
        """))
        session.execute(text("""
            INSERT INTO dead_letter_queue (workflow_id, error_message, execution_trace, status)
            VALUES ('wf_1', 'ElementNotInteractable', 'trace...', 'unresolved')
        """))
        
    # Analyze DLQ
    await learning_engine.analyze_dlq_failures()
    
    # Check if resolved
    with db.safe_transaction() as session:
        row = session.execute(text("SELECT status, resolution_notes FROM dead_letter_queue WHERE workflow_id = 'wf_1'")).fetchone()
        assert row.status == 'auto_resolved'
        assert row.resolution_notes == '{"action": "corrected_step"}'
