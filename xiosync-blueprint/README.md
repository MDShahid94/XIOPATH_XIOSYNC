# XIOSYNC — Ground-Truth Rebuild Blueprint

> **This directory is the single source of truth for building XIOSYNC.**
> XIOSYNC is a clean-room, zero-legacy successor to **XIOPATH**. It keeps every
> good idea from XIOPATH and discards every compromised implementation. No file
> in this directory describes "what XIOPATH did"; it describes **what XIOSYNC
> must be** and **why**, with the XIOPATH evidence attached so the reasoning is
> auditable.

Any agent (human or AI) picking up this project MUST read this file first, then
read the documents in order. These documents are **normative**: the words
**MUST**, **MUST NOT**, **SHOULD**, and **MAY** are used in the RFC 2119 sense.

---

## Why this rebuild exists

XIOPATH is an ambitious platform: a universal graph that unifies identity,
capability, execution, memory, and provenance for coordinating humans, AI
models, tools, browsers, workflows, and distributed workers. The *concept* is
coherent and worth preserving.

The *implementation* diverged from the concept faster than the enforcement layer
could keep up. A forensic pass (see [`02-forensic-audit-xiopath.md`](./02-forensic-audit-xiopath.md))
confirmed, against the actual source, that:

- The **conceptual architecture advanced far ahead of the enforcement architecture.**
- Two competing vocabularies (`agent`/`actor`) coexist behind compatibility
  aliases, and one subsystem (Phantom) is wired to fields that no longer exist —
  it will raise at runtime.
- **Tenant isolation is aspirational, not enforced.** The tenant middleware runs
  before authentication resolves, so it stamps a `"pending"` placeholder.
- **Capability grants are stored but never checked** at execution time; the
  "policy enforcer" compares strings like `tenant_id == "suspended_tenant"`.
- **Schema ownership is split** between Alembic and a runtime `_init_db()`.
- **Migrations run per API replica at startup**, hardcoded to SQLite even when a
  Postgres `DATABASE_URL` is set.
- **CORS is `allow_origin_regex=".*"` with credentials enabled** — a wildcard
  that defeats the explicit allowlist next to it.

These are not cosmetic. They are structural. Patching them in place means fighting
the legacy every step. The decision recorded here is: **rebuild from a correct
foundation, port the good ideas, and never reintroduce the compromises.**

---

## The prime directives (non-negotiable)

1. **Enforcement precedes features.** No feature ships until the invariant it
   depends on is enforced and tested. Identity, tenancy, and capability checks
   are load-bearing, not decorative.
2. **One canonical vocabulary.** XIOSYNC uses `Actor`, `Operation`, `Capability`,
   `Edge`, `Event`, `Grant`. There are **no** `agent`/`actor` aliases. Ever.
3. **The schema has exactly one authority.** Migrations own the schema. No
   application code creates, alters, or probes tables at runtime.
4. **Every tenant-bearing row carries an immutable `organization_id`.** Every
   query that touches tenant data filters by it. There is no "global by default."
5. **Every capability is checked at the point of execution**, and every check
   emits an auditable decision record.
6. **Autonomy is gated.** AI-proposed changes (workflow corrections, memory
   merges, marketplace installs) are *proposals* subject to validation and
   approval. Untrusted workers never mutate global state.
7. **No quality degradation is acceptable.** A green compile is not evidence. A
   claim is not done until a reproducible test or operator check proves it, and
   the proof is recorded.

If a proposed change violates a prime directive, the change is wrong — not the
directive. Escalate and revise the blueprint deliberately, with a decision-log
entry.

---

## How to use these documents

Read in order. Each builds on the last.

| # | Document | Purpose |
|---|----------|---------|
| 00 | [`README.md`](./README.md) | This file. Prime directives and index. |
| 01 | [`01-vision-and-quality-bar.md`](./01-vision-and-quality-bar.md) | What XIOSYNC is, its product thesis, and the definition of "production-grade." |
| 02 | [`02-forensic-audit-xiopath.md`](./02-forensic-audit-xiopath.md) | Complete catalog of every remediation scope found in XIOPATH — critical and non-critical — each with evidence and the investigation that surfaced it. |
| 03 | [`03-ontology-formal-spec.md`](./03-ontology-formal-spec.md) | The mathematically/logically established domain model: entities, invariants, graph semantics, state machines. |
| 04 | [`04-target-architecture.md`](./04-target-architecture.md) | Control plane vs. execution plane, service boundaries, module map, data flow. |
| 05 | [`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md) | Identity model, sessions, tenancy, one authorization layer, capability enforcement, threat model. |
| 06 | [`06-persistence-schema.md`](./06-persistence-schema.md) | Single schema authority, migration policy, table invariants, indexes, immutability. |
| 07 | [`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md) | Durable execution, worker enrollment, DLQ/self-learning governance, the Phantom boundary. |
| 08 | [`08-frontend-contract.md`](./08-frontend-contract.md) | Frontend reliability, accessibility, state, transport, and the route/permission matrix. |
| 09 | [`09-deployment-ops-ci.md`](./09-deployment-ops-ci.md) | Deployment, CI gates, observability, backup/DR, rollout/rollback. |
| 10 | [`10-build-roadmap-and-gates.md`](./10-build-roadmap-and-gates.md) | The phased from-scratch build order with entry/exit criteria per phase. |
| 11 | [`11-acceptance-gates.md`](./11-acceptance-gates.md) | The global definition of done. Nothing is "complete" until these pass. |
| 12 | [`12-investigation-playbook.md`](./12-investigation-playbook.md) | For every concept, the broadest investigation required to re-derive, verify, or extend it — so findings can be reproduced, not trusted blindly. |
| — | [`DECISIONS.md`](./DECISIONS.md) | Append-only architectural decision log. Durable decisions live here. |
| — | [`GLOSSARY.md`](./GLOSSARY.md) | Canonical terms. If a word is not here, it is not canonical. |

---

## Working rules for any agent

1. **Read before writing.** These docs, then the relevant target-state section,
   then the code.
2. **Never reintroduce a legacy pattern** listed in document 02. If you find
   yourself adding an alias, a runtime `CREATE TABLE`, a wildcard CORS, or an
   unchecked capability, stop.
3. **Every change is deployable and narrowly scoped**, and lands with a
   security-negative test, not just a happy path.
4. **Record decisions** in [`DECISIONS.md`](./DECISIONS.md). Do not bury durable
   decisions in commit messages or chat.
5. **Verify, then claim.** Attach the exact command and result. If a check could
   not run, record the blocker verbatim — never claim a green you did not see.
6. **The blueprint is living but disciplined.** Improving it is encouraged;
   silently contradicting it is not. Change the document and log why.

---

## Status

This blueprint was authored from a forensic re-investigation of the XIOPATH
codebase (~35,700 LOC across FastAPI, core Python services, React/Vite, Alembic,
and a Manifest V3 extension). Every claim in document 02 is traceable to a file
and line in that source. XIOSYNC has **not** been built yet — this is the
foundation it must be built on.
