# STATE — Current Ground-Truth Position of the XIOSYNC Rebuild

> **Authoritative for position.** Any agent booting into this project reads
> this file first (per root `AGENTS.md`). The last agent to work MUST have
> updated this file before stopping; if the "Last updated" session below does
> not match the newest entry in `HANDOFF-LOG.md`, treat the log as truth and
> repair this file first.

- **Last updated:** Session 014 — 2026-07-15
- **Repo:** `chainaanantapurasha-rgb/XIO_SYNC_V0` (GitHub; default branch
  `main`). Work branch: `v0/shahidraiganj-7383-804ea72a` (PR #1 → main).

---

## Where the rebuild stands

| Milestone | Status |
|-----------|--------|
| Blueprint authored (docs 00–12, DECISIONS, GLOSSARY) | ✅ Complete |
| Legacy XIOPATH placed in repo root as evidence | ✅ Complete (committed in Session 002) |
| Continuity plane (this system: AGENTS.md, STATE, HANDOFF-LOG, SESSION-PROTOCOL) | ✅ Complete (Session 002) |
| Phase R — Rebuild-readiness deep research (doc 10) | ✅ Complete (Session 003 — D-013..D-018) |
| **Phase 0 — Foundation & guardrails** | In progress — all agent work complete. **CI proven green on GitHub (D-017): run `29367288883`, SHA `1f84669`, PR #1** — jobs lint-type-arch / unit / migration-chain all pass. Note: history was squashed in the Session 013→014 workspace duplication; old SHAs (`bc3faa8` etc.) no longer resolve, the work itself survived. **Remaining: operator merges PR #1 + sets branch protection** (D-016) |
| Phases 1–7 | 🔲 Blocked (sequential, gated) |

**No XIOSYNC implementation code exists yet.** The `app/` directory is the v0
sandbox scaffold, not XIOSYNC; per D-015 it is deleted when Phase 0 begins.

## The exact next action

Close the **Phase 0 exit gate** (doc 10). All agent-side work is done and
proven; what remains is operator action, then verification:

1. Boot per SESSION-PROTOCOL §1 (sentinel set/guard; if freshly duplicated
   workspace, §7 drill first — and note the duplication may squash git
   history and drop gitignore rules / `xiosync/*` symlinks; check
   `git ls-files xiosync/` and `uv run python -c "import
   xiosync.platform.clock"` before trusting CI).
2. **Complete — do not redo:** everything through CI-green-on-GitHub.
   Proof (D-017): workflow `.github/workflows/ci.yml` on branch
   `v0/shahidraiganj-7383-804ea72a`, PR #1, run `29367288883` SHA
   `1f84669` `conclusion=success` (jobs: lint-type-arch, unit,
   migration-chain on postgres:17). See HANDOFF-LOG Session 014.
3. **Blocked on operator:** (a) merge PR #1 into `main`; (b) set branch
   protection on `main` requiring all three CI jobs (D-016); (c) choose
   the Gate 10 secret scanner (doc 09 §7).
4. When a session starts and PR #1 is merged: verify the push-trigger run
   on `main` is green, record it in HANDOFF-LOG, flip the Phase 0
   milestone to ✅, and open **Phase 1 (domain ontology, doc 03)**. If PR
   #1 is not merged, state the blocker and stop cheaply — do not start
   Phase 1 early (roadmap ordering is mandatory).
5. Deferred: autogenerate-drift half of INV-TEST-SCHEMA-2 until ORM models
   exist (Phase 1+; `target_metadata` is `None` in
   `persistence/migrations/env.py`).

No structural questions remain open — do not improvise a stack or layout
choice; everything is in D-013..D-019.

**Governing docs for the next task:** 10 (roadmap, Phase 0), 04 §2/§6
(layering + layout), 06 (persistence/migrations, §10 test harness),
09 (config/CI), DECISIONS.md D-013..D-019.

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
