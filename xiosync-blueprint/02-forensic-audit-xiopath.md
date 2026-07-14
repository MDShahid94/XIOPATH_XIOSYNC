# 02 — Forensic Audit of XIOPATH

> Normative reference catalog. Every finding below was verified against the
> actual XIOPATH source (~38,485 LOC of Python/JS/TS across FastAPI, core
> services, React/Vite, Alembic, and a Manifest V3 extension). Each finding lists
> **evidence** (file + the observed code), **why it matters**, and the
> **XIOSYNC remediation** that supersedes it.
>
> This document is the "never reintroduce this" list. If a XIOSYNC change matches
> a legacy pattern here, it is a regression.

Severity legend:
- **C (Critical)** — breaks tenant isolation, authz, data integrity, or will fail
  at runtime. Blocks any public deployment.
- **H (High)** — structural defect that forces legacy fighting or hides breakage.
- **M (Medium)** — correctness/operability gap that degrades production quality.
- **L (Low)** — cleanliness/consistency issue; cheap to prevent in a rebuild.

---

## Part A — Critical findings

### C1 — Tenant middleware runs before auth; stamps a placeholder `"pending"`
**Evidence:** `api/middleware/tenant_scope.py`. For non-public paths it reads
`request.state.user`, which is not yet populated (JWT validation happens later in
route dependencies), so it falls through to:
```python
request.state.tenant = TenantContext(user_id="pending", role="user")
```
**Why it matters:** The object that is supposed to *scope every tenant query*
carries a placeholder identity for authenticated requests. Any handler trusting
`request.state.tenant` operates without a real tenant. This is isolation in name
only.
**XIOSYNC remediation:** Identity and organization are resolved in a single
authentication step that runs *before* any tenant-scoped logic, and the resolved
`organization_id` is a required, non-defaulted value on the request context. No
`"pending"` sentinel exists. See [`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md).

### C2 — No `organization_id` on core ontology rows
**Evidence:** `core/ontology_models.py` — `Actor`, `Operation`, `ActorEdge`,
`Capability`, `CapabilityGrant`, `Event` dataclasses and their `to_db_row()`
methods contain **no** `organization_id` field. Tenancy is implied only through
mutable `parent_id` chains.
**Why it matters:** Without an immutable tenant key on every row, query isolation
cannot be enforced at the data layer. `parent_id` can change and does not
constrain `WHERE` clauses. This is the root cause that makes C1 unfixable in place.
**XIOSYNC remediation:** Every tenant-bearing entity carries an immutable,
indexed `organization_id`, set at creation and never updated. Repository methods
*require* organization context as a non-optional parameter. See
[`06-persistence-schema.md`](./06-persistence-schema.md).

### C3 — Capability grants stored but never enforced at execution
**Evidence:** `core/ontology_ops.py` writes to `capability_grants`, but the
execution gate `core/policy_enforcer.py::validate_execution()` never reads them.
Its actual logic:
```python
if tenant_id == "suspended_tenant":
    return False
...
if action_type == "phantom_harvesting" and tenant_id != "admin":
    return False
```
**Why it matters:** Authorization is theater. A stored grant that is never checked
is documentation, and the "enforcement" is hardcoded string matching that no real
tenant will ever match.
**XIOSYNC remediation:** A single policy decision point answers *"may actor A
perform operation O using capability C on resource R in organization T under
constraints K?"* by reading real grants, and returns an auditable decision id.
Every execution path calls it. See [`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md).

### C4 — CORS wildcard with credentials
**Evidence:** `api/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", ...],
    allow_origin_regex=".*",          # defeats the allowlist above
    allow_credentials=True,
    ...
)
```
**Why it matters:** `allow_origin_regex=".*"` with `allow_credentials=True` lets
any origin make credentialed requests. The explicit allowlist next to it is dead
code. This is a textbook CSRF/credential-exposure hole.
**XIOSYNC remediation:** A single explicit origin allowlist sourced from
configuration per environment. No regex wildcard. Credentialed CORS only for
enumerated origins. See [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md).

