# STATE — Current Ground-Truth Position of the XIOSYNC Rebuild

> **Authoritative for position.** Any agent booting into this project reads
> this file first (per root `AGENTS.md`). The last agent to work MUST have
> updated this file before stopping; if the "Last updated" session below does
> not match the newest entry in `HANDOFF-LOG.md`, treat the log as truth and
> repair this file first.

- **Last updated:** Session 018 — 2026-07-15
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
| **Phase 1 — Identity, tenancy & authorization spine** | 🟡 In progress. **Slice 1 (five identity tables) ✅ Complete (Session 018):** ORM models + Alembic revision 0002 (RLS per doc 05 §3.2 + IMM triggers per doc 06 §4) + drift/RLS/immutability integration tests. PR #2 squash-merged into `main` @ `87e0086`; GitHub CI run `29373985898` success (lint-type-arch / unit / migration-chain, postgres:17). Remaining slices: OrgContext (C1), sessions (C8), authority axes (H4/H8), `authorize(...)` (C3) |
| Phases 2–7 | 🔲 Blocked (sequential, gated) |

**No XIOSYNC implementation code exists yet.** The `app/` directory is the v0
sandbox scaffold, not XIOSYNC; per D-015 it is deleted when Phase 0 begins.

## The exact next action

Continue **Phase 1 — Identity, tenancy & the authorization spine** (doc 10
Phase 1; docs 03, 05, 06). Slice 1 (identity tables) is merged — do not
revisit it.

1. Boot per SESSION-PROTOCOL §1 (sentinel set/guard; if freshly duplicated
   workspace, §7 drill first — verify `git ls-files xiosync/` shows the
   namespace symlinks and `uv run python -c "import
   xiosync.platform.clock"` works; check `git remote -v` — a v0 bundle
   `origin` is unusable, push with the canonical URL inline per the Repo
   header above). Integration tests need a local Postgres: install
   postgresql16-server, `initdb -U postgres --auth=trust` at
   `/tmp/pgdata`, `pg_ctl start`, create db `xiosync`, and ensure
   `DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/xiosync`
   is in `.env.development.local` (on its own line).
2. Next Phase 1 slice — **OrgContext middleware (C1) + session lifecycle
   (C8)** per docs 05 §2/§4 and 04 §2/§6: derive OrgContext from the
   authenticated session, set `app.current_org` per-transaction at the
   persistence boundary (the RLS GUC the 0002 policies key on), session
   issuance/rotation/revocation. Work on a feature branch off `main`
   @ `87e0086`; write the CHECKPOINT step plan before the first edit.
3. Then: authority axes (H4/H8) and the single `authorize(...)` decision
   point (C3). Exit gate = the security-negative suite (doc 05 §8, doc 11).
4. Before writing app-facing code, resolve D-015's note that the v0
   sandbox `app/` scaffold is deleted when implementation begins — check
   D-015's exact wording and comply.
5. Canonical `main` is branch-protected: feature branch + PR + GitHub CI
   green (D-016/D-017) + squash-merge; never force-push canonical `main`.

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
