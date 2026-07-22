## TASK
Phase 4 Exit Gate — Implement worker-isolation tests to prove that a worker credential cannot mint a user/admin token, a below-tier worker cannot execute a tier-gated grant, and a compromised volunteer worker cannot mutate global/cross-actor state.

## PROJECT CONTEXT
Type: python project (fastapi, sqlalchemy, alembic, pytest)

CRITICAL: THIS IS A PURE PYTHON BACKEND PROJECT.
DO NOT GENERATE ANY NEXT.JS, REACT, OR UI CODE.
DO NOT CREATE `app/`, `components/`, OR `package.json`.
ONLY WRITE CODE MATCHING THIS PROJECT TYPE.

Migration head: `0008_worker_enrollment` (alembic)
Migration dir: `xiosync/persistence/migrations/versions`

Test dir: `tests`

## KEY IMPORTS (use these, do not reinvent)
```python
from xiosync.platform.ids import new_id
from alembic import op
from sqlalchemy import text
from xiosync.domain.context import MembershipRole, OrgContext, PlatformRole
from xiosync.domain.context import OrgContext
from sqlalchemy import create_engine, text
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, HTTPException, Depends
from xiosync.persistence.tenancy import org_scoped_session
from sqlalchemy.engine import Engine
```

## GUARDRAILS (from xiosync-blueprint/README.md)
- *MUST**, **MUST NOT**, **SHOULD**, and **MAY** are used in the RFC 2119 sense.
- **Capability grants are stored but never checked** at execution time; the
- foundation, port the good ideas, and never reintroduce the compromises.**
- approval. Untrusted workers never mutate global state.
- | 02 | [`02-forensic-audit-xiopath.md`](./02-forensic-audit-xiopath.md) | Complete catalog of every remediation scope found in XIOPATH — critical and non-critical — each with evidence and the investigation that surfaced it. |
- 2. **Never reintroduce a legacy pattern** listed in document 02. If you find
- 4. **Record decisions** in [`DECISIONS.md`](./DECISIONS.md). Do not bury durable
- not run, record the blocker verbatim — never claim a green you did not see.

## VERIFICATION
- No external database available in V0 sandbox.
- Validate via: static analysis, lint, import checks.
- Do NOT try to provision external databases (Neon, Supabase, etc.).

## COMPLETED STEPS (do not redo these)
- [x] feat: Phase 4 Step 2 — WorkerService methods and credential integration tests
- [x] feat: Phase 4 Step 3 — Execution-plane API endpoints and DLQ governance stubs implemented and unit-tested.
- [x] feat: Phase 4 Step 4 — Task credential minting (INV-TASK-SEC-1/2)
- [x] chore: remove stray V0 Next.js sandbox pollution (app, components, lib, package.json, etc.)
- [x] chore: add root-level V0 sandbox pollution guards to .gitignore
- [x] chore: remove obsolete manual phase3_prompt.txt scratchpad
- [x] fix: E501 line length in workflows.py
- [x] chore: apply V0 generation (job 77558179)
- [x] chore: fix linting after V0 generation
- [x] feat: Phase 4 Step 2 — WorkerService methods and credential integration tests

## EXISTING FILES (do not recreate these)
```
.github/
  workflows/
    ci.yml
continuity/
  HANDOFF-LOG.md
  SESSION-PROTOCOL.md
  STATE.md
tests/
  integration/
    __init__.py
    conftest.py
    test_api_auth.py
    test_authorization_integration.py
    test_events_immutability.py
    test_events.py
    test_identity_security.py
    test_identity_session_lifecycle.py
    test_lifecycle.py
    test_memory_versioning.py
    test_migration_chain.py
    test_ontology_graph.py
    test_ontology.py
    test_operations.py
    test_tenancy_boundary.py
    test_workers_integration.py
    test_workflows.py
  unit/
    __init__.py
    test_api_execution.py
    test_authorization_policy.py
    test_domain_context.py
    test_persistence_database.py
    test_persistence_models.py
    test_platform_config.py
    test_platform_primitives.py
    test_platform_task_credentials.py
    test_platform_telemetry.py
    test_platform_tokens.py
    test_services_identity.py
    test_workers_domain.py
tools/
  __init__.py
XIOPATH/
  .github/
    workflows/
      ci.yml
  alembic/
    versions/
      14c2c1f29abe_add_swarm_intelligence_tables.py
      5f7f5f1793c7_baseline_current_schema.py
      9fc8d1c36f34_add_extension_4_tables.py
      a05b6e2f8d34_add_workflows_tables.py
      a3b7e2d5f819_add_marketplace_tables.py
      b16c7f3a9e45_add_policies_extend_marketplace.py
      b50a0c7e3d12_v5_0_rename_agent_to_actor.py
      c61f2a8b4e90_add_type_registry_table.py
      d677c600b9c0_add_core_ontology_7_tables.py
      d72e3b9a5c01_add_auth_identities_table.py
      e83f4c0b6d12_add_organizations_tables.py
      f94a5d1c7e23_add_knowledge_nodes_table.py
... and 362 more files
```