### C5 — Schema ownership split between Alembic and runtime `_init_db()`
**Evidence:** `core/database.py::_init_db()` issues `CREATE TABLE IF NOT EXISTS`
for `memory_nodes`, `client_votes`, `users`, `scheduled_jobs`,
`marketplace_listings`, etc. `core/trust_ledger.py` and `phantom/vault.py` also
create tables at runtime. Meanwhile `alembic/versions/*` defines an overlapping
schema.
**Why it matters:** Two authorities produce drift. The database a test sees, the
database a fresh install builds, and the database migrations describe can all
differ. Nothing is the source of truth.
**XIOSYNC remediation:** Migrations are the *only* schema authority. Application
code never creates, alters, or probes tables. See [`06-persistence-schema.md`](./06-persistence-schema.md).

### C6 — Migrations run per API replica at startup, hardcoded to SQLite
**Evidence:** `api/main.py` lifespan:
```python
engine = create_engine("sqlite:///data/xiopath.db")
...
command.upgrade(alembic_cfg, "head")
...
db = DatabaseManager(Path("data/xiopath.db"))
```
The Postgres branch in `DatabaseManager` is never used by the startup migration,
which is pinned to a local SQLite file. `start.sh` also runs `alembic upgrade
head` independently.
**Why it matters:** In a horizontally scaled deployment, every replica races to
migrate; and it migrates the wrong database (SQLite) even when `DATABASE_URL`
points at Postgres. Data written to Postgres and schema applied to SQLite diverge
completely.
**XIOSYNC remediation:** Migration is a discrete deploy step against the
configured `DATABASE_URL`, run exactly once per release, never inside the API
process. The API refuses to start if the DB is not at the expected head. See
[`06-persistence-schema.md`](./06-persistence-schema.md) and [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md).

### C7 — Phantom bridge wired to nonexistent fields; will raise at runtime
**Evidence:** `phantom/ontology_bridge.py` imports `Operation` but constructs
`AgentOperation(agent_id=..., ...)`, builds `Event(agent_id=...)` while `Event`
expects `actor_id`, creates actors with `agent_type`/`agent_subtype` while the
model expects `actor_type`/`actor_subtype`, uses lifecycle states
(`provisioning`, `aging`, `locked`, `recovering`) and actor types (`tool`,
`ecosystem`) and edge types (`donates_to`, `deployed_on`) absent from the
built-in vocabularies in `core/ontology_models.py`.
**Why it matters:** These calls raise `TypeError`/constraint errors at runtime, or
silently write records the ontology does not recognize. A whole subsystem is
wired to a schema that no longer exists.
**XIOSYNC remediation:** Phantom (renamed and re-scoped) speaks the one canonical
vocabulary sourced from the authoritative type registry, and every registration/
lifecycle method has a contract test. See [`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md).

### C8 — No session revocation, refresh rotation, or password-change invalidation
**Evidence:** `api/routers/session.py` exposes only `list`, `get`, and
`cancel` (for execution sessions, not auth sessions). `api/routers/auth.py`
issues 60-minute HS256 access tokens with a `jti` but there is no refresh token,
no revocation list, no rotation, and no mechanism to invalidate tokens on
password change or logout.
**Why it matters:** A leaked token is valid until expiry with no kill switch.
Password changes do not log out active sessions. There is no server-side session
lifecycle.
**XIOSYNC remediation:** Short-lived access tokens plus rotating refresh tokens
with a server-side session record that can be revoked; password change and logout
invalidate all sessions for the identity. See [`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md).

