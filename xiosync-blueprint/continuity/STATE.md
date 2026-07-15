# STATE — Current Ground-Truth Position of the XIOSYNC Rebuild

> **Authoritative for position.** Any agent booting into this project reads
> this file first (per root `AGENTS.md`). The last agent to work MUST have
> updated this file before stopping; if the "Last updated" session below does
> not match the newest entry in `HANDOFF-LOG.md`, treat the log as truth and
> repair this file first.

- **Last updated:** Session 022 — 2026-07-15
- **Repo (canonical, D-020):** `MDShahid94/XIOSYNC_V0` (GitHub; default
  branch `main`; managed via `GITHUB_FINE_GRAINED_PAT`). Remote names
  churn with workspace duplication — as of Session 018 there is NO usable
  named remote (`origin` is a v0 bundle URL); push with the full canonical
  URL inline. If a mirror repo is configured in your workspace, push every
  step to both, canonical last.
  Pushing needs the PAT, and in a fresh sandbox shell
  `GITHUB_FINE_GRAINED_PAT` is EMPTY until sourced (it lives in the
  gitignored `.env.development.local`) — an unsourced push fails with
  "could not read Username", not an auth error. Always:
  `set -a; source .env.development.local; set +a; git push
  "https://x-access-token:${GITHUB_FINE_GRAINED_PAT}@github.com/MDShahid94/XIOSYNC_V0.git"
  <branch>` (token inline per command; never store it in git config, and
  pipe push output through `sed "s#${GITHUB_FINE_GRAINED_PAT}#***#g"`).

---

## Where the rebuild stands

| Milestone | Status |
|-----------|--------|
| Blueprint authored (docs 00–12, DECISIONS, GLOSSARY) | ✅ Complete |
| Legacy XIOPATH placed in repo root as evidence | ✅ Complete (committed in Session 002) |
| Continuity plane (this system: AGENTS.md, STATE, HANDOFF-LOG, SESSION-PROTOCOL) | ✅ Complete (Session 002) |
| Phase R — Rebuild-readiness deep research (doc 10) | ✅ Complete (Session 003 — D-013..D-018) |
| **Phase 0 — Foundation & guardrails** | ✅ **Complete (Session 015).** Exit gate closed on canonical repo `MDShahid94/XIOSYNC_V0`: CI green on `main` — **run `29368647653`, SHA `a14e791`, event push, conclusion success** (jobs lint-type-arch / unit / migration-chain); branch protection on `main` requires all three (strict) per D-016; Gate 10 scanner = GitHub-native secret scanning + push protection, enabled (D-020). Prior PR-proof on the mirror: run `29367288883`, SHA `1f84669` |
| **Phase 1 — Identity, tenancy & authorization spine** | 🟡 In progress. **Slice 1 (five identity tables) ✅ Complete (Session 018):** PR #2 → `main` @ `87e0086`, CI `29373985898`. **Slice 2 (OrgContext C1 + org-scoped persistence boundary) ✅ Complete (Session 020):** `domain/context.py` frozen OrgContext + `persistence/tenancy.py` `org_scoped_session` (parameterized `set_config('app.current_org', ..., true)`, SET LOCAL scope) + revision 0003 hardening the 0002 RLS policies to fail closed on the empty-string GUC (`NULLIF(...,'')::uuid`). PR #4 squash-merged into `main` @ `deda247`; GitHub CI green (lint-type-arch / unit / migration-chain). Remaining slices: HTTP middleware wiring for OrgContext, session lifecycle (C8), authority axes (H4/H8), `authorize(...)` (C3) |
| Phases 2–7 | 🔲 Blocked (sequential, gated) |

**No XIOSYNC implementation code exists yet.** The `app/` directory is the v0
sandbox scaffold, not XIOSYNC; per D-015 it is deleted when Phase 0 begins.

## The exact next action

Continue **Phase 1 — Identity, tenancy & the authorization spine**. The
session-lifecycle slice is IN FLIGHT on local branch
`phase1/sessions-middleware` (session 021–022 work, **unpushed**): done so
far — sentinel threshold 1.50 (`6deaccc`, D-022), `platform/tokens.py`
PyJWT HS256 access tokens + `XIOSYNC_AUTH_SECRET` config (`a656f10`,
D-023), sentinel time-decay (`440892d`, D-024). Local `main` @ `4ab62f9`
is 1 docs commit ahead of canonical `deda247`; the eventual PR carries
both. Remaining steps (CHECKPOINT plan, session 022 numbering):

1. Boot per SESSION-PROTOCOL §1 (sentinel set/guard — note decay, D-024;
   if freshly duplicated workspace, §7 drill first — verify `git ls-files
   xiosync/` shows namespace symlinks and `uv run python -c "import
   xiosync.platform.clock"` works; `git remote -v` — a v0 bundle `origin`
   is unusable, push with the canonical URL inline per the Repo header).
   Integration tests need local Postgres: postgresql16-server, `initdb -U
   postgres --auth=trust -E UTF8 --locale=C.UTF-8` (MUST be UTF8),
   `pg_ctl start`, create db `xiosync`, append
   `DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/xiosync` to
   `.env.development.local` (own line, leading newline).
2. Step 6: `persistence/identity.py` repo + `services/identity.py`
   SessionService — login, refresh rotation + reuse-revoke
   (INV-SESSION-3), logout, revoke-all (INV-SESSION-2),
   validate→OrgContext via session-row lookup (INV-SESSION-1) — against
   the 0002 `sessions` table; unit + integration tests; commit.
3. Step 7: `api/app.py` + `api/middleware.py` (request_id →
   security_headers → body_size → authenticate) + auth router
   (login/refresh/logout) + contract tests; commit. Middleware derives
   `OrgContext` (`domain/context.py`) and enters `org_scoped_session(...)`
   (`persistence/tenancy.py`). Docs: 05 §2/§4, 04 §2/§6.
4. Step 8: full gate (ruff, format, mypy --strict, import-linter, pytest
   all), push branch with the inline-token URL, PR, squash-merge on green
   CI (D-016/D-017); never force-push canonical `main`.
5. Then: authority axes (H4/H8) and the single `authorize(...)` decision
   point (C3). Exit gate = the security-negative suite (doc 05 §8, doc 11).
6. Before writing app-facing code, resolve D-015's note that the v0
   sandbox `app/` scaffold is deleted when implementation begins — check
   D-015's exact wording and comply.

No structural questions remain open — do not improvise a stack or layout
choice; everything is in D-013..D-020.

**Governing docs for the next task:** 10 (Phase 1), 03 (ontology), 05
(security/identity/tenancy), 06 (persistence schema), 04 §2/§6 (layering),
DECISIONS.md D-013..D-020.

## Standing constraints (never stale)

- Prime directives: `xiosync-blueprint/README.md` §"The prime directives".
- Roadmap ordering is mandatory: R → 0 → 1 → … → 7, each behind its exit gate.
- `XIOPATH/` is read-only evidence. Verify against it; never port from it.

## How to update this file (on every handoff)

1. Update "Last updated" with your session number and date.
2. Update the milestone table — only mark ✅ when the proof exists and is
   referenced in your HANDOFF-LOG entry.
3. Rewrite "The exact next action" so a cold-booted agent can proceed with
   zero further context.
4. Append your session entry to `HANDOFF-LOG.md` (see SESSION-PROTOCOL.md).
