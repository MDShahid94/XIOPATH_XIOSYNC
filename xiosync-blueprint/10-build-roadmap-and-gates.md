# 10 — Build Roadmap & Phase Gates

> Normative. The phased from-scratch build order with entry/exit criteria per
> phase. Enforces the prime directive **enforcement precedes features**
> (README). No phase begins until the prior phase's exit gate passes with
> attached proof (doc 01 §4.6, doc 11).

Phases are named by **capability**, never by letter/number sprawl (L1). "Done"
means the exit gate passed reproducibly, not that code compiles.

**Phase order is: C → R → 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7.** Phases C and R are
prerequisites of all implementation; no granular builder work begins before
both have passed their exit gates.

---

## Phase C — Continuity plane (inter-agent synchronization)

**Goal:** any agent — present or future — can be plugged into this rebuild and
proceed instantly with the full legacy context, the blueprint, and all prior
progress, with zero dependence on chat history or any single agent's memory.

Build:
- Root `AGENTS.md` bootstrap: the mandatory entrypoint and boot sequence for
  any incoming agent.
- `continuity/STATE.md`: the single authoritative statement of position —
  current phase, milestone table, and the exact next action, rewritten at
  every handoff.
- `continuity/HANDOFF-LOG.md`: append-only session ledger; one entry per agent
  session with scope, produced artifacts, verification commands + results, and
  known gaps.
- `continuity/SESSION-PROTOCOL.md`: the normative boot → work → handoff
  procedure, including the log-vs-STATE integrity cross-check.
- Legacy anchoring: the complete `XIOPATH/` tree committed into git at the
  repo root as **read-only evidence** so audit claims (doc 02) remain
  re-verifiable by every future agent.

**Exit gate:**
- A cold-booted agent, given only the repository, can state the current
  position and the exact next action without asking a human.
- `XIOPATH/` is tracked in git (`git ls-files XIOPATH | wc -l` > 0).
- STATE.md's "Last updated" session matches the newest HANDOFF-LOG entry.
- Every README index link and continuity cross-reference resolves.

**Status: ✅ built and gated in Session 002** (see `continuity/HANDOFF-LOG.md`).

---

## Phase R — Rebuild-readiness deep research

**Goal:** resolve every open pre-implementation question with recorded,
evidence-backed decisions, so that Phase 0 starts on a fully determined
foundation and no builder agent ever improvises a structural choice.

This phase produces **decisions and pinned specifications, not code.** Its
outputs land as DECISIONS.md entries and (where needed) blueprint doc
amendments.

Research and decide:
- **Deferred decisions D-D1..D-D3** (DECISIONS.md): close each or explicitly
  re-defer with a dated rationale and the condition that reopens it.
- **Stack pinning:** exact language/runtime versions, framework, ORM/query
  layer, migration tool, test framework, lint/type toolchain — each choice
  justified against docs 04/06/09 requirements (e.g. RLS support, single-chain
  migrations, fail-fast config) and pinned with versions.
- **Repo instantiation plan:** map doc 04 §6's layout onto this repository —
  what happens to the sandbox scaffold, where `platform/` and services live,
  workspace/package-manager topology (L5), and the architecture-rule checker
  that will enforce boundaries from day one.
- **CI substrate:** which CI runs the doc 09 §7 blocking gates in this
  environment, and how the empty-Postgres migration harness is provisioned.
- **Continuity integration:** how each builder session's gate proofs get
  recorded (HANDOFF-LOG verification format is the minimum bar).

**Explicitly out of scope:** writing implementation code, scaffolding
services, or "just starting" Phase 0 — INV-ROADMAP-1 applies.

**Exit gate:**
- Zero open structural questions: every item above has a DECISIONS.md entry
  (accepted or re-deferred with a reopening condition).
- Doc 04 §6 layout is instantiated on paper for *this* repo with no
  placeholders.
- A named agent could begin Phase 0 from STATE.md + DECISIONS.md alone,
  without asking a single stack or layout question.

