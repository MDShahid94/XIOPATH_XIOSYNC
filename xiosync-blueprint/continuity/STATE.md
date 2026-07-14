# STATE — Current Ground-Truth Position of the XIOSYNC Rebuild

> **Authoritative for position.** Any agent booting into this project reads
> this file first (per root `AGENTS.md`). The last agent to work MUST have
> updated this file before stopping; if the "Last updated" session below does
> not match the newest entry in `HANDOFF-LOG.md`, treat the log as truth and
> repair this file first.

- **Last updated:** Session 012 — 2026-07-15
- **Repo branch:** `master`

---

## Where the rebuild stands

| Milestone | Status |
|-----------|--------|
| Blueprint authored (docs 00–12, DECISIONS, GLOSSARY) | ✅ Complete |
| Legacy XIOPATH placed in repo root as evidence | ✅ Complete (committed in Session 002) |
| Continuity plane (this system: AGENTS.md, STATE, HANDOFF-LOG, SESSION-PROTOCOL) | ✅ Complete (Session 002) |
| Phase R — Rebuild-readiness deep research (doc 10) | ✅ Complete (Session 003 — D-013..D-018) |
| **Phase 0 — Foundation & guardrails** | In progress — all in-sandbox work complete: `platform/` (`bc3faa8`), Postgres wiring + Alembic scaffold (`bf679d4`), migration test harness on Neon (`198d176`), CI workflow authored (Session 012, `a221516`). **Sole remaining blocker: operator connects GitHub** so CI runs green and blocking (D-016/D-017 exit-gate proof) |
| Phases 1–7 | 🔲 Blocked (sequential, gated) |

**No XIOSYNC implementation code exists yet.** The `app/` directory is the v0
sandbox scaffold, not XIOSYNC; per D-015 it is deleted when Phase 0 begins.

## The exact next action

Execute **Phase 0 — Foundation & guardrails** as specified in
[`../10-build-roadmap-and-gates.md`](../10-build-roadmap-and-gates.md) §"Phase 0",
using the fully pinned foundation from DECISIONS.md **D-013..D-019**:

1. Boot per SESSION-PROTOCOL §1 and, if this is a freshly duplicated
   workspace (operator credit-cycle), run the **§7 duplication-survival
   drill** first: operator re-sets the sentinel (`uv run python
   tools/budget_sentinel.py set <USD_AMOUNT>` from the `BUDGET USD` line),
   agent runs `... guard`; verify `DATABASE_URL` exists in
   `.env.development.local` (Neon integration) before DB-touching steps.
2. **Complete — do not redo:** `platform/` (`bc3faa8`); Postgres wiring +
   Alembic scaffold (`bf679d4`); migration test harness on Neon (`198d176`);
   SESSION-PROTOCOL §7 duplication drill (`739deb1`); CI workflow
   `.github/workflows/ci.yml` with Phase 0 gates — lint-type-arch, unit,
   migration-chain on `postgres:17` service container (`a221516`; all gate
   commands proven green locally, 57 pytest / ruff / format / mypy --strict
   / lint-imports 4/0).
3. **Next (blocked on operator): connect GitHub.** Once `git remote -v`
   shows GitHub: push, confirm the `ci` workflow runs green, have the
   operator require all three jobs in branch protection, choose the Gate 10
   secret scanner, and record the green run ID + SHA in HANDOFF-LOG per
   D-017. That closes the Phase 0 exit gate (doc 10) — then flip the
   milestone to ✅ and Phase 1 (domain ontology, doc 03) opens.
4. If GitHub is still not connected when a session starts, there is no
   in-sandbox Phase 0 work left — do not invent tasks or start Phase 1
   early (roadmap ordering is mandatory). State the blocker and stop
   cheaply, preserving budget.
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
