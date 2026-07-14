# 05 — Security, Identity & Tenancy

> Normative. The load-bearing document. Defines identity, sessions, tenancy, the
> single authorization layer, and the threat model. Remediates C1, C3, C8, H4,
> H8, and supports C2/C9. RFC 2119 keywords binding.

If any other document or any code contradicts this one on a security matter,
this document wins.

---

## 1. Identity model (H4 remediation)

XIOSYNC separates **who authenticated** from **what participates** from **which
tenant**. Three distinct concepts, one explicit mapping:

```
AuthIdentity  ──1:1──  HumanActor  ──member of──▶  Organization
     │                     │                            ▲
 authenticated by      participates as            tenant boundary
     ▼                     │
  Session             Grant authorizes Actor → Capability
```

- **`AuthIdentity`** — login credentials (email + password hash). Never acts;
  only authenticates. (doc 03 §2.2)
- **`HumanActor`** — the graph participant for a human. Exactly one per
  AuthIdentity (INV-AUTH-1).
- **`Organization`** — the tenant boundary and root of isolation (doc 03 §2.1).
- **`Session`** — a server-side, revocable authentication session (doc 03 §2.10).

**INV-ID-1:** A JWT/access token identifies exactly one `(AuthIdentity, Session,
Organization, HumanActor)` tuple. There is no token that is ambiguous about org
or actor.
**INV-ID-2:** There is no anonymous actor, no `"pending"` identity, and no
"super admin" seeded actor (H8). System bootstrap uses a neutral `system-root`
principal that cannot log in and holds no password.

### 1.1 Authority axes (never one overloaded `role` string — H4)

Three orthogonal axes, each stored separately (doc 03 §5):

1. **Platform role** ∈ {`platform_admin`, `none`}. Governs platform operations.
   **Never** assignable by public signup or any tenant API. Granted only via the
   audited bootstrap flow (§6) or by an existing `platform_admin`.
2. **Organization membership role** ∈ {`org_owner`, `org_admin`, `org_member`,
   `org_viewer`}, scoped to one `(AuthIdentity, Organization)` pair via a
   `Membership` record. An identity MAY belong to multiple orgs with different
   roles; the active org is fixed per session.
3. **Execution capability** — expressed **only** through `Grant` records
   (doc 03 §2.5). No role string ever implies capability.

**INV-ROLE-1 (restated):** Public signup produces at most `org_member`. It can
never produce `platform_admin` or `org_owner` (owner arises only from org
creation or the bootstrap flow).

---

## 2. Authentication & sessions (C8 remediation)

### 2.1 Credentials

- Passwords hashed with **argon2id** (bcrypt permitted only as an explicit,
  documented fallback). Plaintext or reversible storage is forbidden.
- Password verification is constant-time. Failed attempts increment
  `failed_attempts`; threshold breach sets `locked_until` (lockout policy).
- Crypto libraries are **hard dependencies**. If unavailable at startup, the
  process fails fast — never a plaintext fallback (M6).

### 2.2 Token & session lifecycle

```
login  → validate credentials
       → create Session (server-side row, refresh_token_hash stored)
       → issue short-lived access token (≤15 min, HS256/EdDSA, carries jti,
         session_id, org_id, actor_id)
       → issue rotating refresh token (opaque; only its hash is stored)

refresh → present refresh token → verify against active Session
        → rotate: old refresh hash invalidated, new one stored (reuse ⇒ revoke
          the whole session family and alert — token-theft detection)
        → issue new access token

logout        → Session.state = revoked
password change → ALL sessions for the identity → revoked (INV-SESSION-2)
admin revoke   → target Session(s) → revoked
```

- **INV-SESSION-1:** Every access token is validated against an `active` Session
  on every request. A token whose session is `revoked`/`expired` is rejected
  even before expiry. This is the kill switch XIOPATH lacked (C8).
- **INV-SESSION-2:** Password change or logout revokes all sessions for that
  identity.
- **INV-SESSION-3:** Refresh-token reuse (a rotated token presented twice)
  revokes the entire session family and emits a `critical` `auth_event`.
- Access-token validation checks the server-side session; to avoid a DB hit per
  request, sessions MAY be cached with a short TTL, but revocation MUST
  invalidate the cache within a bounded, documented window (default ≤30s).

### 2.3 Transport (M2 remediation)

- Browser session transport: **HTTP-only, `Secure`, `SameSite=Strict` cookies**,
  or a strictly memory-held access token with silent refresh. Access tokens
  **never** touch `localStorage`/`sessionStorage`.
- WebSocket authentication happens in the **handshake** (cookie or
  `Sec-WebSocket-Protocol` subprotocol), **never** a `?token=` query string
  (which leaks into logs/proxies). See doc 08.