### C9 — Autonomous DLQ correction mutates state without approval
**Evidence:** `core/self_learning.py::analyze_dlq_failures()` queries the LLM for
a correction and immediately writes:
```python
session.execute(text("UPDATE dead_letter_queue SET status='auto_resolved', resolution_notes=:notes ..."))
```
`ARCHITECTURE.md` §5 confirms the intent that the platform "dynamically proposes a
corrected workflow spec" and "learns from its mistakes" autonomously.
**Why it matters:** Model output directly changes durable state with no
validation, no human gate, and no rollback path. Combined with untrusted workers,
this is an autonomous mutation channel.
**XIOSYNC remediation:** Corrections are versioned *proposals* moving through
`failure → diagnosis → proposed patch → validation → approval → canary →
promotion`. Untrusted actors never mutate global state. See
[`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md).

### C10 — Plugins executed in-process via `import_module`, no sandbox
**Evidence:** `core/plugin_manager.py::execute_plugin()` calls
`importlib.import_module(module_name)` and invokes the plugin's `run()` in the API
process. The allowlist is optional ("when populated, only listed plugins can
execute").
**Why it matters:** Arbitrary plugin code runs with the API's full privileges,
secrets, and network. An empty allowlist means no restriction. Marketplace-
installed plugins would be remote code execution.
**XIOSYNC remediation:** Plugins run out-of-process in a sandbox with an explicit
capability grant, network allowlist, and no ambient access to core secrets.
Installation requires approval. See [`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md).

---

## Part B — High findings

### H1 — Two competing vocabularies (`agent` vs `actor`) behind aliases
**Evidence:** `core/ontology_models.py` ends with `Agent = Actor`,
`AgentOperation = Operation`, `AgentEdge = ActorEdge`, `Tool = Capability`,
`AgentProfile = ActorProfile`, `AgentEnvironment = Bundle`. Routers exist in
pairs: `api/routers/agents_v2.py` **and** `actors_v2.py`; `agent.py` **and**
`actions.py`; `workflows.py` **and** `workflows_v2.py`. Migration
`b50a0c7e...rename_agent_to_actor` renames some tables but the code keeps both.
**Why it matters:** Aliases let drift continue silently. New code picks either
name; subsystems diverge (see C7). Two routers for one concept double the attack
surface and the maintenance cost.
**XIOSYNC remediation:** One canonical vocabulary — `Actor`, `Operation`,
`Capability`, `Edge`, `Event`, `Grant` — defined once in
[`GLOSSARY.md`](./GLOSSARY.md). No aliases, no `_v2` twins. See [`03-ontology-formal-spec.md`](./03-ontology-formal-spec.md).

### H2 — Database↔model drift proven by test fabrication
**Evidence:** `tests/conftest.py` manually issues `CREATE TABLE IF NOT EXISTS`
for `type_registry`, `actors`, `actor_edges`, `knowledge_nodes`, `workflows`,
etc., instead of running the Alembic chain. The original ontology migration
created `agents`, `agent_operations`, `tool_registry`, `event_log`,
`runtime_args`, `tool_id`; current code expects `actors`, `operations`,
`capabilities`, `events`, `runtime_state`, `capability_id`.
**Why it matters:** Tests validate against hand-built tables that may not match
what migrations produce. Green tests can coexist with a broken migration chain.
**XIOSYNC remediation:** Tests upgrade an empty database through the full
migration chain and run against the result. Fabricated schemas are banned. See
[`06-persistence-schema.md`](./06-persistence-schema.md).

### H3 — "Dynamic ontology" is partly hardcoded
**Evidence:** `ARCHITECTURE.md` §1 says the `TypeRegistry` is authoritative, but
`core/ontology_models.py` hardcodes `LIFECYCLE_STATES`, `ACTOR_TYPES`,
`ACTOR_SUBTYPES`, `OPERATION_TYPES`, `EDGE_TYPES`, `EVENT_TYPES` as module-level
sets, and subsystems (Phantom) already use values outside them (C7).
**Why it matters:** Two sources of truth for "what types exist" guarantee
disagreement. The registry is undermined by the constants that compete with it.
**XIOSYNC remediation:** One type-registry service with namespaced, versioned,
validated type definitions; constants exist only to *bootstrap* the registry, not
to compete with it at runtime. See [`03-ontology-formal-spec.md`](./03-ontology-formal-spec.md).

