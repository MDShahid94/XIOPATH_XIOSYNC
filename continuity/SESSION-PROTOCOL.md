# Session Protocol — XIOV0 Orchestrated

> This project's continuity is managed by the **XIOV0 Agentic Pipeline**.
> V0 agents do NOT manage these files — the orchestrator does.

## Boot Sequence (for any agent)

1. Read `continuity/STATE.md` → know the current phase, step, and next action.
2. Read `continuity/HANDOFF-LOG.md` → know what has been done and by whom.
3. Read `xiosync-blueprint/DECISIONS.md` → know all architectural decisions.
4. Read `xiosync-blueprint/10-build-roadmap-and-gates.md` → know the full phase plan.
5. Begin work on the "Next Action" from STATE.md.

## Handoff Rules

1. After completing a step, the orchestrator updates `STATE.md` and appends to `HANDOFF-LOG.md`.
2. `STATE.md` is the **single source of truth** for current position.
3. `HANDOFF-LOG.md` is **append-only** — never edit past entries.
4. V0 workspace injection **excludes** `continuity/` — these files are for the master agent only.

## Compatibility with D-025

D-025 offloaded continuity tracking to the external orchestrator (XIOV0).
These files remain in the repo as a **portable fallback** — any agent cloning
the repo can bootstrap from `STATE.md` alone without the orchestrator.
