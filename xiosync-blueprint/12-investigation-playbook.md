# 12 — Investigation Playbook

> **Purpose.** Docs 01–11 are conclusions. This document is the method. For every
> concept in XIOSYNC, it defines the broadest investigation an agent must run to
> **re-derive, verify, or extend** that concept — so findings are reproduced, not
> trusted blindly. If a future agent suspects any blueprint claim is stale or wrong,
> the procedure to falsify it is here.
>
> **Rule of use:** never patch a blueprint doc from memory. Run the relevant
> investigation below, record evidence, then amend the doc and log the change in
> `DECISIONS.md`.

---

## 1. How to investigate (general method)

Every investigation follows the same five steps:

1. **State the claim** exactly as written in the blueprint (doc + section).
2. **Locate the ground truth** — source code, schema, running behavior, or spec.
   Never accept a comment, README, or docstring as ground truth (XIOPATH's docs
   contradicted its code in at least 6 places — see doc 02).
3. **Reproduce** — write the smallest possible script/test that demonstrates the
   claim true or false. Prefer executable evidence over reading.
4. **Check the negative space** — what the code *doesn't* do: missing enforcement,
   missing indexes, missing revocation, missing scoping. Most of XIOPATH's critical
   findings (C1–C10) were absences, not bugs.
5. **Record** — evidence (file:line, test output), verdict, and the doc amendment
   if any. Append a decision entry if the verdict changes a durable choice.

**Falsification bias.** Approach every claim trying to break it. A claim survives
an investigation only if a genuine attempt to falsify it failed.

---

## 2. Concept-by-concept investigation procedures

Each entry: the concept, where it is specified, and the investigation that
verifies it in a living XIOSYNC codebase.

### 2.1 Tenancy isolation (docs 03 §2.1, 05 §3; findings C1, C2)

- **Claim:** no query can return a row from another organization; tenant context
  derives only from the authenticated session, never from headers or placeholders.
- **Investigate:**
  1. Grep the persistence layer for any query builder entry point that does not
     require an `organization_id` parameter. Every repository method must take it.
  2. Grep for `X-Org`, `X-Tenant`, or any header-derived tenant value reaching a
     query. There must be none.
  3. Run the cross-tenant test suite (doc 11 §3): create two orgs, attempt every
     read/write/list/delete across the boundary with valid credentials from the
     other org. Expect 404 (not 403 — existence must not leak).
  4. Check new tables added since the last audit: every tenant-owned table must
     carry `organization_id NOT NULL` with a composite index. List tables lacking it.
- **Red flags:** default tenant values, nullable `organization_id`, "temporary"
  service-role bypasses, list endpoints without a tenant predicate.

### 2.2 Authorization spine (docs 03 §5–6, 05 §4; finding C3)

- **Claim:** exactly one decision function authorizes every mutating action;
  grants are enforced at execution time, not just stored.
- **Investigate:**
  1. Grep for the decision function's name; every mutating router/handler must
     call it (directly or via middleware). Enumerate handlers that don't.
  2. Prove enforcement: grant a capability, exercise the action (expect success),
     revoke it, exercise again (expect denial) — in the same session, without
     re-login. If revocation requires re-login, session-embedded authority has
     crept back in (C8 regression).
  3. Search for any second authorization path (role string checks, `is_admin`
     booleans, inline permission lists). Two paths = finding.
- **Red flags:** authority cached in JWT claims, `if user.role == "admin"` inline,
  decorators that skip the central decision point.

### 2.3 Identity unification (docs 03 §2.2–2.3, 05 §1; findings H1, H4, H8)

- **Claim:** one AuthIdentity per human/service, linked to per-org Actors; no
  parallel vocabulary (`agent` aliases), no ontology-seeded superuser.