---

## Phase 0 — Foundation & guardrails

**Goal:** the skeleton that makes every later invariant enforceable.

Build:
- Repo layout (doc 04 §6), one package manager per ecosystem (L5), clean root
  (L2).
- `platform/`: config schema + fail-fast loader (no embedded defaults — L4),
  UUIDv7 (M6), crypto (hard dep — M6), clock, structured logging, `request_id`.
- PostgreSQL-only wiring (C6), Alembic single-chain scaffold (C5), empty-DB test
  harness that migrates (no fabricated tables — H2).
- CI skeleton with the blocking gates wired (doc 09 §7), even before there is
  much to test: lint/type, architecture-rule check, migration up/down, secret
  scan, container smoke.

**Exit gate:**
- `upgrade → downgrade → upgrade` clean on empty Postgres; autogenerate diff
  empty.
- App refuses to start with a missing required secret and with DB not at head.
- Architecture-rule check fails a deliberately planted cross-layer import.
- All CI gates run and are blocking.

---

## Phase 1 — Identity, tenancy & the authorization spine

**Goal:** the load-bearing security layer, before any feature uses it.

Build (docs 03, 05, 06):
- `organizations`, `auth_identities`, `memberships`, `sessions`, `actors` tables
  with immutable `organization_id` (C2) and RLS (doc 05 §3.2).
- Authentication **middleware** that resolves `OrgContext` before any handler
  (C1) — no `"pending"`.
- Sessions: short access tokens + rotating refresh + server-side revocation +
  password-change/logout invalidation + reuse detection (C8).
- Separated authority axes (platform/org/grant), signup capped at `org_member`
  (H4); neutral `system-root` + audited bootstrap for first admin (H8).
- The single `authorize(...)` decision point reading real grants, fail-closed,
  emitting `policy_decision` Events (C3).

**Exit gate (security-negative suite — doc 05 §8, doc 11):**
- Cross-tenant read/write fails at repo **and** RLS layer.
- Revoked session rejected pre-expiry; password change kills all sessions;
  refresh reuse revokes family.
- Signup cannot produce `platform_admin`/`org_owner`.
- Unauthorized capability attempt denied with an audit record; **no** execution
  path bypasses `authorize`.

---

## Phase 2 — Ontology, type registry & graph semantics

**Goal:** the canonical model, one vocabulary, enforced graphs.

Build (docs 03, 06):
- Type Registry as the single authority (H3): `core.*` seeded by migration,
  runtime writes validated against it (INV-TYPE-1/2).
- `capabilities`, `grants`, `operations`, `edges`, `events`, `memory` tables with
  invariants and immutability triggers/grants.
- Lifecycle state machines (doc 03 §4); illegal transitions rejected; each writes
  Operation + Event (INV-LC-1/2).
- Four graph classes with per-class acyclicity validated on write (H5).
- Append-only Events (INSERT/SELECT-only grant, optional hash chain — H6);
  versioned Memory.
- One canonical vocabulary end to end — **no** `agent`/`actor` aliases, **no**
  `_v2` twins (H1).

**Exit gate:**
- Writing an unregistered type value is rejected.
- Creating a cycle in hierarchy/workflow graph is rejected on write.
- An `UPDATE`/`DELETE` on `events` from the app role fails at the DB.
- No alias or `_v2` symbol exists (grep gate in CI).

---

## Phase 3 — Workflows & durable execution (control-plane side)

**Goal:** define, publish, run workflows; schedule tasks; DLQ — all governed.

Build (docs 03, 04, 07):
- `workflows` (DAG-validated on publish — INV-WF-1), `workflow_runs`, `tasks`,
  `dead_letters`.
- Scheduler: expand run → tasks; lease protocol endpoints (doc 04 §3.1);
  at-least-once + idempotent completion (INV-EXEC-2); result validation +
  re-authorization on completion (INV-EXEC-3).