### H4 — Auth identity vs ontology identity not unified
**Evidence:** `api/routers/auth.py` creates both an `auth_identity` and a
corresponding `actor` on signup, with the JWT carrying both `sub` and `auth_id`,
but there is no enforced 1:1 mapping, no defined relationship between an
`auth_identity`, its `HumanActor`, and an `Organization`, and `role` is a single
overloaded string.
**Why it matters:** Ambiguity about "who is this token" and "which org" leads to
inconsistent authorization. A single `role` field cannot represent platform
admin, org membership, and execution capability simultaneously.
**XIOSYNC remediation:** Explicit model: `AuthIdentity 1—1 HumanActor`,
`HumanActor —member of→ Organization`, `Session authenticates AuthIdentity`,
`Grant authorizes Actor`. Roles are scoped, not overloaded. See
[`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md).

### H5 — "DAG" claim not enforced; generic edges allow cycles
**Evidence:** `ARCHITECTURE.md` §2 calls workflows DAGs, and describes the graph
as version-controlled, but `ActorEdge` in `core/ontology_models.py` is a generic
directed edge with `bidirectional` and no acyclicity constraint or validation.
`edge_type` includes `collaborates_with`, which is naturally cyclic.
**Why it matters:** Calling the whole graph a DAG is false. Workflow execution
that assumes acyclicity can infinite-loop on a relationship cycle.
**XIOSYNC remediation:** Separate graphs with distinct rules — hierarchy
(acyclic), workflow (acyclic, validated on write), relationship (cycles allowed),
dependency (validated per edge semantics). See [`03-ontology-formal-spec.md`](./03-ontology-formal-spec.md).

### H6 — "Append-only" events are ordinary mutable tables
**Evidence:** `Event` in `core/ontology_models.py` is described as an "append-only
telemetry/audit event," but it is a normal table with no update/delete guard, no
integrity hash, and the original migration had weak/missing referential
constraints.
**Why it matters:** An audit stream that can be silently updated or deleted is not
an audit stream. Compliance and forensics depend on immutability.
**XIOSYNC remediation:** No application update/delete path, restricted DB grants,
optional hash-chaining for high-assurance events, retention/redaction rules, and
tenant+correlation indexes. See [`06-persistence-schema.md`](./06-persistence-schema.md).

### H7 — Worker credentials are the shared JWT secret, long-lived
**Evidence:** `core/worker_boot_integration.py` signs a worker token with
`self.worker_secret or os.environ.get("XIOPATH_JWT_SECRET", "xiopath-dev-secret-change-in-production")`;
`colab_worker.py` hardcodes `WORKER_ID` and a blank `WORKER_AUTH_SECRET` "@param"
that "must match XIOPATH_JWT_SECRET or WORKER_SECRET on server."
**Why it matters:** Workers hold (or share) the platform's signing secret. A
compromised volunteer worker can mint any token, including admin. There is no
enrollment, no per-worker scoped credential, no expiry.
**XIOSYNC remediation:** Workers enroll and receive short-lived, per-worker,
capability-scoped credentials distinct from the user JWT secret; revocable
independently. See [`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md).

### H8 — Seed creates a "Super Admin" ontology actor
**Evidence:** `api/main.py` lifespan calls `ontology.seed_initial_actors()`;
XIOPATH's seed creates a conceptual "Super Admin" actor automatically at startup.
**Why it matters:** A privileged-sounding actor exists without an authenticated
human behind it, and can be confused with a real administrator, blurring the
identity model.
**XIOSYNC remediation:** Seed only a neutral system-root/bootstrap principal. The
first real administrator is linked through an explicit, one-time, audited
bootstrap flow. See [`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md).

### H9 — Local file secret storage as the secret manager
**Evidence:** `core/secret_manager.py` stores secrets in `data/secrets.json` with
a Fernet key written to `data/.vault_key` (chmod 600). `phantom/vault.py` creates
its own `phantom_identities`/`browser_profiles`/`vault_log` tables at runtime.
**Why it matters:** Secrets and their decryption key live side-by-side on the same
local disk; anyone with filesystem access has both. This does not survive a
multi-replica or containerized deployment and is not a real KMS boundary.
**XIOSYNC remediation:** Secrets go through a managed secret backend
(env/KMS/managed vault) with the key material never colocated with ciphertext on
app disk. Phantom secrets stay behind a hardened boundary. See
[`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md) and [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md).

---

## Part C — Medium findings

