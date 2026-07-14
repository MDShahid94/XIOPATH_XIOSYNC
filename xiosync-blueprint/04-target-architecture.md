# 04 — Target Architecture

> Normative. Defines XIOSYNC's planes, service boundaries, module map, and data
> flow. Supersedes XIOPATH's implicit architecture. Remediates: M3 (duplicate
> routers/clients), L1–L2 (phase-named sprawl), and structurally enables the
> fixes in 05/06/07.

---

## 1. Architectural thesis

XIOSYNC is split into exactly **two planes** with a hard trust boundary between
them, plus a thin client layer:

```
┌────────────────────────────────────────────────────────────────┐
│  CLIENTS            web app · browser extension · CLI · API    │
└───────────────┬────────────────────────────────────────────────┘
                │  HTTPS + WS (authenticated, org-scoped)
┌───────────────▼────────────────────────────────────────────────┐
│  CONTROL PLANE      (trusted; owns truth, authz, scheduling)   │
│  gateway → identity → authorization → ontology → orchestration │
│  ──────────────  one PostgreSQL database (migrated)  ───────── │
└───────────────┬────────────────────────────────────────────────┘
                │  task lease protocol (short-lived, per-worker creds)
┌───────────────▼────────────────────────────────────────────────┐
│  EXECUTION PLANE    (semi-trusted → untrusted; does the work)  │
│  managed workers · volunteer workers · sandboxed plugins ·     │
│  isolation-tier subsystems (Phantom successor)                 │
└────────────────────────────────────────────────────────────────┘
```

**The control plane authorizes and schedules. The execution plane executes.**
No execution-plane component ever holds platform signing secrets (H7), writes
directly to the control-plane database, or mutates global state (C9). Results
re-enter the control plane only through the task-completion API, where they are
validated and authorized like any other input.

This preserves XIOPATH's strongest idea (control-plane/execution-plane split —
audit Part E #7) and makes the boundary real.

---

## 2. Control plane — service decomposition

XIOSYNC v1 ships the control plane as a **modular monolith**: one deployable
API process with strictly layered internal modules. Physical microservices are a
deliberate later ADR, not a v1 requirement — but module boundaries below are
drawn so extraction is mechanical, not surgical.

### 2.1 Layering (dependencies point downward only)

```
api/            HTTP + WS transport. Zero business logic.
  └─ depends on ─▼
services/       Use-cases. Orchestrate domain + persistence. Transactional.
  └─ depends on ─▼
domain/         Pure model: entities, invariants, state machines (doc 03).
                No I/O. No framework imports.
  └─ depends on ─▼ (interfaces only)
persistence/    Repositories implementing domain-defined interfaces.
                Every method requires OrgContext (doc 05/06).
platform/       Cross-cutting: config, clock, ids, crypto, telemetry.
```

**RULE-ARCH-1:** `domain/` imports nothing from `api/`, `services/`,
`persistence/`, or any web/DB framework. Invariants from doc 03 live here and
are unit-testable with zero infrastructure.
**RULE-ARCH-2:** `api/` handlers do exactly: parse → authenticate context →
call one service method → shape response. A handler containing a query or a
business rule is a defect.
**RULE-ARCH-3:** Repositories never accept an optional org filter. `OrgContext`
is the first, non-defaulted parameter of every tenant-touching method (C1/C2).

### 2.2 Module map

