# 11 — Acceptance Gates

> Normative. The **global definition of done**. Nothing is "complete" — no
> feature, no phase, no release — until the gates that apply to it pass with
> **attached, reproducible proof** (doc 01 §4.6). A green compile is not proof.

Each gate below is `ID | statement | how it's proven | finding(s) it closes`.
A gate is **closed** only when the exact command and its result are recorded.

---

## 1. How to use this document

- Every feature PR closes the **per-feature gates** (§2) for the surfaces it
  touches.
- Every phase (doc 10) closes its **phase exit gate**, which is a named subset of
  the gates here.
- A **public multi-tenant release** requires **every** gate in §3–§9 green in
  staging, reproducibly, with proof artifacts attached.
- **A finding from doc 02 is not closed until its gate here passes.** The
  traceability column ties each gate back to the audit.

---

## 2. Per-feature gates (apply to every change)

| ID | Statement | Proof |
|---|---|---|
| F-MODEL | Behavior derives from an explicit invariant in doc 03 | link to the invariant + unit test |
| F-TENANT | Every new tenant query filters by `organization_id` | code + passing cross-tenant negative test |
| F-AUTHZ | Every privileged path calls `authorize(...)` and emits a decision Event | unauthorized-attempt test fails closed |
| F-MIGRATE | Schema change is a migration; no runtime DDL | migration file + up/down/up clean |
| F-OBSERVE | State change emits an audit Event; failures are typed, never swallowed | log/event sample + failure test |
| F-FE | User-facing change declares route authority; handles loading/empty/error/success; axe-clean | test + axe output |
| F-PROOF | "Done" ships with the exact command run and its result | the recorded command + output |

**A change missing any applicable per-feature gate is not merge-eligible.**

---

## 3. Tenancy & isolation gates (C1, C2)

| ID | Statement | Proof | Closes |
|---|---|---|---|
| G-ISO-1 | Every request resolves a real `OrgContext` before any handler; no `"pending"` exists | middleware order test + grep for placeholder = none | C1 |
| G-ISO-2 | Every tenant-bearing table has non-null immutable `organization_id` | schema introspection test over all tables | C2 |
| G-ISO-3 | Cross-tenant read fails at the **repository** layer | negative test (org A cannot read org B) | C1/C2 |
| G-ISO-4 | Cross-tenant read fails at the **RLS** layer even with a raw query | negative test bypassing repo, still denied | C1/C2 |
| G-ISO-5 | No cross-org FK can be committed in any graph class | negative write tests per entity | isolation |

---

## 4. AuthN / AuthZ / session gates (C3, C8, H4, H8)

| ID | Statement | Proof | Closes |
|---|---|---|---|
| G-AUTH-1 | `authorize(...)` reads real grants; no hardcoded-identifier check exists | grep = none + allow/deny tests over real grants | C3 |
| G-AUTH-2 | No execution path runs a capability without a prior `allowed=true` | exhaustive entry-point test + arch check | C3 |
| G-AUTH-3 | Revoked session rejected before token expiry | revoke-then-request test | C8 |
| G-AUTH-4 | Password change / logout revokes all identity sessions | multi-session test | C8 |
| G-AUTH-5 | Refresh-token reuse revokes the session family + `critical` event | reuse-detection test | C8 |
| G-AUTH-6 | Signup cannot yield `platform_admin`/`org_owner` | escalation negative test | H4 |
| G-AUTH-7 | No auto-seeded privileged actor; first admin only via audited bootstrap | seed inspection + bootstrap audit event | H8 |
| G-AUTH-8 | Authority is three separate axes, never one role string | model test | H4 |

---

## 5. Persistence & schema gates (C5, C6, H2, H3, H6, M6)

| ID | Statement | Proof | Closes |
|---|---|---|---|
| G-DB-1 | No runtime `CREATE TABLE`/`ALTER`/`create_all`/probe in app code | grep + arch check = none | C5 |
| G-DB-2 | PostgreSQL only; no SQLite target anywhere (code, config, manifest) | grep across repo = none | C6 |
| G-DB-3 | Migration runs once as a deploy step; API never migrates; refuses to serve off-head | pipeline config + startup head-gate test | C6 |
| G-DB-4 | `upgrade → downgrade → upgrade` clean; autogenerate diff empty; single head | CI migration job output | C5/H2 |
| G-DB-5 | Tests run against the migrated schema; no fabricated tables | grep for `CREATE TABLE` in tests = none | H2 |
| G-DB-6 | Type values validated against the registry; no runtime constant-set authority | negative write + grep | H3 |
| G-DB-7 | `events` UPDATE/DELETE from app role fails; hash-chain verifiable | privilege test + chain verifier | H6 |
| G-DB-8 | Memory is versioned, never overwritten | version test | H6 |
| G-DB-9 | One vetted UUIDv7; no uuid4 fallback; crypto is a hard dep | grep + startup-without-crypto fails | M6 |

