# 03 — Ontology Formal Spec

> Normative. The mathematically/logically established domain model for XIOSYNC:
> entities, invariants, graph semantics, and state machines. Everything the
> platform stores or enforces derives from this document. If code contradicts
> this spec, the code is wrong.

---

## 1. Design principles

1. **One vocabulary.** The canonical entities are `Actor`, `Capability`, `Grant`,
   `Operation`, `Edge`, `Event`, `Memory`, `Organization`, `AuthIdentity`,
   `Session`, `Workflow`, `WorkflowRun`, `Worker`. No synonyms, no aliases.
   ([`GLOSSARY.md`](./GLOSSARY.md) is the authority for terms.)
2. **Three primitives, made executable.** Identity (`Actor`), Knowledge
   (`Memory`), Action (`Capability`) — but each is bound to enforcement, not just
   description.
3. **Tenancy is a property of the model, not the query.** Every tenant-bearing
   entity has an immutable `organization_id`. Isolation is a schema invariant.
4. **Types are data, with one authority.** The Type Registry defines valid type
   values. Code constants exist only to bootstrap it.
5. **Graphs are typed and their acyclicity is explicit per graph**, not assumed.
6. **Provenance is append-only and immutable**, enforced at the persistence layer.

---

## 2. Entities and their invariants

Notation: `PK` primary key, `FK` foreign key, `IMM` immutable after creation,
`REQ` required (non-null, non-defaulted at the API boundary).

### 2.1 Organization
The tenant boundary. The root of all isolation.
- `id` PK, UUIDv7, IMM
- `slug` REQ, unique, IMM
- `name` REQ
- `state` ∈ {`active`, `suspended`, `archived`}
- `created_at` IMM

**INV-ORG-1:** An `Organization` is never a child of another organization. There
is no org hierarchy in v1. (Sub-orgs, if ever needed, are a deliberate future ADR.)

### 2.2 AuthIdentity
An authentication principal (login credentials).
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM
- `human_actor_id` FK→Actor, REQ, IMM, unique (1:1)
- `email` REQ, unique within organization
- `password_hash` REQ (argon2id or bcrypt; never plaintext, never optional)
- `state` ∈ {`active`, `locked`, `disabled`}
- `failed_attempts`, `locked_until` (lockout policy)
- `created_at` IMM

**INV-AUTH-1:** Each `AuthIdentity` maps to exactly one `HumanActor`
(`actor_type = human`) and vice versa.
**INV-AUTH-2:** An `AuthIdentity` belongs to exactly one `Organization`, fixed at
creation.

### 2.3 Actor
Any participating entity: human, AI, or compute.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM
- `actor_type` REQ ∈ TypeRegistry(`actor_type`) — bootstrap set {`human`, `ai`, `compute`}
- `actor_subtype` ∈ TypeRegistry(`actor_subtype[actor_type]`)
- `role` — scoped role reference, not a free string (see §5)
- `alias` — human-readable label
- `parent_id` FK→Actor (organizational/structural parent; **not** a tenancy key)
- `state` — lifecycle state (see §4.1)
- `lifecycle_phase` ∈ {`pre_birth`, `birth`, `operational`, `end_of_life`}
- `trust_tier` ∈ {`newcomer`, `contributor`, `trusted`, `core`, `admin`} (see §7)
- `config` IMM (init args), `runtime_state` (mutable live state)
- `health_status` ∈ {`healthy`, `degraded`, `offline`, `unknown`}
- `last_heartbeat`, `created_at` IMM, `updated_at`, `created_by` FK→Actor

**INV-ACTOR-1:** `organization_id` is set at creation and never changes.
**INV-ACTOR-2:** `parent_id`, if set, MUST reference an Actor in the *same*
organization. Cross-org parenting is forbidden.
**INV-ACTOR-3:** `actor_type`/`actor_subtype` MUST be valid in the Type Registry
at write time.

### 2.4 Capability
A registered, invokable ability.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization for private capabilities; NULL only for
  platform-global capabilities defined by the platform itself (see INV-CAP-2)
- `name` REQ, `capability_type` ∈ TypeRegistry(`capability_type`) — bootstrap
  {`browser`, `api`, `plugin`, `llm`, `system`}
- `version`, `description`
- `input_schema`, `output_schema` (JSON Schema)
- `execution_mode` ∈ {`sync`, `async`, `streaming`}
- `timeout_ms`, `retry_policy`
- `state` ∈ {`active`, `deprecated`, `disabled`}