### M1 — Rate limiter is per-process in-memory
**Evidence:** `api/middleware/rate_limiter.py` uses an in-memory `defaultdict`
token bucket; its own docstring says "For multi-instance deployments, swap the
`_buckets` dict for a Redis backend."
**Why it matters:** With N replicas, effective limits are N× the configured value,
and limits reset on restart. Not a real control under scale.
**XIOSYNC remediation:** Shared-store rate limiting (Redis or equivalent) keyed by
identity/org, consistent across replicas. See [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md).

### M2 — Frontend tokens in `localStorage`, token in WS query string
**Evidence:** `frontend/src/lib/api.js` reads/writes `localStorage.getItem('xp_token')`;
`frontend/src/stores/wsStore.js` connects with `?token=${token}` in the URL.
**Why it matters:** `localStorage` tokens are exposed to any XSS; tokens in URLs
leak into logs, proxies, and history.
**XIOSYNC remediation:** HTTP-only, secure, same-site cookies for session
transport, or a strictly memory-held access token with silent refresh; WS auth via
a subprotocol/handshake, not query string. See [`08-frontend-contract.md`](./08-frontend-contract.md).

### M3 — Duplicated/overlapping routers and API clients
**Evidence:** `agents_v2.py`/`actors_v2.py`, `workflows.py`/`workflows_v2.py`,
`agent.py`/`actions.py`; frontend `lib/api.js` and `lib/api-v2.js`.
**Why it matters:** Duplicate surface = duplicate bugs, unclear contract, and
double the security review.
**XIOSYNC remediation:** One router per resource, one generated API client from
the OpenAPI contract. See [`04-target-architecture.md`](./04-target-architecture.md) and [`08-frontend-contract.md`](./08-frontend-contract.md).

### M4 — CI proves syntax and imports, not behavior or security
**Evidence:** `.github/workflows/ci.yml` runs `python -m compileall` and an import
smoke check, then a test suite that (per H2) uses fabricated tables. No
migration-chain test, no cross-tenant test, no container smoke test, no coverage
gate.
**Why it matters:** Green CI does not mean the schema, isolation, or authz work.
**XIOSYNC remediation:** Blocking CI gates: lint/type, migration up/down,
cross-tenant security tests, contract tests, container smoke test, coverage
threshold. See [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md) and [`11-acceptance-gates.md`](./11-acceptance-gates.md).

### M5 — Broad `except Exception` swallowing at startup and in ops
**Evidence:** `api/main.py` wraps migration, ontology seed, type-registry seed,
and orchestrator init each in `try/except Exception` that only logs a warning and
continues. Fresh installs boot "successfully" with missing tables.
**Why it matters:** The system starts in a broken state and reports success,
masking exactly the failures that matter most.
**XIOSYNC remediation:** Startup preconditions (DB at head, required types
present) are hard checks that fail fast. Only genuinely optional subsystems
degrade, and they report degraded health. See [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md).

### M6 — Fallback-to-plaintext crypto and best-effort UUIDv7
**Evidence:** `core/secret_manager.py` "falls back to plaintext if cryptography
not installed"; `core/ontology_models.py` hand-rolls `uuid7()` and `auth.py` does
`try: uuid.uuid7() except AttributeError: uuid.uuid4()`.
**Why it matters:** Silent plaintext fallback is a security cliff; inconsistent ID
generation undermines the "time-sortable" guarantee the schema relies on.
**XIOSYNC remediation:** Crypto is a hard dependency; absence is a startup failure,
never plaintext. One vetted UUIDv7 implementation used everywhere. See
[`06-persistence-schema.md`](./06-persistence-schema.md).

### M7 — Health endpoint reports table existence, not readiness
**Evidence:** `api/routers/health.py` checks for the presence of tables like
`capability_grants`, `events`, `type_registry`, `auth_identities`.
**Why it matters:** "Tables exist" is not "the app can serve": it ignores
migration head, dependency reachability, and degraded subsystems.
**XIOSYNC remediation:** Distinct `live` (process up) and `ready` (DB at head,
dependencies reachable, required types seeded) probes. See [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md).

---

## Part D — Low findings

