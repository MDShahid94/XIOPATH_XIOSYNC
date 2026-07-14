# 01 — Vision & Quality Bar

> Normative. RFC 2119 keywords (MUST, MUST NOT, SHOULD, MAY) are binding.
> Read [`README.md`](./README.md) first.

---

## 1. What XIOSYNC is

XIOSYNC is a **control plane for coordinating humans, AI models, tools, browsers,
workflows, and distributed workers** under one governed graph. It is the
clean-room successor to XIOPATH: it inherits the *idea* and discards the
*implementation*.

The one-sentence thesis:

> **XIOSYNC is a secure, multi-tenant operating system for autonomous and
> semi-autonomous work, in which every actor, capability, execution, and memory
> is identified, authorized, recorded, and recoverable.**

The system unifies five concerns that are normally scattered across unrelated
tools:

1. **Identity** — who or what is acting (human, AI, compute), and on whose behalf.
2. **Capability** — what an actor is allowed to do, under what constraints.
3. **Execution** — durable, delegated, observable work across local and remote workers.
4. **Memory** — retained observations, intentions, outcomes, and reusable knowledge.
5. **Provenance** — an append-only record of what happened and why.

These are not five products bolted together. They are five projections of a
single graph. That graph is the product.

---

## 2. What XIOSYNC is *for* (the product objectives)

Ported forward from XIOPATH's coherent core, restated as enforceable goals:

1. **Universal identity & ontology.** Every important entity has a stable
   identity and a typed place in the graph: human, AI model, API server, worker,
   browser runtime, workflow, capability, plugin, organization. Relationships are
   typed; lifecycles are validated.

2. **Workflow orchestration.** Users define DAG-based workflows, execute them,
   monitor progress, retry failures, and delegate steps to capable workers.

3. **Distributed execution.** Expensive work (LLM inference, browser automation,
   GPU tasks) runs on durable remote workers, not inside the API process. The API
   *authorizes and schedules*; workers *execute*.

4. **Memory & learning.** Actors retain provenance-bearing memory. Failures feed a
   correction system that *proposes* improved workflows — as governed proposals,
   never silent mutations.

5. **Security & governance.** The platform is the single authority on: who may
   access an organization, who owns a resource, which actor may use which
   capability, which worker may receive a task, which autonomous change needs
   approval, and what must be audited.

6. **Operational control.** Operators get deployment, health, monitoring, audit,
   recovery, and rollback as first-class, tested capabilities.

The **primary success metric** is not feature count. It is:

> **Can one organization safely execute a workflow without another organization,
> an untrusted worker, or a compromised plugin affecting it — and can we prove
> it with a test?**

If that question cannot be answered "yes, reproducibly," the platform is not
ready, regardless of how many features exist.

---

## 3. Why a rebuild, not a patch

XIOPATH is a large, working prototype (~38.5k LOC). Its concept is sound. But its
**enforcement architecture never caught up to its conceptual architecture**, and
the gap is structural, not cosmetic. Document
[`02-forensic-audit-xiopath.md`](./02-forensic-audit-xiopath.md) catalogs every
finding against real files and lines. The short version:

- Two vocabularies (`agent`/`actor`) coexist behind aliases; one subsystem
  (Phantom) calls fields that no longer exist and will raise at runtime.
- Tenant isolation is aspirational: middleware stamps `"pending"` because it runs
  before auth resolves, and core tables carry no `organization_id` at all.
- Capability grants are stored but never enforced; the "policy enforcer" compares
  hardcoded strings like `tenant_id == "suspended_tenant"`.
- Schema ownership is split between Alembic and a runtime `_init_db()`, and
  migrations run per API replica at startup hardcoded to SQLite.
- CORS is `allow_origin_regex=".*"` with credentials enabled.
- Tests fabricate their own tables instead of migrating, so green tests do not
  prove the schema.

