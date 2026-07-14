# 07 — Execution, Workers & the Phantom Boundary

> Normative. Defines durable execution, worker enrollment, the sandboxed plugin
> host, DLQ/self-learning governance, memory-merge governance, and the isolation
> boundary that supersedes XIOPATH's "Phantom." Remediates C7, C9, C10, H7, H9,
> and enforces doc 03 §7 (trust tiers). RFC 2119 keywords binding.

---

## 1. Execution model

The control plane **authorizes and schedules**; the execution plane **executes**
(doc 04 §1). The only channel between them is the **task lease protocol**
(doc 04 §3.1). Restated invariants:

- **INV-EXEC-1:** No execution-plane component reads or writes the control-plane
  database, publishes Events directly, or calls internal services. It only calls
  the lease API.
- **INV-EXEC-2:** Task delivery is **at-least-once**; every capability handler is
  **idempotent** keyed on `task_id`. Duplicate completions are detected and
  ignored.
- **INV-EXEC-3:** A task result is **untrusted input** until the scheduler
  validates it against the capability `output_schema`, verifies the lease is
  still held, and re-checks the grant (doc 05 §4). Only then are state
  transitions committed with their Operation + Event.

### 1.1 Task & lease lifecycle

```
queued → leased → (completed | failed | expired)
leased → expired → queued        (lease deadline passed; returned to pool)
completed → (validated ⇒ committed | invalid ⇒ failed)
failed → (retriable ⇒ queued with backoff | exhausted ⇒ dead_letter)
```

- Leases carry a deadline; heartbeats extend them. Expired leases return the
  task to the queue (INV-EXEC-2 covers the resulting duplicate).
- Retry policy (count, backoff, jitter) comes from the capability/grant, not
  hardcoded. Exhausted retries route to the DLQ (§4), never silently dropped.

---

## 2. Worker enrollment (H7 remediation)

XIOPATH workers signed tokens with the shared platform JWT secret and hardcoded
worker ids (H7). XIOSYNC replaces this with real enrollment.

```
1. register    worker presents an enrollment token (one-time, operator- or
               org-admin-issued, scoped to a pool + max trust tier)
2. attest      worker submits identity material (public key); platform records
               a Worker row (actor_type = compute) in enrollment_state = pending
3. approve     managed pool: auto on valid enrollment token;
               volunteer pool: explicit approval, starts at newcomer tier
4. credential  platform issues a SHORT-LIVED, per-worker credential (signed with
               a worker-credential key DISTINCT from the user JWT secret),
               scoped to the worker's granted capabilities
5. operate     worker leases tasks; credential auto-rotates before expiry
6. revoke      any worker credential is independently revocable; revocation is
               immediate at the lease API
```

- **INV-WORKER-CRED-1:** Worker credentials are **short-lived**, **per-worker**,
  **capability-scoped**, and signed with a key **distinct** from the user-session
  signing key (kills H7). A compromised worker can never mint a user or admin
  token.
- **INV-WORKER-CRED-2:** `WORKER_ID`/`WORKER_SECRET` are never hardcoded or
  shared; each worker's identity is unique and enrolled (kills
  `colab_worker.py`'s blank shared secret).
- **INV-WORKER-2 (doc 03):** A worker only ever leases tasks it holds a valid
  Grant for, in its org/pool, at or above the required trust tier.

### 2.1 Trust tiers (doc 03 §7 enforcement)

`newcomer → contributor → trusted → core → admin`.
- Promotion requires verifiable successful-execution proofs; failures demote.
- **INV-TRUST-1:** An actor below a grant's required tier cannot execute it, even
  with an otherwise-valid grant.
- **INV-TRUST-2:** `newcomer`/`contributor` workers execute only isolated task
  classes and **never** mutate global or cross-actor state. Their results are
  advisory until validated/promoted.

---

## 3. Task credentials (secret handling)

- **INV-TASK-SEC-1:** Task payloads contain **no secrets**. A capability needing
  credentials (e.g. an API key) receives **scoped, single-use, short-TTL**
  material minted at lease time from the managed secret backend (doc 05 §7), not
  the raw stored secret.
- **INV-TASK-SEC-2:** Minted task credentials are bound to `(task_id, worker_id)`
  and expire with the lease; they cannot be replayed on another task.

---

## 4. DLQ & self-learning governance (C9 remediation)

XIOPATH's `self_learning.py` queried an LLM and immediately wrote
`UPDATE dead_letter_queue SET status='auto_resolved' ...` — a model mutating
durable state with no gate (C9). XIOSYNC makes every correction a **governed
proposal**:

```
failure → diagnosis → proposed_patch → validation → approval → canary → promotion
                                              │
                                       (any stage may reject → back to human)
```

- **INV-DLQ-1:** A failed task lands in `dead_letters` in state `open`. Nothing
  auto-resolves it.
- **INV-DLQ-2:** The self-learning engine may produce a **diagnosis** and a
  **proposed** corrected workflow spec, written as a *proposal record* — it
  **never** updates the DLQ row's status to resolved, and **never** mutates the
  live workflow.
- **INV-DLQ-3:** A proposal advances only through: schema/DAG **validation** →
  human/policy **approval** → **canary** execution on a limited scope → measured
  **promotion** to a new workflow **version** (doc 06 versioning). Each stage
  emits Operations + Events; any stage can reject.
- **INV-DLQ-4:** Promotion creates a **new workflow version**; it never edits a
  published spec in place (doc 03 INV-WF-1, doc 06 §6).
- Autonomous (unapproved) correction in production is a **non-goal for v1**
  (doc 01 §6) and remains disabled until these gates are proven (doc 11).

