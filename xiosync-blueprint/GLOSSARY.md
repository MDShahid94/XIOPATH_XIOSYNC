# GLOSSARY — Canonical Terms

> If a word is not in this glossary, it is **not canonical** and must not appear
> in XIOSYNC code, schema, API surfaces, or docs as a domain term. To add a term:
> define it here first (with a DECISIONS.md entry if it introduces a concept),
> then use it. One concept, one name — synonyms and aliases are forbidden
> (that rule exists because of XIOPATH finding H1).

---

## Core entities (doc 03)

| Term | Definition |
|---|---|
| **Organization** | The tenancy boundary. Every tenant-owned row carries its `organization_id`. Nothing crosses it except by explicit, audited design. |
| **AuthIdentity** | A globally unique authenticated principal (human or service). Owns credentials. Has no authority by itself. |
| **Actor** | The unit of agency *within* an Organization. Linked to at most one AuthIdentity per org. All authority attaches to Actors via Grants. |
| **Capability** | A named, registered permission to perform a class of Operations. Capabilities are data, defined in the Type Registry — never hardcoded strings scattered in logic. |
| **Grant** | The time-bounded assignment of a Capability to an Actor, with scope. Grants are the *only* source of authority and are read at decision time (D-004). |
| **Operation** | A discrete, authorizable action against a resource. The unit the authorization decision reasons about. |
| **Edge** | A typed, directed relation between two ontology entities. Edge kinds declare their constraints (e.g., DAG kinds are cycle-checked at write time). |
| **Event** | An immutable, append-only record of something that happened. The app database role cannot UPDATE or DELETE event rows (D-009). |
| **Memory** | Versioned knowledge attached to an Actor or workflow. New versions append; "current" is a derived pointer. Never overwritten. |
| **Session** | An opaque, server-side login record referenced by an HttpOnly cookie. Revocable immediately (D-005). |
| **Workflow** | A declared, versioned definition of orchestrated work. |
| **WorkflowRun** | One execution of a Workflow version, with its own lifecycle state machine (doc 03 §4.4). |
| **Worker** | An enrolled execution-plane process holding short-lived, self-scoped credentials (D-007). |

## Authority & security (doc 05)

| Term | Definition |
|---|---|
| **Decision point** | The single function that answers every authorization question. There is exactly one (D-004). |
| **Bootstrap** | The documented procedure that creates the first administrator of a fresh deployment. The only privileged-creation path that bypasses an existing Grant, and it self-disables after use (doc 05 §6). |
| **Trust tier** | The governance level assigned to a Worker or plugin, constraining what task classes and secret scopes it may receive (doc 03 §7). |
| **Task credential** | A secret minted for one task, scoped to it, expiring with it (doc 07 §3). |
| **One-time ticket** | A short-lived single-use token used solely to authenticate a WebSocket handshake when the cookie cannot ride along. |

## Execution plane (doc 07)

| Term | Definition |
|---|---|
| **Control plane** | The API, authorization spine, persistence, and orchestration services. Never executes tenant/plugin code in-process. |
| **Execution plane** | Workers, sandboxes, and the isolation-tier subsystem — where work actually runs. |
| **Sandbox** | The out-of-process, resource/fs/network-limited environment where all plugin code executes (D-008). |
| **Plugin** | Third-party or tenant-supplied executable capability. Only ever runs in a Sandbox. |
| **Proposal** | A suggested state change produced by automated analysis (e.g., DLQ processing). Inert until approved by a distinct granted authority (D-008). |
| **DLQ** | Dead-letter queue: where failed tasks land for analysis. Its consumer may only write Proposals. |
| **Isolation tier** | The Phantom-successor subsystem for chained, isolated execution. Feature-flagged until its contract tests pass (D-010). |
| **Chain** | A registered sequence of isolation-tier steps. No chain registers without a passing contract test against real entity shapes. |

## Persistence (doc 06)

| Term | Definition |
|---|---|
| **Type Registry** | The persisted catalog of entity types, edge kinds, and capabilities. The runtime consults it; logic never hardcodes type names (H3 remediation). |
| **Migration chain** | The single linear sequence of migrations — the only code allowed to emit DDL (D-003). |
| **Repository** | The persistence-layer module for one aggregate. Every method on a tenant-owned aggregate requires `organization_id` (D-006). |
| **Schema version** | The migration head a database is at. Replicas refuse to serve if behind. |

## Process & quality (docs 01, 10–12)

| Term | Definition |
|---|---|
| **Blueprint** | This document set (`xiosync-blueprint/`). The ground truth for the rebuild. |
| **Finding** | An audited defect, IDed by severity: **C** (critical), **H** (high), **M** (medium), **L** (low) — catalog in doc 02. |
| **Gate** | A falsifiable acceptance check (doc 11) mapped to a named CI job (D-012). A gate that cannot fail is not a gate. |
| **Phase** | A roadmap stage (doc 10) that ends only when its gates pass. No phase-skipping. |
| **Investigation** | The reproduction procedure (doc 12) that verifies a blueprint claim against the living codebase. |
| **Four-state contract** | Every frontend async surface distinctly renders loading, empty, error, and success (doc 08 §5). |

---

## Forbidden terms

These words carried ambiguity or falsehood in XIOPATH and must not appear as
domain terms in XIOSYNC code, schema, or API surfaces:

| Forbidden | Why | Use instead |
|---|---|---|
| **agent** (as entity name) | H1 — alias of `actor`; two vocabularies for one concept | **Actor** |
| **user** (as schema/domain term) | Conflates AuthIdentity with Actor (H4) | **AuthIdentity** or **Actor**, whichever is meant |
| **super admin** (seeded) | H8 — bootstrap must not seed ontology superusers | **Bootstrap** administrator via doc 05 §6 |
| **pending** (as tenant value) | C1 — placeholder tenancy | derive org from **Session** only |
| **phantom** (as module name) | Names the broken XIOPATH subsystem; carries its field contract | **Isolation tier** |
| **role** (as inline check) | Bypasses the decision point (C3-class regression) | **Capability** + **Grant** via the decision point |
| **soft delete** (on events) | H6 — events are append-only, not "deleted" | append a compensating **Event** |

---

*One concept, one name. When in doubt, this file wins over any other document.*