- **Investigate:**
  1. Grep the entire codebase for the forbidden legacy vocabulary (see GLOSSARY
     "Forbidden terms"). Zero hits allowed outside historical docs.
  2. Verify the bootstrap path (doc 05 §6): a fresh deployment must produce its
     first administrator only via the documented bootstrap procedure — no seed
     script that inserts a privileged ontology row.
  3. Trace one request end-to-end: token → session → AuthIdentity → Actor →
     grants → decision. Every hop must exist in code; document the file:line chain.

### 2.4 Ontology & graph semantics (doc 03 §2.6–2.7, §3; findings H3, H5)

- **Claim:** entity types come from the Type Registry (not hardcoded); edges that
  claim DAG semantics are cycle-checked at write time.
- **Investigate:**
  1. Grep for hardcoded type-name literals in validation or business logic.
     Types must be looked up from the registry.
  2. Attempt to create a cycle through the API on a DAG-constrained edge kind.
     Expect a validation error with a stable error code.
  3. Verify cycle detection cost: the check must be bounded (e.g., scoped
     traversal), not a full-graph scan per write. Benchmark on a graph of 10k edges.

### 2.5 Sessions & revocation (docs 03 §2.10, 05 §2; findings C8, M2)

- **Claim:** opaque server-side sessions; revocation is immediate; password change
  invalidates all other sessions; no tokens in localStorage or WS query strings.
- **Investigate:**
  1. Revoke a session, then replay its credential within 1s. Expect 401.
  2. Change a password from session A; verify sessions B..N die.
  3. Inspect frontend storage: cookies must be HttpOnly; grep frontend for
     `localStorage`/`sessionStorage` writes of any credential.
  4. Inspect the WS handshake: auth must ride the cookie or a one-time ticket —
     never a long-lived token in the URL (URLs are logged everywhere).

### 2.6 Schema authority & migrations (doc 06 §1–3; findings C5, C6, H2)

- **Claim:** migrations are the only schema authority; runtime never creates or
  alters tables; migrations run as a deploy step, once, not per replica.
- **Investigate:**
  1. Grep runtime code for DDL (`CREATE TABLE`, `ALTER`, metadata `create_all`
     equivalents). Zero hits outside migration files.
  2. Diff the ORM/model definitions against the migration-produced schema in a
     scratch database. Any drift is a finding (this is exactly how H2 arose:
     tests fabricated columns to paper over drift).
  3. Verify deploy config: the migration job must be a separate step/Job with a
     lock, and app replicas must fail fast if the schema version is behind.

### 2.7 Append-only events & memory versioning (docs 03 §2.8–2.9, 06 §6; finding H6)

- **Claim:** events are insert-only (no UPDATE/DELETE paths in code, and
  database-level protection where the engine allows); memory is versioned,
  never overwritten.
- **Investigate:**
  1. Grep repositories for update/delete methods on event/memory tables.
  2. Attempt an UPDATE against the events table with the app's database role.
     Expect a privilege error (the app role must lack UPDATE/DELETE on those tables).
  3. Verify memory reads return the version chain and that "current" is a
     derived pointer, not the only surviving row.

### 2.8 Worker trust & credentials (docs 03 §2.12 & §7, 05 §5, 07 §2–3; findings H7, H9)

- **Claim:** workers enroll individually with short-lived, per-worker credentials;
  no shared signing secret leaves the control plane; task secrets are scoped and
  expire with the task.
- **Investigate:**
  1. Inspect what a worker receives at enrollment. If it can mint tokens valid
     for any other worker or any API scope, H7 has regressed.
  2. Kill a worker mid-task; verify its credential is useless after task expiry.
  3. Verify secret material at rest on the worker host: nothing durable beyond
     the current task's scope.

### 2.9 Sandboxed plugins (doc 07 §5; finding C10)

- **Claim:** plugin code never executes in the control-plane process; the sandbox
  enforces resource, filesystem, and network limits.