- **L1 — Naming sprawl in phases.** Files/tests are labeled by "phase" (`test_phase_e/m/s/w`, "Phase M.6", "Phase S", "Phase X") rather than by capability. XIOSYNC names things by domain concept, not build phase.
- **L2 — Scratch/utility scripts committed to root.** `scratch_download.py`, `scratch_download_solutions.py`, `heal_memory.py`, `verify_*.py` live at repo root. XIOSYNC keeps a clean root; utilities live under `scripts/` and are tested or removed.
- **L3 — Mixed docstring provenance.** Docstrings reference internal phase codes and TODO-style fixes (e.g. "C9 Fix", "E-15", "F-20"), which are meaningless without the tracker. XIOSYNC documents behavior, not ticket numbers.
- **L4 — Default dev secret embedded in code.** `"xiopath-dev-secret-change-in-production"` appears as a literal default in multiple files. XIOSYNC has no embedded secret defaults; missing secrets fail fast in every environment.
- **L5 — Two lockfiles / package managers in frontend.** `frontend/` ships both `package-lock.json` and `pnpm-lock.yaml`. XIOSYNC pins exactly one package manager.

---

## Part E — What XIOPATH got right (port these forward)

The rebuild is not a repudiation. These ideas are sound and MUST be preserved in
XIOSYNC — correctly enforced this time:

1. **The unifying graph.** One model spanning identity, capability, execution,
   memory, and provenance is the right abstraction.
2. **Three primitives.** Identity (Actor), Knowledge (Memory), Action (Capability)
   is a clean conceptual spine.
3. **Operations as first-class lifecycle records** (`proposed → designing →
   implementing → validating → active`) with initiator, collaborators, rationale,
   artifacts, outcome, and parent — excellent provenance design.
4. **Events as a telemetry/audit stream** — right idea, needs real immutability.
5. **Capability + Grant separation** — the model is correct; it just needs to be
   *checked*.
6. **Trust tiers for workers** — a sensible basis for zero-trust worker
   governance, once credentials and enforcement are real.
7. **Control-plane / execution-plane split** — offloading heavy work to durable
   workers is the right architecture.
8. **Type registry concept** — dynamic, versioned types are valuable once they are
   the *single* authority.
9. **Phantom-as-isolated-plugin intent** — the *boundary* is the right design;
   it simply was never enforced.
10. **Bundles / portable runtime environments** and **DLQ-based learning** — both
    worth keeping as *governed* features.

---

## Part F — Traceability index (finding → remediation doc)

| Finding | Severity | Remediation home |
|---|---|---|
| C1 tenant placeholder | C | 05 |
| C2 no organization_id | C | 06 |
| C3 unchecked grants | C | 05 |
| C4 CORS wildcard | C | 09 |
| C5 split schema authority | C | 06 |
| C6 startup/SQLite migration | C | 06, 09 |
| C7 Phantom field mismatch | C | 03, 07 |
| C8 no session revocation | C | 05 |
| C9 autonomous mutation | C | 07 |
| C10 in-process plugins | C | 07 |
| H1 agent/actor aliases | H | 03, GLOSSARY |
| H2 test schema fabrication | H | 06 |
| H3 hardcoded "dynamic" types | H | 03 |
| H4 auth/ontology identity | H | 05 |
| H5 DAG not enforced | H | 03 |
| H6 events not append-only | H | 06 |
| H7 worker shares JWT secret | H | 07 |
| H8 seeded super admin | H | 05 |
| H9 local file secrets | H | 07, 09 |
| M1 in-memory rate limit | M | 09 |
| M2 localStorage/URL tokens | M | 08 |
| M3 duplicate routers/clients | M | 04, 08 |
| M4 shallow CI | M | 09, 11 |
| M5 swallowed startup errors | M | 09 |
| M6 plaintext fallback / uuid7 | M | 06 |
| M7 shallow health check | M | 09 |
| L1–L5 hygiene | L | 04, 09 |

Every remediation is elaborated in its home document. No finding is closed until
its acceptance gate in [`11-acceptance-gates.md`](./11-acceptance-gates.md) passes
with attached proof.
