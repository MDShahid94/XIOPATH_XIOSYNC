# DECISIONS — Architectural Decision Log

> **Append-only.** Never edit or delete an accepted entry; supersede it with a new
> one that references the old ID. Every durable choice made during the XIOSYNC
> rebuild is recorded here with its alternatives and the reason they lost.
>
> **Entry format:**
> `ID | Status | Decision | Context (finding refs) | Alternatives rejected | Consequences`
>
> Statuses: **Accepted** · **Superseded by D-nnn** · **Deferred**

---

## D-001 — Rebuild from scratch; zero legacy compatibility

- **Status:** Accepted
- **Decision:** XIOSYNC is a clean rebuild. No XIOPATH code, schema, or data
  format is imported. Concepts are re-derived from the formal spec (doc 03), not
  ported.
- **Context:** Doc 02 found 10 critical, 9 high findings; several are structural
  (split schema authority, unenforced authorization, placeholder tenancy) and
  cannot be patched without rewriting the affected planes anyway.
- **Alternatives rejected:** incremental remediation of XIOPATH (each critical fix
  invalidates neighboring code; audit showed drift was systemic); strangler-fig
  migration (no production data worth preserving justifies the dual-run cost).
- **Consequences:** no migration tooling from XIOPATH is built; the forbidden-
  vocabulary rule (GLOSSARY) is enforceable because nothing legacy must keep working.

## D-002 — Single formal ontology; auth identity and ontology actor unified by link, not by merger

- **Status:** Accepted
- **Decision:** `AuthIdentity` (who authenticates) and `Actor` (who acts within an
  org) are distinct entities joined by an explicit link; one AuthIdentity may map
  to at most one Actor per organization.
- **Context:** H1, H4, H8. XIOPATH had two vocabularies behind aliases and a
  seeded ontology superuser.
- **Alternatives rejected:** one merged "user" table (conflates global identity
  with per-org authority, makes multi-org membership a hack); keeping aliases for
  familiarity (aliases are how H1 happened).
- **Consequences:** every request resolves the chain token → session →
  AuthIdentity → Actor(org) → grants. Bootstrap creates the first admin through
  this chain only (doc 05 §6).

## D-003 — Postgres-only, migrations as sole schema authority

- **Status:** Accepted
- **Decision:** PostgreSQL is the only supported engine in every environment
  including tests. Migrations (one linear chain) are the only code allowed to
  emit DDL, run as a deploy step with a lock — never at app startup.
- **Context:** C5, C6, H2. XIOPATH split authority between Alembic and a runtime
  `_init_db()`, ran migrations per replica, and hardcoded SQLite paths.
- **Alternatives rejected:** SQLite for dev/tests (dialect drift caused H2-class
  fabrication); runtime `create_all` for convenience (that convenience *was* C5).
- **Consequences:** replicas fail fast when the schema version is behind; CI runs
  the full migration chain against real Postgres (doc 09 §7).

## D-004 — One authorization decision point, enforced at execution

- **Status:** Accepted
- **Decision:** a single decision function answers every "may Actor A perform
  Operation O on resource R in Org G" question. Authority is read from grants at
  decision time — never cached in tokens.
- **Context:** C3 (grants stored, never enforced), C8 (no revocation).
- **Alternatives rejected:** JWT-embedded permissions (fast, but revocation
  becomes eventual, which is C8 again); per-router permission decorators with
  local logic (guarantees divergence).
- **Consequences:** opaque server-side sessions are required (D-005); every
  mutating handler is auditable by grepping for the one function.

## D-005 — Opaque server-side sessions in HttpOnly cookies

- **Status:** Accepted
- **Decision:** credentials are opaque session IDs stored server-side, delivered
  in HttpOnly, Secure, SameSite cookies. No JWTs for interactive sessions, no
  browser-storage tokens, no tokens in WS URLs (WS auths via cookie or one-time ticket).