---

## 5. Sandboxed plugin host (C10 remediation)

XIOPATH ran plugins in-process via `importlib.import_module(...).run()` with an
optional (often empty) allowlist — effectively RCE with the API's privileges
(C10). XIOSYNC runs plugins **out-of-process, sandboxed**:

- **INV-PLUGIN-1:** Plugins execute in a **separate process/container** with:
  no ambient access to platform secrets or the control-plane DB, an **explicit
  network allowlist** (default deny), a **filesystem jail**, CPU/memory/time
  quotas, and a required **capability Grant** describing exactly what they may do.
- **INV-PLUGIN-2:** A plugin communicates only over a narrow, typed host↔plugin
  RPC. Inputs and outputs are schema-validated (like any capability, doc 06 §8).
- **INV-PLUGIN-3:** Plugin **installation requires approval**; the marketplace
  never installs untrusted code into a privileged context. Marketplace installs
  into privileged contexts are a **non-goal for v1** (doc 01 §6).
- **INV-PLUGIN-4:** The allowlist is **not optional**. There is no mode where an
  empty allowlist means "allow everything" (kills C10's optional allowlist).

---

## 6. The isolation-tier subsystem (Phantom successor) — C7 remediation

XIOPATH's `phantom/` (identity forging, residential-IP harvesting, browser
profile synthesis, TOTP/email automation) was wired to **fields that no longer
exist** — `agent_id`, `agent_type`, lifecycle states and edge types absent from
the model — so it raises at runtime or writes unrecognized rows (C7). It also
created its own tables at runtime (H9).

XIOSYNC's stance:

- **INV-PHANTOM-1 (vocabulary):** The subsystem speaks **only** the one canonical
  vocabulary from the Type Registry (`Actor`/`actor_type`, `Operation`, `Event`
  with `actor_id`, etc.). Every actor type, edge type, lifecycle state, and event
  type it uses **must be registered first** (doc 03 §8 INV-TYPE-2). No
  `agent_id`, no `agent_type`, no unregistered `donates_to`/`deployed_on` edges.
- **INV-PHANTOM-2 (contract tests):** Every registration and lifecycle method has
  a **contract test** that constructs real domain objects against the migrated
  schema (doc 06 §10). The C7 class of "wired to a nonexistent field" bug is
  caught in CI, not at runtime.
- **INV-PHANTOM-3 (boundary):** It runs **only** as a sandboxed, out-of-process
  subsystem (per §5) behind its **own policy wall**, in a **dedicated deployment
  mode**. Its capabilities require explicit, high-clearance grants and every
  invocation is authorized (doc 05 §4) and audited.
- **INV-PHANTOM-4 (no runtime DDL):** It owns **no** runtime table creation; its
  tables (if any) are ordinary migrated tables with `organization_id` (kills H9's
  `phantom/vault.py` self-created tables). Its secrets go through the managed
  backend (doc 05 §7), never a local `.vault_key`.
- **INV-PHANTOM-5 (deferral):** The subsystem is a **non-goal for general
  multi-tenant production in v1** (doc 01 §6). It MAY run in a restricted
  internal pilot with the above enforced; a public multi-tenant release MUST NOT
  enable it until its acceptance gates pass (doc 11).

The **boundary was always the right design** (audit Part E #9); XIOSYNC makes the
boundary real and refuses to ship the subsystem across it until enforcement is
proven.

---

## 7. Durability & recovery

- **INV-DURABLE-1:** Run and task state live in the control-plane DB (doc 06),
  not in worker memory. A worker crash loses at most an in-flight lease, which
  expires and re-queues (INV-EXEC-2).
- **INV-DURABLE-2:** The scheduler is restart-safe: on boot it reconciles leases
  (expire stale ones), never double-commits a validated completion (idempotency
  key = `task_id`), and resumes from committed state.
- **INV-DURABLE-3:** Every failure mode is one of: **retry** (with backoff),
  **dead-letter** (governed, §4), or **surfaced typed error**. A silent swallow
  is forbidden (mirrors M5; doc 09).

---

## 8. Memory merge governance (supports C9 / doc 03 §2.9)

XIOPATH merged edge-node memory into global state via LWW CRDT automatically.
XIOSYNC keeps CRDT/LWW as the *mechanism* but gates the *global* effect:

- **INV-MEM-MERGE-1:** A worker/edge node proposes memory as a
  `memory_merge_proposal`, scoped to its org. It is not applied to `org_shared`
  global memory until validated and (per policy/tier) approved.
- **INV-MEM-MERGE-2:** A merge produces a **new memory version** with provenance
  (doc 06 §6); originals are retained. Untrusted-tier sources auto-merging into
  global state is a **non-goal for v1** (doc 01 §6).

---

## 9. Execution anti-patterns (forbidden)

- Any execution-plane write to the control-plane DB or direct Event publish. **(arch)**
- A worker holding/sharing the user JWT signing secret or a long-lived broad
  credential. **(H7)**
- Hardcoded `WORKER_ID`/blank shared `WORKER_SECRET`. **(H7)**
- LLM/model output mutating durable workflow or DLQ state without the proposal
  gate. **(C9)**
- In-process plugin execution, or an optional/empty-means-all allowlist. **(C10)**
- The isolation subsystem using `agent_*` fields or unregistered types. **(C7)**
- The isolation subsystem creating tables at runtime or using local-disk vault
  keys. **(H9)**
- Auto-merging untrusted memory into global state. **(C9)**
- Any silent-swallow of a task failure. **(M5)**

Any of these is an execution-plane regression to be reverted.