| Module | Owns | Key contents |
|---|---|---|
| `identity` | AuthIdentity, Session, login/refresh/revoke | password hashing, session store, token issuance (doc 05) |
| `authz` | Grants + the single decision point | `authorize(...)`, decision audit emission (doc 03 §6) |
| `ontology` | Actor, Edge, Operation, Type Registry | lifecycle state machines, graph-class acyclicity validation |
| `capabilities` | Capability registry | schema validation of input/output contracts |
| `memory` | Memory entities + merge proposals | versioned writes, provenance, merge-proposal queue (doc 07) |
| `workflows` | Workflow, WorkflowRun | DAG validation on publish, run state machine |
| `scheduling` | Task queue, leases, DLQ | lease issuance to workers, retry policy, dead-lettering |
| `workers` | Worker enrollment + trust ledger | enrollment flow, credential issuance/rotation, tiers (doc 07) |
| `events` | Append-only Event stream | insert-only writer, hash-chaining, query API |
| `orgs` | Organization lifecycle | creation, suspension, membership roles |
| `admin` | Platform-role operations | bootstrap flow, platform health, cross-org read (audited) |

**RULE-ARCH-4 (M3/H1):** One module per concept; one router per resource; one
canonical name. There are no `_v2` twins, no `agents.py`-and-`actors.py` pairs,
and no compatibility aliases — versioning happens at the API prefix (`/api/v1`)
if ever needed, never by duplicating files.
**RULE-ARCH-5 (L1):** Modules, files, and tests are named by domain concept
(`workers/enrollment_test.py`), never by build phase ("phase_s", "M.6").

### 2.3 The API surface

- Single OpenAPI 3.1 contract, generated from code, committed to the repo, and
  diffed in CI (breaking-change detection is a blocking gate — doc 09).
- Route inventory (v1): `auth`, `orgs`, `actors`, `capabilities`, `grants`,
  `operations`, `edges`, `events`, `memory`, `workflows`, `runs`, `workers`,
  `tasks`, `types`, `admin`, `health`. Exactly one router each.
- WebSocket: one endpoint, `/ws`, authenticated at handshake (doc 08), carrying
  typed, org-scoped event frames only. No command channel over WS in v1 —
  mutations go through HTTP where authz and audit are uniform.
- Every response envelope includes `request_id`; every error is a typed problem
  document (`application/problem+json`) with a stable `code`.

### 2.4 Middleware pipeline (order is normative)

```
request_id → security_headers → CORS(allowlist) → body_size_limit
  → authenticate (resolve identity + org, or reject)      [C1 fix]
  → rate_limit (shared store, keyed by identity/org)      [M1 fix]
  → route handler (authz decision inside the service)     [C3 fix]
```

Authentication is **middleware**, before anything tenant-scoped. There is no
"pending" state: a request is either anonymous-on-a-public-path or fully
resolved. The pipeline is declared in one place and covered by an order test.

---

## 3. Execution plane — components

| Component | Trust | Description |
|---|---|---|
| **Managed workers** | Semi-trusted | Platform-operated runners (LLM inference, browser automation, GPU). Enrolled, per-worker short-lived credentials, capability-scoped leases. |
| **Volunteer workers** | Untrusted | Community/edge nodes (Colab-style). Same enrollment protocol, lowest trust tier, isolated task classes only, results always validated. |
| **Sandboxed plugins** | Untrusted | Out-of-process, no ambient secrets, explicit grant + network allowlist (C10 fix; doc 07 §5). |
| **Isolation-tier subsystem** (Phantom successor) | Quarantined | Runs only in a dedicated deployment mode behind its own policy wall (doc 07 §6). Disabled in general multi-tenant production (doc 01 §6). |

### 3.1 The task lease protocol (the only control↔execution channel)

```
worker → POST /tasks/lease        (present worker credential; receive ≤N tasks
                                   matching its grants + trust tier, with a
                                   lease_id and lease deadline)
worker → POST /tasks/{id}/heartbeat   (extend lease; report progress)
worker → POST /tasks/{id}/complete    (result payload, validated against the
                                       capability's output_schema)
worker → POST /tasks/{id}/fail        (structured failure → retry or DLQ)
```

- Leases expire; expired tasks return to the queue (at-least-once delivery).
- Task payloads carry **no secrets**; capabilities needing credentials receive
  scoped, single-use material minted at lease time (doc 07 §3).
- Completion is not trusted: the scheduler validates the result schema, checks
  the lease, re-checks the grant, and only then commits state transitions.