---

## 3. Tenancy & isolation (C1, C2 remediation)

### 3.1 The resolution guarantee

**INV-TENANT-1:** Identity and organization are resolved by authentication
middleware that runs **before any tenant-scoped logic** (doc 04 §2.4). The
resolved context is:

```
OrgContext {
  auth_identity_id,        # who
  actor_id,                # participating HumanActor
  organization_id,         # tenant — REQUIRED, never defaulted, no "pending"
  session_id,
  platform_role,           # none | platform_admin
  membership_role,         # org_* for this org
}
```

There is **no** code path that produces an `OrgContext` with a placeholder org
(C1). If org cannot be resolved, the request is rejected with 401/403 before
reaching a handler.

### 3.2 The isolation invariant

**INV-TENANT-2:** Every tenant-bearing row carries an immutable, indexed
`organization_id` set at creation (C2; doc 06). **INV-TENANT-3:** Every
repository method that reads or writes tenant data takes `OrgContext` as a
required parameter and filters by `organization_id`. There is no "global by
default" query.

Enforcement is layered so a single mistake cannot open a cross-tenant hole:

1. **Application layer:** repositories require `OrgContext`; a lint/type rule
   forbids raw table access outside repositories.
2. **Database layer:** PostgreSQL **Row-Level Security** policies keyed on a
   per-transaction `app.current_org` setting provide defense-in-depth. Even a
   buggy query cannot read another org's rows.
3. **Test layer:** every tenant-touching feature ships a **cross-tenant
   negative test** that MUST fail to access another org's data (doc 11).

**INV-TENANT-4:** No entity may reference an entity in a different organization
(doc 03 INV-EDGE-1, INV-ACTOR-2, INV-GRANT-1, etc.). Cross-org FKs are rejected
at write time and structurally impossible under RLS.

### 3.3 Platform-role cross-org access

`platform_admin` operations that legitimately span orgs (e.g. platform health,
abuse investigation) go through a **dedicated admin service** that (a) requires
`platform_role = platform_admin`, (b) sets an explicit "cross-org" flag, and (c)
emits a high-severity audit Event for every access. Ordinary handlers can never
cross orgs regardless of role.

---

## 4. Authorization — the single decision point (C3 remediation)

All privileged execution passes through **exactly one** function (doc 03 §6):

```python
authorize(
    actor, operation, capability, resource, organization, constraints
) -> Decision(allowed: bool, decision_id: UUID, reason: str)
```

Evaluation order (fail-closed at the first failing check):