Patching in place means fighting these defaults on every change. The recorded
decision (see [`DECISIONS.md`](./DECISIONS.md), ADR-0001) is: **rebuild on a
correct foundation, port the good ideas, never reintroduce the compromises.**

"Zero legacy" is literal. There are **no** compatibility aliases, **no** dual
schemas, **no** runtime table creation, **no** wildcard CORS, **no** unchecked
capability. If a legacy pattern from document 02 appears in XIOSYNC, it is a
regression to be reverted.

---

## 4. The definition of "production-grade"

A capability is **production-grade** in XIOSYNC only when *all* of the following
hold. This is the quality bar; it is not negotiable per-feature.

### 4.1 Correctness & rigor
- The behavior is derived from an explicit model in
  [`03-ontology-formal-spec.md`](./03-ontology-formal-spec.md), not improvised.
- Invariants are stated, and violating inputs are rejected with a defined error,
  not undefined behavior.
- State transitions follow a declared state machine; illegal transitions are
  impossible, not merely discouraged.

### 4.2 Security & tenancy
- Every request resolves to an authenticated identity and an organization before
  any handler logic runs.
- Every tenant-bearing query filters by `organization_id`.
- Every privileged action passes exactly one authorization decision that emits an
  auditable decision record.
- The feature ships with at least one **security-negative test** (a cross-tenant
  or unauthorized attempt that MUST fail).

### 4.3 Persistence & schema
- The schema change is a migration. No runtime DDL. No ORM `create_all` in app code.
- A test upgrades an empty database through the full migration chain and exercises
  the feature against the resulting schema.

### 4.4 Observability & recovery
- The feature emits structured logs, an audit event where state changes, and
  metrics where it affects throughput or error rate.
- Failure modes are defined: retry, dead-letter, or surfaced error — never a
  silent swallow.

### 4.5 Frontend (if user-facing)
- The route declares its required permission; unauthorized users never render it.
- Loading, empty, error, and success states are all handled.
- It meets the accessibility bar in [`08-frontend-contract.md`](./08-frontend-contract.md).

### 4.6 Proof
- The claim of "done" is accompanied by the exact command run and its result.
- If a check could not run, the blocker is recorded verbatim. **A green compile,
  a clean type-check, or "no lint errors" is not evidence of behavior.**

---

## 5. Quality anti-patterns (automatic rejection)

The following are never acceptable and any change introducing one is wrong:

- A compatibility alias between canonical and legacy names.
- A runtime `CREATE TABLE`, `create_all`, or schema probe in application code.
- A tenant filter that is optional, defaulted, or "global by default."
- An authorization check implemented as a string comparison against a hardcoded
  identifier.
- A wildcard CORS origin (`*` or `.*`) with credentials enabled.
- An autonomous process that mutates global workflow or memory state without a
  validation-and-approval gate.
- A worker or plugin that executes with long-lived, broadly-scoped, or shared
  credentials.
- A test that constructs its own tables instead of migrating.
- A "done" claim without an attached, reproducible proof.

---

## 6. Non-goals (explicitly out of scope for v1)

To keep the foundation stable before autonomy, the following are **deferred** and
MUST remain disabled until their governing invariants are enforced and tested:

- Autonomous (unapproved) workflow correction in production.
- Automatic CRDT memory merges into global state from untrusted sources.
- Marketplace installation of untrusted plugins into privileged contexts.
- Phantom subsystem in general multi-tenant production (see
  [`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md)).
- Untrusted volunteer workers mutating global state.

A restricted internal pilot MAY ship with these disabled. A public multi-tenant
release MUST NOT ship until the acceptance gates in
[`11-acceptance-gates.md`](./11-acceptance-gates.md) all pass reproducibly.

---

## 7. How this document governs the build

Every phase in [`10-build-roadmap-and-gates.md`](./10-build-roadmap-and-gates.md)
is measured against section 4. Every feature PR is measured against section 4 and
must avoid every item in section 5. When in doubt, the ordering rule from the
prime directives applies: **enforcement precedes features.**
