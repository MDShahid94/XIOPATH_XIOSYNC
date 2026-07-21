# Current Position
- **Phase**: Phase 3 — Workflows & durable execution (control-plane side)
- **Step**: Step 2 is **COMPLETE**. Phase 3 is COMPLETE. Ready for Phase 4.
- **Next Action**: Phase 4 Step 1 — Worker enrollment flow; per-worker short-lived
  capability-scoped credentials (doc 05, doc 07 §2); trust tiers with proof-based
  promotion/demotion (INV-TRUST-1/2).
- **Last updated**: Session 033 (2026-07-21)
- **Orchestrator**: XIOV0 (v0-agentic-pipeline)

## Phase 3 Complete
| Component | Status |
|-----------|--------|
| workflows/workflow_runs/tasks/dead_letters schema (0007) | ✅ |
| domain/workflows.py — DAG validation + lease predicates | ✅ |
| services/workflows.py — full lease + DLQ governance | ✅ |
| INV-WF-1: cyclic spec rejected on publish | ✅ |
| INV-EXEC-2: idempotent task completion | ✅ |
| INV-DLQ-1/2/3: governed DLQ, no auto-resolve | ✅ |
| Integration tests — Step 1 coverage | ✅ |
| Integration tests — Step 2 lease+DLQ coverage | ✅ |

## Migration Chain
| Revision | Name | Phase |
|----------|------|-------|
| 0001 | baseline | Phase 0 |
| 0002 | identity_tables | Phase 1 |
| 0003 | rls_empty_guc_fail_closed | Phase 1 |
| 0004 | authorization_spine | Phase 1 |
| 0005 | ontology_type_registry | Phase 2 |
| 0006 | events_memory_triggers | Phase 2 |
| 0007 | workflows_tasks_dlq | Phase 3 |