**INV-CAP-1:** A capability is invokable only through a valid `Grant` (see §6).
**INV-CAP-2:** Platform-global capabilities (`organization_id` NULL) are defined
only by platform migrations/seed, never by tenant API calls. Tenant-created
capabilities MUST carry the creating `organization_id`.

### 2.5 Grant
Authorization linking an Actor to a Capability. This is the load-bearing authz
record.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM
- `actor_id` FK→Actor, REQ
- `capability_id` FK→Capability, REQ
- `granted_by` FK→Actor, REQ
- `scope` ∈ {`full`, `read_only`, `execute_only`, `limited`}
- `constraints` (JSON: rate, resource allowlist, argument bounds, time windows)
- `state` ∈ {`active`, `revoked`, `expired`}
- `expires_at`, `created_at` IMM, `revoked_at`, `revoked_by`

**INV-GRANT-1:** `actor_id`, `capability_id`, and `granted_by` MUST belong to the
same `organization_id` as the grant (except when `capability_id` is a
platform-global capability).
**INV-GRANT-2:** A grant authorizes execution only while `state = active` and
(`expires_at` is null or in the future).
**INV-GRANT-3:** Revocation is a state transition to `revoked` with `revoked_at`/
`revoked_by` set; grants are never hard-deleted.

### 2.6 Operation
A first-class record of an Actor's lifecycle transition or meaningful activity.
Ported from XIOPATH's strongest design.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM
- `actor_id` FK→Actor, REQ
- `operation` ∈ TypeRegistry(`operation_type`)
- `from_state`, `to_state`
- `trigger` ∈ {`user_command`, `schedule`, `auto`, `error`, `system`}
- `initiated_by` FK→Actor, REQ
- `collaborators` (JSON: `[{actor_id, role_in_operation}]`)
- `scope` ∈ {`actor`, `component`, `organization`}
- `depth_level`, `parent_operation_id` FK→Operation
- `artifacts`, `rationale`, `outcome` ∈ {`success`, `partial`, `failed`, `pending`}
- `started_at` IMM, `completed_at`, `duration_ms`

**INV-OP-1:** `parent_operation_id` forms an acyclic tree (see §3, hierarchy graph).
**INV-OP-2:** All referenced actors share the operation's `organization_id`.

### 2.7 Edge
A typed, directed relationship between two Actors.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM
- `source_id` FK→Actor, REQ; `target_id` FK→Actor, REQ
- `edge_type` ∈ TypeRegistry(`edge_type`) — bootstrap {`manages`, `delegates_to`,
  `collaborates_with`, `provides`, `owns`}
- `graph_class` ∈ {`hierarchy`, `workflow`, `relationship`, `dependency`} (see §3)
- `weight`, `state` ∈ {`active`, `inactive`}
- `created_at` IMM

**INV-EDGE-1:** `source_id` and `target_id` MUST be in the same organization as
the edge.
**INV-EDGE-2:** An edge's acyclicity constraint is determined by its `graph_class`
(see §3), validated on write.

### 2.8 Event
Append-only telemetry/audit record.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM (nullable only for
  platform-lifecycle events with no tenant)
- `actor_id` FK→Actor
- `event_type` ∈ TypeRegistry(`event_type`) — bootstrap {`action_executed`,
  `error`, `state_change`, `heartbeat`, `tool_invoked`, `auth_event`, `metric`,
  `policy_decision`}
- `severity` ∈ {`debug`, `info`, `warn`, `error`, `critical`}
- `summary`, `payload` (JSON), `correlation_id`, `operation_id` FK→Operation
- `prev_hash`, `hash` (optional chained integrity for high-assurance streams)
- `created_at` IMM

**INV-EVENT-1:** Events are insert-only. There is no application update or delete
path. (Enforced by DB grants; see [`06-persistence-schema.md`](./06-persistence-schema.md).)
**INV-EVENT-2:** Every `policy_decision` event records the decision id, inputs
(actor, capability, resource, org), and the allow/deny outcome.

### 2.9 Memory
Knowledge owned by an Actor.
- `id` PK, UUIDv7, IMM
- `organization_id` FK→Organization, REQ, IMM
- `owner_actor_id` FK→Actor, REQ
- `kind` ∈ {`observation`, `intention`, `outcome`, `fact`}
- `content` (JSON/text), `embedding_ref` (vector store pointer)
- `visibility` ∈ {`private`, `org_shared`}
- `provenance` (JSON: source operation/event, confidence)
- `version`, `superseded_by` FK→Memory
- `created_at` IMM