- **Context:** C8, M2.
- **Alternatives rejected:** JWT + refresh rotation (still leaves a revocation
  window and pushes complexity into every client); localStorage tokens (XSS = full
  compromise, and URLs/logs leak WS query tokens).
- **Consequences:** the API keeps session state (backed by the primary database in
  v1); logout, revocation, and password-change invalidation are immediate.

## D-006 — Tenancy scoped in the persistence layer, derived only from the session

- **Status:** Accepted
- **Decision:** every tenant-owned table carries `organization_id NOT NULL`; every
  repository method requires the org ID as a parameter, populated from the
  authenticated session context. Cross-tenant access returns 404.
- **Context:** C1 (placeholder "pending" tenant stamped pre-auth), C2 (no org
  column on ontology rows).
- **Alternatives rejected:** header-derived tenant (spoofable — that's C1);
  database-per-tenant (operationally heavy for v1; revisit if isolation
  requirements harden — see Deferred D-101).
- **Consequences:** repository signatures are noisier by design; the cross-tenant
  test suite (doc 11 §3) is a permanent CI gate.

## D-007 — Per-worker enrollment with short-lived scoped credentials

- **Status:** Accepted
- **Decision:** each worker enrolls individually (doc 03 §4.5) and receives
  short-lived credentials scoped to itself; task secrets are minted per task and
  expire with it. The signing/root secret never leaves the control plane.
- **Context:** H7 (shared long-lived JWT secret as worker credential), H9 (file-
  based secret store).
- **Alternatives rejected:** shared worker token (one leaked worker = whole fleet);
  mTLS-only identity for v1 (right long-term, but certificate lifecycle is heavy;
  deferred — D-102).

## D-008 — Plugins execute only in an external sandbox; DLQ corrections are proposals

- **Status:** Accepted
- **Decision:** plugin code never runs in a control-plane process (out-of-process
  sandbox with resource/fs/network limits — doc 07 §5). Failure-analysis ("self-
  learning") output is written as proposals that a distinct granted authority must
  approve before any state changes.
- **Context:** C10 (`import_module` in-process plugins), C9 (autonomous DLQ mutation).
- **Alternatives rejected:** in-process plugins with code review as the control
  (review is not a sandbox); fully autonomous correction with audit-after
  (mutation-then-audit is how silent corruption compounds).
- **Consequences:** plugin API surface must be serializable across the sandbox
  boundary; a proposal/approval table pair exists in the schema (doc 06 §5).

## D-009 — Events append-only at the database privilege level; memory versioned

- **Status:** Accepted
- **Decision:** the application database role has no UPDATE/DELETE privilege on
  event tables; memory entries are immutable versions with a derived "current"
  pointer.
- **Context:** H6 ("append-only" was a naming convention, not a property).
- **Alternatives rejected:** code-discipline-only append-only (indistinguishable
  from H6); event-sourcing everything (v1 needs audit trails, not a full ES
  architecture — see doc 01 §6 non-goals).

## D-010 — Isolation-tier execution (Phantom successor) ships behind contract tests or not at all

- **Status:** Accepted
- **Decision:** the Phantom-successor subsystem (doc 07 §6) is rebuilt with
  explicit entity contracts; no chain registers without a passing integration
  test against real entity shapes. It is feature-flagged default-off until
  Phase 4 gates pass.
- **Context:** C7 (bridge referenced nonexistent fields — proof the path never ran).
- **Alternatives rejected:** dropping the subsystem entirely (its capability is a
  core product objective, doc 01 §2); porting XIOPATH chains as-is (they encode
  the broken field contract).

## D-011 — Frontend: TypeScript, single transport module, four-state async contract

- **Status:** Accepted
- **Decision:** the frontend is TypeScript with one API transport module and one
  WS manager; every async surface renders loading/empty/error/success
  distinctly (doc 08).
- **Context:** M2, M3 (duplicated JS API clients, token handling in components).
- **Alternatives rejected:** porting the JSX codebase (carries M2/M3 forward);
  multiple per-feature clients (that's M3 by construction).

## D-012 — CI gates must be falsifiable behavior tests

- **Status:** Accepted
- **Decision:** every acceptance gate in doc 11 maps to a named CI job that
  exercises real behavior (real Postgres, real HTTP), and each job must be
  demonstrably able to fail (mutation-checked per doc 12 §2.15).
- **Context:** M4 (CI proved imports, not behavior).
- **Alternatives rejected:** coverage thresholds as the quality bar (coverage
  measures execution, not assertion strength).

---

## D-013 — Backend stack pinned (Phase R)

- **Status:** Accepted (Session 003, 2026-07-14)
- **Decision:** The control plane is built on:
  - **Python 3.13.x** (3.13.11 verified in the build environment; requires-python `>=3.13,<3.14`).
  - **uv** (0.9.22 verified) as the sole Python package manager; one `uv.lock` at repo root (INV-CFG-3 / L5). Exact library versions are pinned in the lockfile at Phase 0 init; majors are fixed here.
  - **FastAPI** (doc 04 §5 commitment) on **uvicorn**, with the §2.1 layering enforced by tooling (below).
  - **SQLAlchemy 2.0.x** + **Alembic 1.x** (single linear chain, deploy-step only — D-003) + **psycopg 3.x** as the only DB driver. No other engine or driver is ever installed (C6).
  - **pytest 8.x** + **pytest-asyncio** for all test tiers; integration/security tiers read `DATABASE_URL` and require a migrated real Postgres (H2, doc 06 §10).
  - **ruff** (lint + format) and **mypy --strict** as the type/lint gates (doc 09 §7.1).
  - **import-linter** as the architecture-rule checker: declared contracts enforce RULE-ARCH-1/2/3 layering (`domain` imports nothing upward; `api` never imports `persistence`); a CI grep gate enforces the GLOSSARY forbidden-terms table.
  - **uuid-utils** for UUIDv7 in `platform/ids` (M6 — Python 3.13 stdlib has no `uuid7`; it lands in 3.14. One vetted library, no fallback).
  - **cryptography** as a hard dependency (startup fails if absent — M6) and **argon2-cffi** for password hashing (doc 05).
  - **PostgreSQL 17** pinned as the engine major in every environment including CI.
- **Context:** Phase R "stack pinning" mandate (doc 10); doc 04 §5 technology commitments; verified environment: Python 3.13.11, uv 0.9.22 present; Docker and psql absent from the sandbox (see D-016).
- **Alternatives rejected:** Poetry/pip-tools (uv is present, faster, one tool for venv+lock+run); pyright instead of mypy (either passes doc 09 §7.1 "strict"; mypy chosen for import-linter/pytest plugin ecosystem maturity); `uuid6` pure-python lib (uuid-utils is maintained and faster; either acceptable — do not install both).
- **Consequences:** Phase 0 `pyproject.toml` declares these and CI fails on any second lockfile or package manager. Version bumps are ordinary commits; changing a major here requires a superseding decision.

## D-014 — Frontend stack pinned (Phase R)

- **Status:** Accepted (Session 003, 2026-07-14)
- **Decision:** `frontend/` is a **Vite 7 + React 19 + TypeScript 5 (strict)** single-page app, managed by **pnpm 10** (sole JS package manager, one `pnpm-lock.yaml` — L5), on **Node 24.x**. Server state via **TanStack Query** (doc 08 §4 names it), keyed by resource + `organization_id`. The single API client (M3, INV-FE rules) is **generated from the committed OpenAPI 3.1 contract** via `openapi-typescript` + `openapi-fetch`, regenerated and diffed in CI (doc 09 §7.6).
- **Context:** doc 08 §1 mandates React + TS strict + one generated client; environment has Node 24.14.1 and pnpm 10.34.3.
- **Alternatives rejected:** Next.js for the product frontend (the control plane is FastAPI; a Node server layer would create a second auth/session surface and duplicate the transport rules of doc 08 §2 — the SPA + cookie model keeps exactly one backend); hand-rolled fetch hooks (that is M3 by construction).
- **Consequences:** the v0 sandbox preview shows nothing for XIOSYNC until Phase 6 scaffolds `frontend/`; that is accepted (see D-015). Dev preview then runs the Vite dev server.

## D-015 — Repository instantiation of doc 04 §6 onto this repo (Phase R)

- **Status:** Accepted (Session 003, 2026-07-14)
- **Decision:** **This repository's root becomes the `xiosync/` root** of doc 04 §6. Concrete mapping, no placeholders:

  | Path (repo root) | Created in | Content |
  |---|---|---|
  | `api/` | Phase 0 (skeleton) | transport layer: routers, middleware, ws |
  | `services/` | Phase 0 (skeleton) | use-case layer |
  | `domain/` | Phase 0 (skeleton) | pure model + invariants (no I/O, no framework imports) |
  | `persistence/` | Phase 0 | repositories + `persistence/migrations/` (Alembic home) |
  | `platform/` | Phase 0 | config loader, ids (uuid-utils), crypto, clock, telemetry |
  | `workers/` | Phase 4 | execution-plane worker runtime (separate uv workspace member) |
  | `plugins-sdk/` | Phase 5 | plugin contract + out-of-process host |
  | `frontend/` | Phase 6 | Vite/React SPA (D-014) |
  | `deploy/` | Phase 0 | Dockerfiles, compose/k8s, migration job |
  | `scripts/` | as needed | only CI-exercised scripts (doc 04 §6 rule) |
  | `tests/` | Phase 0 | `unit/ integration/ security/ contract/` |
  | `xiosync-blueprint/` | exists | normative docs + continuity plane |
  | `XIOPATH/` | exists | read-only legacy evidence (never imported) |

  Python topology: one uv workspace at root; `api/ services/ domain/ persistence/ platform/` are packages of a single `xiosync` distribution; `workers/` and `plugins-sdk/` are separate workspace members (they must be installable without control-plane code — RULE-ARCH-6). JS topology: pnpm workspace containing only `frontend/`.

  **The v0 sandbox Next.js scaffold (`app/`, `components/`, `lib/`, `hooks/`, `next.config.mjs`, `components.json`, current root `package.json`/`pnpm-lock.yaml`, `.next/`) is deleted at Phase 0 start.** It is not XIOSYNC (STATE.md already states this), violates clean-root L2, and its lockfile would collide with the frontend workspace (L5).
- **Context:** Phase R "repo instantiation plan" mandate; doc 04 §6; L2/L5.
- **Alternatives rejected:** nesting everything under an `xiosync/` subdirectory (adds a path layer with no isolation benefit; blueprint's own layout shows `xiosync-blueprint/` as a sibling of the code, which this repo already satisfies at root); keeping the sandbox scaffold "for preview" (a preview of a page that is not the product is not evidence of anything — doc 01 §4.6 spirit).
- **Consequences:** between Phase 0 and Phase 6 the repo has no runnable web UI; verification is tests + CI, which is exactly the doc 09 quality bar.

## D-016 — CI substrate and Postgres provisioning (Phase R)

- **Status:** Accepted (Session 003, 2026-07-14)
- **Decision:** **GitHub Actions** runs all doc 09 §7 blocking gates. The empty-Postgres migration harness (gate 2) and integration/security gates (4, 5, 8) use **GitHub Actions service containers (`postgres:17`)** — a fresh, empty database per job. Tests connect only via `DATABASE_URL`; no engine/path assumptions in code (C6). For interactive development **inside this v0 sandbox** (verified: no Docker, no psql, git remote is a v0 bundle), the developer database is a **Neon Postgres** (v0's connected-integration Postgres), same major (17), also consumed only via `DATABASE_URL`.
- **Preconditions recorded:** the repo is not yet connected to GitHub (remote is a local bundle). **Connecting this repo to GitHub is a Phase 0 entry prerequisite** — without it, gates cannot be blocking and Phase 0's exit gate ("all CI gates run and are blocking") is unreachable.
- **Context:** Phase R "CI substrate" mandate; doc 09 §7; environment probes this session (`docker: command not found`, `psql: command not found`, `git remote -v` → bundle); XIOPATH precedent of `.github/workflows/ci.yml` shows the ecosystem fit.
- **Alternatives rejected:** running the harness in the sandbox (no container runtime; installing a local Postgres per session is unreproducible and dies with the sandbox); SQLite for local tests (explicitly banned — D-003/C6).
- **Consequences:** local sandbox work can run lint/type/unit gates offline; DB-touching gates need the Neon `DATABASE_URL` or a pushed branch. CI is the arbiter of migration-gate greens.

## D-017 — Gate-proof recording format (Phase R, continuity integration)

- **Status:** Accepted (Session 003, 2026-07-14)
- **Decision:** every phase exit-gate claim MUST be recorded in the session's HANDOFF-LOG entry as: (a) the exact command (or CI job name) run, (b) the observed result verbatim or the CI run URL/ID, and (c) the git commit SHA the proof applies to. Once GitHub Actions is live, a green named CI run ID is the canonical proof for CI-gated claims; a local command transcript is acceptable only for gates that have no CI job yet. Blocked checks are recorded verbatim as blocked (prime directive 7). STATE.md milestone flips to ✅ only when its HANDOFF-LOG entry contains such a proof.
- **Context:** Phase R "continuity integration" mandate; SESSION-PROTOCOL §2; INV-ROADMAP-2.
- **Alternatives rejected:** a separate `continuity/gates/` artifact directory (duplicates the ledger; two places to go stale).
- **Consequences:** none beyond discipline; this makes the existing HANDOFF-LOG verification field sufficient and mandatory.

## D-018 — Deferred decisions D-101/D-102/D-103 re-deferred with reopening conditions (Phase R)

- **Status:** Accepted (Session 003, 2026-07-14)
- **Decision:** all three deferred items remain deferred; none blocks Phase 0–7:
  - **D-101 (database-per-tenant):** re-deferred 2026-07-14. Reopens if a customer/regulatory requirement demands physical isolation, or if the cross-tenant security-negative suite (doc 11 §3) ever passes only via RLS with a repo-layer miss (i.e., defense-in-depth degraded to single-layer).
  - **D-102 (mTLS worker identity):** re-deferred 2026-07-14. Reopens when the enrolled worker fleet exceeds ~50 nodes, workers run on networks the platform does not control beyond the volunteer tier's isolated task classes, or credential-rotation incident volume makes certificate lifecycle cheaper than token ops.
  - **D-103 (multi-region/DR beyond backup-restore):** re-deferred 2026-07-14. Reopens when a production SLO requires RTO/RPO below what the rehearsed restore drill (INV-DR-1) demonstrably achieves, or at the first contractual availability commitment to a paying tenant.
- **Context:** Phase R requires each deferred decision closed or explicitly re-deferred with a dated rationale and reopening condition (doc 10 Phase R). Note: STATE.md (Session 002) referred to these as "D-D1..D-D3"; the canonical IDs are D-101..D-103 — corrected in STATE.md this session.
- **Consequences:** Phase 0 may begin with zero open structural questions.

## D-019 — import-linter external-package checking enabled (Phase 0)

- **Status:** Accepted (Session 008, 2026-07-15)
- **Decision:** `[tool.importlinter]` sets `include_external_packages = true`.
  This is required for the "domain is framework-free" forbidden contract
  (RULE-ARCH-1) to check external modules (`fastapi`, `sqlalchemy`, `psycopg`,
  …); without it `lint-imports` fails closed with a configuration error and
  the architecture gate cannot evaluate any contract.
- **Context:** discovered during Phase 0 step 4 (full-gate run): the original
  pyproject.toml declared external forbidden modules but omitted the flag, so
  `uv run lint-imports` errored before evaluating contracts ("The top level
  configuration must have include_external_packages=True when there are
  external forbidden modules.").
- **Alternatives rejected:** dropping external modules from the forbidden
  contract (would leave RULE-ARCH-1 "domain is framework-free" unenforced —
  exactly the class of silent gate decay M4 warns about).
- **Consequences:** all four architecture contracts evaluate (proof:
  `uv run lint-imports` → "Contracts: 4 kept, 0 broken."). The blocking
  lint-imports CI gate (doc 09 §7) is meaningful rather than vacuously broken.

## D-020 — Canonical remote is MDShahid94/XIOSYNC_V0; GitHub-native secret scanning is the Gate 10 scanner

- **Status:** Accepted
- **Decision:** The operator's public repo `MDShahid94/XIOSYNC_V0` (default
  branch `main`) is the canonical remote for the rebuild, managed directly via
  the operator-supplied fine-grained PAT (env `GITHUB_FINE_GRAINED_PAT`) until
  the rebuild + production workspace is complete. The v0-chat-connected repo
  (`chainaanantapurasha-rgb/XIO_SYNC_V0`, remote `origin`) is a working mirror
  that changes whenever the operator credit-cycles v0 accounts; every session
  pushes to both, canonical last. The Gate 10 secret scanner (doc 09 §7) is
  GitHub-native secret scanning **with push protection**, enabled on the
  canonical repo.
- **Context:** Session 015. Operator credit-cycling breaks the v0 git
  connection each cycle (Session 013→014 lost history and gitignore rules);
  a stable canonical remote decouples the project's git truth from v0 account
  churn. Old canonical main (Session 012 state, `cf6aa86`) is preserved at
  branch `archive/pre-rebuild-session-012`.
- **Alternatives rejected:** treating each v0-connected repo as canonical
  (identity churns every credit cycle; PR #1's repo will go stale); gitleaks/
  trufflehog in CI as the Gate 10 scanner (viable, but GitHub-native scanning
  is zero-maintenance on a public repo, includes push protection, and adds no
  CI latency — revisit only if the repo goes private without GHAS).
- **Consequences:** branch protection on canonical `main` requires the three
  Phase 0 jobs (lint-type-arch, unit, migration-chain) with strict
  up-to-date-ness; direct pushes that leak credentials are blocked at push
  time; sessions must not force-push canonical `main` again now that
  protection is on (the one-time history replacement predates protection).

## D-021 — Budget sentinel fails loud: `set` returns the decision; `handoff` always prints the checklist

- **Status:** Accepted
- **Decision:** `tools/budget_sentinel.py set <amount>` now evaluates the
  recorded amount against the threshold immediately: below threshold it prints
  `decision=handoff-required` plus the full handoff sequence and exits `20`;
  otherwise it prints `decision=continue` and exits `0`. `handoff` prints the
  graceful-stop checklist unconditionally — including when the snapshot is
  missing, malformed, or stale (exit `21`,
  `decision=snapshot-unavailable-fail-closed`).
- **Rationale:** The operator's stop commands were silently ineffective. `set 0`
  exited `0` printing only `recorded=true`, giving agents no signal that a
  handoff was mandatory; and after every credit-cycle workspace duplication
  (SESSION-PROTOCOL §7.1 — the snapshot is gitignored and does not survive),
  `handoff` printed only an error and *no checklist* — the exact moment the
  checklist is most needed. Both violated the fail-loud intent of §4.
- **Alternatives rejected:** keeping `set` decision-free and relying on agents
  to always chain `guard` (proven unreliable in practice); printing the
  checklist only on healthy snapshots (defeats the command's purpose).
- **Consequences:** SESSION-PROTOCOL §4.2 items 1 and 3 updated; the prior
  "`set` does not return a budget decision" contract and its test are replaced;
  `set 0` alone is now a complete, machine-checkable stop order.

---

## D-022 — Budget sentinel default threshold raised to USD 1.50

- **Status:** Accepted
- **Decision:** `DEFAULT_THRESHOLD` in `tools/budget_sentinel.py` is raised
  from USD 0.50 to USD 1.50. Contract tests and SESSION-PROTOCOL §4.2 item 3
  updated to match. Per-invocation `--threshold` overrides remain available.
- **Rationale:** Operator directive in the Session 021 resume prompt
  ("MODIFY threshold_usd FROM 0.50 TO 1.50"). USD 0.50 left too little
  headroom to execute the full graceful handoff (§3: log entry, STATE.md
  rewrite, commits, CHECKPOINT IDLE) before credits ran out; USD 1.50
  triggers the handoff while enough budget remains to complete it.
- **Alternatives rejected:** leaving the default and requiring the operator
  to pass `--threshold 1.50` on every invocation (error-prone, and the
  protocol quotes the default as the norm).
- **Consequences:** `set`/`guard`/`status` now exit `20` for any snapshot
  below USD 1.50; operators reporting balances in the 0.50–1.49 range will
  trigger a handoff that previously would have continued.

---

## D-023 — Access tokens are PyJWT HS256 *session pointers*; `XIOSYNC_AUTH_SECRET` required (Phase 1)

- **Status:** Accepted (Session 021)
- **Decision:** The session slice implements doc 05 §2.2 exactly: server-side
  `sessions` rows (already in the merged schema: `refresh_token_hash`,
  `access_token_jti` — revision 0002) plus short-lived HS256 access tokens
  signed/verified with **PyJWT** (`pyjwt>=2.9,<3`) in `platform/tokens.py`.
  Hard 15-minute TTL cap; required claims `jti/sid/org/act/iat/exp`; expiry
  checked against the injected clock so tests control time. The signing
  secret is the new **required** config key `XIOSYNC_AUTH_SECRET` (min 32
  chars, no default — L4).
- **Relationship to D-005:** not a contradiction — a refinement. D-005's
  rationale (C8: JWTs make revocation eventual) is neutralized because
  INV-SESSION-1 validates every access token against its `active` session
  row on every request: the JWT carries no authority, only a signed pointer
  at a revocable session. D-005's transport rule stands: browser delivery is
  HttpOnly/Secure/SameSite cookies; tokens never touch browser storage (M2).
  D-004 also stands: grants are read at decision time, never from tokens.
- **Context:** doc 05 §2.2 (token & session lifecycle); merged revision 0002
  already shipped the hybrid schema; doc 05 §2.3 permits cookie transport.
- **Alternatives rejected:** pure opaque cookie session ID with no access
  token (contradicts the merged 0002 schema and doc 05 §2.2's refresh
  rotation/theft detection — INV-SESSION-3); python-jose (heavier, historic
  CVEs); hand-rolled stdlib HS256 (reinvents a spec to save one dep); EdDSA
  now (key-management burden, no v1 consumer).
- **Consequences:** every environment must set `XIOSYNC_AUTH_SECRET`; config
  loading fails fast without it. Secret rotation invalidates all access
  tokens at once (sessions survive; refresh re-issues). A per-request
  session lookup is accepted; the doc 05 §2.2 short-TTL cache (≤30s) may be
  added later without changing this contract.

---

## D-024 — Budget sentinel decays the effective balance over time (auto-calibrated burn rate)

- **Status:** Accepted (Session 022)
- **Decision:** `tools/budget_sentinel.py` no longer treats an operator `set`
  as valid-until-stale. Every decision command (`guard`/`status`/`handoff`)
  evaluates a **decayed effective balance**: `effective = stored_amount −
  burn_rate × hours_elapsed` (floored at 0). The burn rate (USD/hour) is
  auto-calibrated from consecutive `set` calls (observed spend ÷ elapsed
  time, ignoring re-sets under 60 s and top-ups) and stored in the snapshot;
  `--burn-rate` overrides it per invocation (persisted on `set`, ephemeral
  on read commands; `--burn-rate 0` disables decay). Default until first
  calibration: 1.00 USD/hour.
- **Context:** Operator directive (Session 022): a single `set` made `guard`
  answer "continue" for the full 6-hour staleness window even though credits
  were being consumed the whole time, so the handoff boundary only moved
  when the operator remembered to re-`set`. That defeated the sentinel's
  purpose during long sessions.
- **Alternatives rejected:** shrinking `--max-age-hours` (binary stale/fresh
  cliff, still no moving boundary within the window); counting agent tool
  calls or steps as a spend proxy (unmeasurable from a stateless CLI, and
  the snapshot must stay meaningful across process restarts); querying v0
  billing (no authoritative API is available to the sandbox — the sentinel
  is explicitly not a billing client).
- **Consequences:** the effective balance shown by `status` is an estimate,
  intentionally conservative; a session that outlives its projected budget
  hands off early rather than late (fail-closed bias preserved). Snapshots
  written by older versions (no `burn_rate_usd_per_hour` field) still read,
  decaying at the default rate. SESSION-PROTOCOL §4.2 updated accordingly.

---

## D-025 — Continuity and Budget tracking offloaded to Agentic Orchestrator

- **Status:** Accepted (Session 023)
- **Decision:** All state tracking (`STATE.md`, `CHECKPOINT.md`, `HANDOFF-LOG.md`), crash recovery logic, and budget sentinel scripts (`tools/budget_sentinel.py`) have been entirely removed from this repository. Continuity is now fully offloaded to an external Agentic Orchestrator (the `v0-agentic-pipeline`).
- **Rationale:** The V0 agent environment is stateless and volatile (credits exhaust unpredictably). Forcing the V0 agent to manage its own checkpointing consumed valuable context and often resulted in uncommitted state if a session died mid-generation. The external orchestrator runs deterministically outside the V0 sandbox, safely committing partial states and generating precise "next action" prompts.
- **Alternatives rejected:** Keeping continuity in-repo and relying on prompt discipline (proven fragile against hard 402 API failures).
- **Consequences:** `AGENTS.md` and `SESSION-PROTOCOL.md` are deprecated/removed. V0 agents booting into this repo should only focus on code implementation dictated by the orchestrator prompt.

---

## D-026 — Continuity files restored to repo as portable fallback; XIOV0 is primary orchestrator

- **Status:** Accepted (Session 030, 2026-07-20)
- **Decision:** The `continuity/` directory (`STATE.md`, `HANDOFF-LOG.md`,
  `SESSION-PROTOCOL.md`) is restored to git tracking and removed from
  `.gitignore`. The XIOV0 external orchestrator remains the primary continuity
  manager (D-025 stands), but these files serve as a **portable fallback**:
  any agent cloning the repo can bootstrap from `STATE.md` alone without the
  orchestrator. V0 workspace injection explicitly excludes `continuity/` to
  prevent agent context conflicts.
- **Context:** D-025 removed continuity from the repo entirely, but this
  created a single point of failure — if the orchestrator was unavailable or
  the project was cloned without XIOV0, no agent could determine the current
  position. The XIOPATH legacy codebase (3.4MB) is now also included in V0
  workspace injection as essential rebuild context.
- **Alternatives rejected:** keeping continuity gitignored and relying
  entirely on the orchestrator's database (fragile — DB is per-user and not
  portable); embedding state in commit messages only (not machine-parseable).
- **Consequences:** `continuity/STATE.md` must stay consistent with the
  project's actual position. The orchestrator auto-maintains these files
  after each V0 session completes. Manual edits are acceptable as a fallback.

---

## Deferred decisions

## D-101 — Database-per-tenant isolation

- **Status:** Deferred
- **Context:** D-006 chose row-level scoping for v1. Revisit if a customer
  requires physical isolation or regulatory separation.

## D-102 — mTLS worker identity

- **Status:** Deferred
- **Context:** D-007 chose short-lived scoped credentials for v1. Revisit when
  worker fleet size or network topology justifies certificate lifecycle tooling.

## D-103 — Multi-region / DR beyond backup-restore

- **Status:** Deferred
- **Context:** doc 09 §9 specifies backup + tested restore for v1. Active-active
  is out of scope (doc 01 §6).

---

*Add new entries above the Deferred section, IDs sequential. Never renumber.*