---

## 6. Execution / workers / plugins gates (C7, C9, C10, H7, H9)

| ID | Statement | Proof | Closes |
|---|---|---|---|
| G-EXE-1 | No execution-plane component writes the DB or publishes Events directly | arch check + integration test | arch |
| G-EXE-2 | Duplicate task completion is idempotent | duplicate-completion test | exec |
| G-EXE-3 | Task result re-validated + re-authorized before commit | tampered-result test rejected | C9/exec |
| G-DLQ-1 | DLQ items never auto-resolve; corrections pass the proposal gates | attempted auto-mutation blocked | C9 |
| G-DLQ-2 | Promotion creates a new workflow version; never edits a published spec | version test | C9 |
| G-WRK-1 | Worker creds are short-lived, per-worker, capability-scoped, distinct key | cred inspection + cannot-mint-user-token test | H7 |
| G-WRK-2 | Below-tier worker cannot execute a tier-gated grant | tier negative test | trust |
| G-WRK-3 | Untrusted worker cannot mutate global/cross-actor state | isolation test | C9 |
| G-PLG-1 | Plugin runs out-of-process; no DB/secret/non-allowlisted-host access | sandbox escape test | C10 |
| G-PLG-2 | Empty allowlist denies all; install requires approval | allowlist + approval test | C10 |
| G-PHN-1 | Isolation subsystem uses only canonical registered types (no `agent_*`) | contract tests over migrated schema | C7 |
| G-PHN-2 | Isolation subsystem creates no runtime tables; secrets via managed backend | grep + deployment review | H9 |
| G-PHN-3 | Isolation subsystem disabled in general multi-tenant prod (flag default-off) | flag config test | doc 01 §6 |

---

## 7. Frontend gates (M2, M3, H1, a11y)

| ID | Statement | Proof | Closes |
|---|---|---|---|
| G-FE-1 | No token in `localStorage`/`sessionStorage`/WS query string | grep + runtime test | M2 |
| G-FE-2 | Exactly one generated API client; no hand-written platform fetches | grep + build check | M3 |
| G-FE-3 | One canonical page per concept; no `agents`/`actors` twins, no `_v2` | route inventory | H1/M3 |
| G-FE-4 | Unauthorized route never renders and server rejects the request | guard test + server negative test | doc 08 §3 |
| G-FE-5 | Every async view handles loading/empty/error/success | component tests | doc 08 §5 |
| G-FE-6 | WCAG 2.1 AA; axe clean on all routes | axe CI output | doc 08 §7 |
| G-FE-7 | Web Vitals budgets met on key routes | measured vitals | doc 08 §8 |

---

## 8. Ops / CI / deploy gates (C4, M1, M4, M5, M7, L4, L5)

| ID | Statement | Proof | Closes |
|---|---|---|---|
| G-OPS-1 | CORS: explicit allowlist, no wildcard/regex; non-allowlisted origin rejected | CORS config test | C4 |
| G-OPS-2 | Rate limiting uses a shared store, correct across replicas | multi-replica limit test | M1 |
| G-OPS-3 | CI runs the full blocking gate set (not just compile/import) | CI config + run | M4 |
| G-OPS-4 | Missing precondition (secret, DB head, types, crypto) fails startup | startup failure tests | M5/L4 |
| G-OPS-5 | No broad `except Exception` masks a startup precondition | grep + startup tests | M5 |
| G-OPS-6 | Distinct `/live` and `/ready`; `/ready` checks head/deps/types | probe tests | M7 |
| G-OPS-7 | No embedded secret defaults anywhere | grep = none | L4 |
| G-OPS-8 | One lockfile/package manager per ecosystem | repo check | L5 |
| G-OPS-9 | Container smoke: build → migrate → `/ready` → minimal e2e workflow | CI smoke output | M4 |
| G-OPS-10 | Backups automated; restore rehearsed | DR drill record | doc 09 §9 |

---

## 9. The release gate (the one question, provable)

**G-RELEASE (doc 01 §2):**

> Can one organization safely execute a workflow without another organization, an
> untrusted worker, or a compromised plugin affecting it — **and is it proven by
> test?**

A public multi-tenant release is permitted **only** when:
- §3–§8 are entirely green in staging, reproducibly, with artifacts.
- The end-to-end scenario runs: org A publishes and runs a workflow, tasks are
  leased by an enrolled worker, results validated and authorized, Operations +
  Events recorded — while org B and a below-tier/untrusted worker and a sandboxed
  plugin **provably cannot** read, mutate, or influence org A's data or run.
- Every doc 02 finding maps to a green gate above (traceability complete).

**INV-ACCEPT-1:** If any applicable gate is red or unproven, the thing under
review is **not done** — regardless of how much works. Record the blocker
verbatim; never claim a green you did not see.