**INV-MEM-1:** Memory never crosses organizations. `org_shared` means shared
within the owning organization only.
**INV-MEM-2:** Merges (e.g. CRDT LWW) produce a new version with provenance;
originals are retained (see [`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md)).

### 2.10 Session
Server-side authentication session.
- `id` PK, UUIDv7, IMM
- `auth_identity_id` FK→AuthIdentity, REQ
- `organization_id` FK→Organization, REQ, IMM
- `refresh_token_hash` REQ, `access_token_jti` (current)
- `state` ∈ {`active`, `revoked`, `expired`}
- `created_at` IMM, `last_used_at`, `expires_at`, `revoked_at`

**INV-SESSION-1:** Access tokens are validated against an `active` session.
**INV-SESSION-2:** Password change or logout transitions all of an identity's
sessions to `revoked`.

### 2.11 Workflow & WorkflowRun
- **Workflow:** `id`, `organization_id` REQ IMM, `name`, `version`, `spec` (the
  DAG definition), `state` ∈ {`draft`, `published`, `deprecated`}, `created_by`.
- **WorkflowRun:** `id`, `organization_id` REQ IMM, `workflow_id` FK,
  `state` ∈ {`queued`, `running`, `paused`, `succeeded`, `failed`, `cancelled`},
  `initiated_by` FK→Actor, `started_at`, `finished_at`, correlation to Operations
  and Events.

**INV-WF-1:** A Workflow `spec` MUST be a validated DAG (see §3, workflow graph).
Publishing a cyclic spec is rejected.

### 2.12 Worker
An enrolled execution node.
- `id`, `organization_id` (or `platform` for shared pools — deliberate ADR),
  `actor_id` FK→Actor (`actor_type = compute`), `enrollment_state`,
  `trust_tier`, `capabilities` (granted), `credential_ref` (short-lived),
  `last_heartbeat`, `state`.

**INV-WORKER-1:** A worker receives only tasks it holds a valid Grant for, in its
organization/pool.
**INV-WORKER-2:** Worker credentials are short-lived and per-worker (see
[`07-execution-workers-phantom.md`](./07-execution-workers-phantom.md)).

---

## 3. Graph semantics (H5 remediation)

XIOSYNC has **four distinct graphs**, each with its own acyclicity rule. Edges
declare their `graph_class`. It is false to call the whole ontology "a DAG."

| Graph | Members | Acyclic? | Enforced when |
|---|---|---|---|
| **Hierarchy** | Actor `parent_id`, Operation `parent_operation_id` | **Yes** | On write (reject if it would create a cycle) |
| **Workflow** | Workflow `spec` nodes/edges | **Yes** | On publish (full DAG validation) |
| **Relationship** | Edges: `collaborates_with`, `provides` | **No** (cycles allowed) | Not applicable |
| **Dependency** | Edges: `delegates_to`, `manages`, `owns` | **Per-semantics** | On write, per edge-type rule |

**Acyclicity check (hierarchy/workflow):** adding edge `u → v` is rejected if `u`
is reachable from `v` in the same graph class within the same organization.

**Cross-organization edges are forbidden in every graph class** (INV-EDGE-1).

---

## 4. State machines

### 4.1 Actor lifecycle
```
proposed → designing → implementing → validating → initializing → active
active → updating → active
active → suspended → active
active → migrating → active
active → terminating → terminated → archived
```
- Phases: `pre_birth` = {proposed, designing, implementing, validating};
  `birth` = {initializing}; `operational` = {active, updating, suspended,
  migrating}; `end_of_life` = {terminating, terminated, archived}.
- **INV-LC-1:** Only declared transitions are legal. Any other transition is
  rejected and produces no state change.
- **INV-LC-2:** Every transition writes an `Operation` and a `state_change`
  `Event`.
- Valid lifecycle states/transitions are Type-Registry data; the list above is
  the bootstrap default.

### 4.2 Grant lifecycle
```
active → revoked        (explicit revocation)
active → expired        (expires_at passes; lazily materialized on read + swept)
```
No transition out of `revoked` or `expired`. A new grant is a new row.

### 4.3 Session lifecycle
```
active → revoked        (logout, password change, admin action)
active → expired        (expires_at passes)
```

### 4.4 WorkflowRun lifecycle
```
queued → running → (succeeded | failed | cancelled)
running → paused → running
running → cancelled
failed → (DLQ)          (see 07: governed correction, never auto-mutation)
```

### 4.5 Worker enrollment lifecycle
```
pending → enrolled → active
active → draining → offline
active → suspended → active
any → revoked           (terminal)
```

---

## 5. Roles and authority (H4 remediation)

`role` is **never** a single overloaded string. Authority has three orthogonal
axes, each represented separately:

1. **Platform role** — `platform_admin` | `none`. Governs platform-level
   operations (never granted by public signup).
2. **Organization membership role** — `org_owner` | `org_admin` | `org_member` |
   `org_viewer`, scoped to one `(auth_identity, organization)`.
3. **Execution capability** — expressed *only* through `Grant` records, never
   through a role string.

**INV-ROLE-1:** Public signup can only ever produce `org_member` (or the first
bootstrap owner via the audited flow in
[`05-security-identity-tenancy.md`](./05-security-identity-tenancy.md)); it can
never assign `platform_admin`.

---

## 6. The authorization decision (C3 remediation)

All privileged execution passes through exactly one decision function:

```
authorize(actor, operation, capability, resource, organization, constraints)
  → Decision { allowed: bool, decision_id: uuid, reason: str }
```

It evaluates, in order:
1. `actor.organization_id == organization` (tenant match) — else deny.
2. `resource.organization_id == organization` — else deny.
3. Organization state is `active` — else deny.
4. A `Grant` exists for `(actor, capability)` in this org, `state = active`, not
   expired, and its `scope`/`constraints` permit `operation` on `resource` — else
   deny.
5. Trust-tier and rate constraints from the grant are satisfied — else deny.

**INV-AUTHZ-1:** Every call emits a `policy_decision` Event with `decision_id`,
inputs, and outcome (INV-EVENT-2).
**INV-AUTHZ-2:** There is no code path that executes a capability without a prior
`allowed = true` decision.

---

## 7. Trust tiers (worker governance)

`newcomer → contributor → trusted → core → admin`, ported from XIOPATH's ledger
concept but bound to real enforcement:
- Promotion requires verifiable successful-execution proofs; demotion on failure.
- **INV-TRUST-1:** An actor below the tier required by a grant's `constraints`
  cannot execute that capability, even with an otherwise-valid grant.
- **INV-TRUST-2:** Untrusted actors (`newcomer`/`contributor`) never mutate global
  or cross-actor state; they operate only in isolated scopes.

---

## 8. Type Registry (H3 remediation)

A single service owns valid type values for: `actor_type`, `actor_subtype`,
`capability_type`, `operation_type`, `edge_type`, `event_type`, `lifecycle_state`.

- Definitions are **namespaced** (`core.*` vs tenant/plugin namespaces),
  **versioned**, **validated**, support **deprecation** and **migration aliases**,
  with **cached reads and explicit invalidation**.
- Code constants (the bootstrap sets in this document) exist **only** to seed the
  registry on first migration. At runtime, the registry is authoritative.
- **INV-TYPE-1:** Writing an entity with a type value not present (and not
  deprecated-but-allowed) in the registry is rejected.
- **INV-TYPE-2:** No subsystem may introduce a type value by using it; it must
  register it first.

---

## 9. Formal invariant summary (the checklist enforcement must satisfy)

1. Every tenant-bearing row has an immutable `organization_id`. *(C2)*
2. No entity references another entity in a different organization. *(C1, isolation)*
3. Every capability invocation is preceded by an `allowed` authorization decision
   with an audit record. *(C3)*
4. Only declared state transitions occur; each writes an Operation + Event. *(H5, provenance)*
5. Hierarchy and workflow graphs are acyclic, validated on write. *(H5)*
6. Events and (versioned) Memory are append-only; no destructive application path. *(H6)*
7. Type values are valid in the Type Registry at write time. *(H3)*
8. `AuthIdentity ↔ HumanActor` is 1:1; authority axes are separate. *(H4)*
9. Sessions are server-side, revocable; password change revokes all. *(C8)*
10. Untrusted actors never mutate global state. *(C9, trust)*

These invariants are the contract every later document implements and every test
in [`11-acceptance-gates.md`](./11-acceptance-gates.md) verifies.
