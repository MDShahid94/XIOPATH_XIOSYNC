# CHECKPOINT — live micro-state (crash-recovery cursor)

> Unlike HANDOFF-LOG.md (append-only ledger), this file is **overwritten
> freely** and describes only the *current instant*. It exists so that an
> agent killed mid-task loses at most ONE step of work. Rules in
> SESSION-PROTOCOL.md §5. Keep it under ~25 lines — it is a cursor, not a log.

- **Status:** IDLE
- **Session:** 018 (Phase 1 slice 1 complete: identity tables + revision
  0002 + RLS/immutability tests; PR #2 squash-merged into canonical `main`
  @ `87e0086`, GitHub CI run `29373985898` success)
- **Task:** none in progress. Next task per STATE.md "exact next action":
  Phase 1 slice 2 — OrgContext middleware (C1) + session lifecycle (C8).
- **Branch:** local `main` = canonical `main` @ `87e0086`;
  `phase1/identity-tables` deleted (merged).
- **Step plan:** (none — write one before starting the next task, §5.1)
- **Cursor:** n/a.
- **Local DB note:** in-sandbox Postgres 16.12 (UTF8) at `localhost:5432`,
  data dir `/tmp/pgdata` (`pg_ctl -D /tmp/pgdata start` if stopped);
  `DATABASE_URL` in `.env.development.local`. Sandbox-only — a duplicated
  workspace must redo the §7.1 restore. GitHub CI remains the
  authoritative postgres:17 proof (D-016).