- **Investigate:**
  1. Grep control-plane code for dynamic import/exec of plugin-supplied code.
     Zero hits.
  2. Run the hostile-plugin test suite: a plugin that tries to read env vars,
     open sockets to the control plane, exhaust memory, and fork-bomb. All four
     must be contained, with evidence.

### 2.10 DLQ & self-learning governance (doc 07 §4; finding C9)

- **Claim:** no autonomous mutation of state from failure analysis; corrections
  are proposals requiring approval by a granted authority.
- **Investigate:**
  1. Trace the DLQ consumer: its write surface must be limited to proposal rows.
  2. Verify a proposal cannot be approved by the actor that generated it.

### 2.11 Isolation-tier execution / Phantom successor (doc 07 §6; finding C7)

- **Claim:** the isolation-tier bridge references only fields that exist; every
  chain is integration-tested against the real entity shapes.
- **Investigate:**
  1. Run the contract tests that instantiate every chain against real (not
     mocked) entity fixtures. C7 existed because nothing ever executed the path.
  2. Confirm no chain is registered without a passing contract test (CI gate).

### 2.12 Transport, CORS & rate limiting (docs 05 §2, 09 §2 & §5; findings C4, M1, M2)

- **Investigate:**
  1. Request with a hostile `Origin` against every environment config. Wildcard +
     credentials must be impossible by construction (startup must refuse it).
  2. Verify the rate limiter is backed by shared state (survives multi-replica) —
     spin two replicas, exhaust the limit on one, verify the other enforces it.

### 2.13 Startup preconditions & health (doc 09 §4 & §6; findings M5, M7)

- **Investigate:**
  1. Boot with each required dependency broken (db down, migrations behind,
     missing secret). Every case must fail fast with a specific exit message —
     no silent `except Exception` recovery.
  2. Call readiness while a dependency is degraded: it must go unready. Health
     must test behavior (round-trip write/read), not table existence.

### 2.14 Frontend reliability contract (doc 08 §5; finding M2)

- **Investigate:**
  1. For each async surface, force loading / empty / error / success and verify
     all four render distinctly (throttle network, return empty sets, inject 500s).
  2. Verify no duplicated API client layers (M3): one transport module, grep for
     stray `fetch(`/axios instances outside it.

### 2.15 CI as proof (doc 09 §7; finding M4)

- **Investigate:**
  1. Read the CI config: does any gate merely import/compile? Each blueprint gate
     in doc 11 must map to a named CI job that runs real behavior.
  2. Mutation-check one gate: intentionally break the behavior it guards on a
     branch, confirm CI goes red. A gate that can't fail is not a gate.

---

## 3. Investigating *new* concepts (extension protocol)

When adding a concept that has no blueprint section yet:

1. **Ontology first** — can it be expressed with existing entities (doc 03)?
   New tables/entities require a DECISIONS.md entry with the rejected
   alternatives.
2. **Threat pass** — run it against the threat model (doc 05 §8): tenant leak?
   authority bypass? credential scope creep? untrusted execution?
3. **Failure pass** — enumerate its failure modes and where they surface
   (doc 07 §7, doc 08 §5).
4. **Gate pass** — write its acceptance gates (doc 11 format) *before*
   implementation.
5. **Playbook entry** — add its investigation procedure to §2 above.

---

## 4. Periodic full re-audit

Run the complete forensic method of doc 02 against XIOSYNC itself:

- **Trigger:** before any major release, or after any change touching auth,
  tenancy, persistence engine, or the execution plane.
- **Method:** treat XIOSYNC as an untrusted inherited codebase. Re-run every §2
  procedure. Produce a findings table in the same C/H/M/L severity format as
  doc 02. Zero C or H findings is the release bar (doc 11 §1).
- **Honesty rule:** findings are recorded even when embarrassing. XIOPATH decayed
  precisely because drift was papered over (H2) instead of recorded.

---

*End of doc 12. The blueprint index lives in [`README.md`](./README.md).*