- DLQ as governed proposals — **no** auto-resolve/auto-mutation (C9); proposal
  lifecycle `failure→diagnosis→proposed→validation→approval→canary→promotion`.

**Exit gate:**
- Publishing a cyclic workflow spec is rejected.
- A duplicate task completion is ignored (idempotency proven).
- A DLQ item cannot transition to resolved without passing the proposal gates;
  no code path auto-mutates workflow/DLQ state.

---

## Phase 4 — Workers & the execution plane

**Goal:** real enrollment, scoped credentials, trust tiers.

Build (docs 05, 07):
- Worker enrollment flow; per-worker short-lived, capability-scoped credentials
  signed with a key distinct from user JWT secret (H7).
- Trust tiers with proof-based promotion/demotion; tier-gated grants
  (INV-TRUST-1/2).
- Task credential minting (single-use, per-lease — INV-TASK-SEC-1/2).

**Exit gate (worker-isolation test):**
- A worker credential cannot mint a user/admin token.
- A below-tier worker cannot execute a tier-gated grant.
- A compromised volunteer worker cannot mutate global/cross-actor state; its
  results are validated before commit.

---

## Phase 5 — Sandboxed plugins

**Goal:** out-of-process, capability-scoped plugin execution.

Build (doc 07 §5):
- Out-of-process plugin host: no ambient secrets, network allowlist (not
  optional — C10), filesystem jail, resource quotas, required grant.
- Typed host↔plugin RPC with schema-validated I/O; approval-gated installation.

**Exit gate (plugin-sandbox test):**
- A plugin cannot reach the DB, platform secrets, or a non-allowlisted host.
- An empty allowlist denies all network (never "allow everything").
- Installing a plugin without approval is impossible.

---

## Phase 6 — Frontend

**Goal:** the user-facing control plane, secure and accessible.

Build (doc 08):
- One generated typed API client (M3); cookie/memory token transport (M2); WS
  handshake auth (M2).
- Route/permission matrix with server-re-checked guards; one canonical page per
  concept (H1/M3).
- Loading/empty/error/success on every async surface; per-route error
  boundaries.

**Exit gate:**
- No token in `localStorage`/WS query (grep + runtime test).
- Unauthorized route never renders; server rejects the matching request.
- axe a11y clean on all routes; Web Vitals budgets met on key routes.

---

## Phase 7 — Ops hardening & release readiness

**Goal:** production deployability with proof.

Build (doc 09):
- Migration-as-deploy-step + readiness head-gate (C6); fail-fast startup (M5);
  distinct `/live` `/ready` (M7); shared-store rate limiting (M1); origin
  allowlist CORS (C4).
- Backups + rehearsed restore (INV-DR-1); progressive rollout + rollback;
  feature flags default-off for non-goals (doc 01 §6).

**Exit gate:** the full acceptance suite (doc 11) passes reproducibly in staging,
including container smoke, DR restore drill, and the entire security-negative
suite. Only then is a public multi-tenant release permitted.

---

## Deferred (behind flags, default-off — doc 01 §6)

Autonomous unapproved correction, untrusted CRDT auto-merge to global state,
marketplace install into privileged contexts, and the isolation-tier subsystem
(Phantom successor) in general multi-tenant production. Each ships only after its
own governing invariants (doc 07) are enforced and its acceptance gate (doc 11)
passes.

---

## Roadmap invariants

**INV-ROADMAP-1:** No phase's features are built before its enforcement is in
place, and no phase closes without its exit gate proven. If a later phase needs
an earlier invariant that isn't done, the earlier phase is not actually complete
— fix it there, do not work around it.

**INV-ROADMAP-2 (continuity):** Every agent session — in every phase — boots
via root `AGENTS.md` and closes via the handoff procedure in
`continuity/SESSION-PROTOCOL.md` (log entry, STATE.md update, decisions
recorded, tree committed). Work whose position and proof are not recorded in
the continuity plane does not count as progress, regardless of code written.