1. **Tenant match:** `actor.organization_id == organization` — else deny.
2. **Resource tenancy:** `resource.organization_id == organization` — else deny.
3. **Org active:** organization state is `active` — else deny.
4. **Grant exists & valid:** an `active`, unexpired `Grant` for
   `(actor, capability)` in this org whose `scope`/`constraints` permit
   `operation` on `resource` — else deny. **This reads real grant rows.** There
   is no hardcoded string comparison (kills C3's `tenant_id == "suspended_tenant"`).
5. **Trust & rate:** the actor's `trust_tier` meets the grant's required tier and
   rate/resource/argument constraints are satisfied — else deny.

**INV-AUTHZ-1:** Every call emits a `policy_decision` Event recording
`decision_id`, all inputs (actor, capability, resource, org), and the outcome
(doc 03 INV-EVENT-2). Deny decisions are logged as thoroughly as allows.
**INV-AUTHZ-2:** There is **no** code path that executes a capability without a
prior `allowed = true` decision from this function. This is enforced by
architecture (only the `authz` module can authorize) and by test (every
execution entry point has an unauthorized-attempt test).
**INV-AUTHZ-3:** Authorization is **fail-closed**. Any error, missing grant,
unknown capability, or unreachable dependency yields `deny`, never a default
allow.

### 4.1 Grants are checked, not decorative

XIOPATH stored grants and never read them (C3). In XIOSYNC:
- Grant creation validates that grantor, grantee, and capability share the org
  (INV-GRANT-1) and that the grantor is authorized to delegate.
- Grant evaluation is the *only* source of execution authority.
- Revocation is a state transition (`active → revoked`), never a delete
  (INV-GRANT-3); revoked grants remain for audit.

---

## 5. Worker & plugin credential trust (H7, C10 support)

Detailed in doc 07; the security invariants that bind here:

- **INV-WCRED-1:** Workers **never** hold the platform JWT signing secret (kills
  H7's shared `XIOPATH_JWT_SECRET`). They enroll and receive short-lived,
  per-worker, capability-scoped credentials, independently revocable.
- **INV-WCRED-2:** Plugins run out-of-process with no ambient access to platform
  secrets, an explicit network allowlist, and an explicit capability grant
  (C10). Installation requires approval.
- **INV-WCRED-3:** Any credential (worker or plugin) is minted per-lease where
  possible and expires; long-lived broadly-scoped credentials are forbidden.

---

## 6. Bootstrap & the first administrator (H8 remediation)

XIOPATH auto-seeded a "Super Admin" actor (H8). XIOSYNC does not.

- Migrations/seed create only `system-root`: a non-login platform principal used
  as `created_by` for platform-owned rows. It has no password, no session, and
  cannot authenticate.
- The **first `platform_admin`** is established by a one-time, audited bootstrap
  flow: an operator runs a signed bootstrap command (out-of-band, requires DB +
  a one-time bootstrap secret) that promotes a named, already-registered
  AuthIdentity to `platform_admin`. The bootstrap secret is single-use and the
  promotion emits a permanent audit Event.
- After first admin exists, further `platform_admin` grants require an existing
  `platform_admin` and are fully audited.

**INV-BOOT-1:** No privileged principal ever exists without a traceable,
audited act that created it.

---

## 7. Secrets & key management (H9, L4, M6 support)

- **INV-SEC-1:** No secret has an embedded default. Missing required secrets
  fail startup in **every** environment (kills L4's
  `"xiopath-dev-secret-change-in-production"`).
- **INV-SEC-2:** Secret ciphertext and its decryption key are **never** colocated
  on application disk (kills H9's `data/secrets.json` + `data/.vault_key`).
  Secrets come from a managed backend (env → KMS/managed vault).
- **INV-SEC-3:** Signing keys support rotation with an overlap window; the
  current `kid` is carried in token headers.
- **INV-SEC-4:** Crypto is a hard dependency; its absence is a startup failure,
  never a plaintext fallback (M6).

---

## 8. Threat model

Adversaries and the controls that answer them:

| # | Threat | Primary control | Verified by |
|---|---|---|---|
| T1 | Cross-tenant data access | Immutable `organization_id` + repo-required OrgContext + RLS | Cross-tenant negative tests (doc 11) |
| T2 | Stolen access token replay | Server-side revocable sessions; short TTL; refresh rotation | Session-revocation test |
| T3 | Refresh-token theft | Rotation + reuse detection → family revoke | Reuse-detection test |
| T4 | Privilege escalation via role | Separate authority axes; signup capped at `org_member` | Escalation negative test |
| T5 | Unauthorized capability use | Single fail-closed decision point reading real grants | Unauthorized-execution test |
| T6 | Compromised volunteer worker | Per-worker scoped short creds; results validated; lowest tier can't mutate global | Worker-isolation test |
| T7 | Malicious plugin (RCE) | Out-of-process sandbox, no ambient secrets, network allowlist, approval | Plugin-sandbox test (doc 07) |
| T8 | CSRF / credential exposure | Origin allowlist (no wildcard), SameSite cookies | CORS config test (doc 09) |
| T9 | Autonomous state corruption | Corrections are governed proposals; untrusted actors can't mutate global | DLQ-governance test (doc 07) |
| T10 | Audit tampering | Insert-only events, restricted DB grants, optional hash-chain | Immutability test (doc 06) |
| T11 | Secret disclosure via disk | Managed secret backend; key never with ciphertext | Deployment review (doc 09) |
| T12 | Migration/schema drift attack surface | Single schema authority; migrate-then-serve gate | Migration-chain test (doc 06) |

**INV-THREAT-1:** Every control above ships with the named security-negative
test. A feature touching one of these surfaces is not "done" until its test
passes reproducibly (doc 01 §4.6, doc 11).

---

## 9. What this document forbids (security anti-patterns)

Restating, with the finding each kills:

- A `"pending"` / placeholder / defaulted organization on any request. **(C1)**
- A tenant-bearing table or query without `organization_id`. **(C2)**
- An authorization check that compares against a hardcoded identifier instead of
  reading grants. **(C3)**
- An access token with no server-side revocation. **(C8)**
- A single overloaded `role` string mixing platform/org/capability authority. **(H4)**
- An auto-seeded privileged actor. **(H8)**
- A worker or plugin holding the platform signing secret or long-lived broad
  credentials. **(H7)**
- Any embedded secret default or plaintext-crypto fallback. **(L4, M6)**
- Secret key material stored next to ciphertext on app disk. **(H9)**
- A wildcard CORS origin with credentials. **(C4 — enforced in doc 09)**

Any of these appearing in XIOSYNC is a security regression to be reverted
immediately.