**RULE-ARCH-6:** There is no code path by which an execution-plane component
writes to the database, publishes events directly, or calls internal service
functions. The lease API is the whole interface.

---

## 4. Data flow — canonical walkthrough (workflow execution)

1. **Submit.** Client `POST /runs` with workflow id. Gateway authenticates →
   `OrgContext{identity, actor, organization_id}`.
2. **Authorize.** `workflows` service calls `authorize(actor, run, workflow,
   org)` → decision id logged as a `policy_decision` Event (doc 03 §6).
3. **Plan.** The published, DAG-validated spec is expanded into Tasks with
   per-node capability requirements. Run enters `queued`.
4. **Lease.** Eligible workers lease tasks matching their grants + tier.
5. **Execute.** Worker runs the capability; heartbeats extend the lease.
6. **Complete.** Result validated (schema, lease, grant) → node marked done →
   dependent nodes become leasable. Operations + Events written at each
   transition (INV-LC-2).
7. **Finish/Fail.** Terminal state on the run; failures route to the DLQ where
   correction is a *governed proposal*, never an auto-mutation (C9; doc 07 §4).

Every step is org-scoped, every privileged step has a decision id, and every
state change is an Operation + Event. This walkthrough is the template for all
execution features.

---

## 5. Technology commitments (v1)

| Concern | Commitment | Rationale / finding |
|---|---|---|
| Control-plane DB | **PostgreSQL only** | C6: no SQLite/Postgres dual paths, ever. One engine, one dialect, one set of migration semantics. |
| Migrations | Alembic, single linear chain, run as a deploy step | C5/C6; doc 06 |
| API framework | FastAPI (retained) with the layering of §2.1 | The framework wasn't the problem; the missing layering was. |
| Queue/lease + rate-limit store | Redis (or managed equivalent) | M1; shared across replicas |
| Vector memory | Dedicated vector store behind `memory` module interface | Never colocated with control-plane truth |
| IDs | One vetted UUIDv7 library, in `platform/ids` | M6: no hand-rolled uuid7, no silent uuid4 fallback |
| Crypto | Hard dependency; startup fails if absent | M6: no plaintext fallback |
| Secrets | Managed backend (env/KMS/vault); never key-next-to-ciphertext on app disk | H9 |
| Frontend | React + TypeScript, one generated API client | M3, doc 08 |
| Package managers | Exactly one per ecosystem (pnpm for JS, uv/pip-tools for Python), one lockfile each | L5 |

---

## 6. Repository layout (clean root — L2)

```
xiosync/
├── api/                # transport layer (routers, middleware, ws)
├── services/           # use-case layer
├── domain/             # pure model + invariants (doc 03)
├── persistence/        # repositories + migrations/
├── platform/           # config, ids, crypto, telemetry, clock
├── workers/            # execution-plane worker runtime (own package)
├── plugins-sdk/        # sandboxed plugin contract + host
├── frontend/           # React app (doc 08)
├── deploy/             # containers, k8s/compose, migration job
├── scripts/            # maintained, tested operational scripts only
├── tests/              # unit / integration / security / contract
└── xiosync-blueprint/  # these documents
```

No scratch files at root. No committed one-off scripts. Anything in `scripts/`
is either exercised by CI or deleted.

---

## 7. Anti-architecture (forbidden shapes)

Restating audit-derived bans at the structural level:

1. No business logic in routers or middleware (beyond authn/limits).
2. No module reaches around a layer (e.g., router → repository directly).
3. No second name for an existing concept (H1/M3).
4. No execution-plane component with DB access or platform secrets (H7).
5. No in-process plugin execution (C10).
6. No runtime schema mutation from any module (C5).
7. No per-replica startup migration (C6).
8. No subsystem-private table creation (H9: `vault.py`, `trust_ledger.py` pattern).

Violations of this section are architectural regressions and block merge.
