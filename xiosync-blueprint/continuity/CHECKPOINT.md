# CHECKPOINT — live micro-state (crash-recovery cursor)

> Unlike HANDOFF-LOG.md (append-only ledger), this file is **overwritten
> freely** and describes only the *current instant*. It exists so that an
> agent killed mid-task loses at most ONE step of work. Rules in
> SESSION-PROTOCOL.md §5. Keep it under ~25 lines — it is a cursor, not a log.

- **Status:** IN-PROGRESS
- **Session:** 020 (budget USD 5.0; recovered crashed session 019 — its
  cursor said "step 1 starting" but steps 1 `bc75af5` and 2 `b155b26` were
  committed; §5.2 proof re-run found step 2's test red, see step 2b).
- **Task:** Phase 1 slice 2 — OrgContext (C1) + session lifecycle (C8)
  foundations: domain contract + persistence boundary (docs 05 §2/§3,
  04 §2/§6). HTTP middleware wiring is the NEXT slice.
- **Branch:** `phase1/orgcontext-sessions` off `main` @ `87e0086`.
- **Step plan:**
  1. ✅ `domain/context.py` OrgContext + unit tests (`bc75af5`).
  2. ✅ `persistence/tenancy.py` org_scoped_session + integration tests
     (`b155b26`) — but proof re-run red: after a scoped txn commits, the
     GUC reverts to '' (not NULL) on the pooled connection and the 0002
     policy's bare `::uuid` cast errors instead of matching no rows.
  2b. ✅ Revision 0003 ALTER POLICY → `NULLIF(current_setting(...), '')::uuid`
     (`29eb21b`); proof: ruff + format + mypy --strict (54 files) +
     lint-imports (4 kept) + `pytest tests -q` → **88 passed, 0 skipped**.
  3. Full local gate green (see 2b proof); push branch; PR + CI + merge if
     budget allows, else hand off with branch pushed.
- **Cursor:** step 3 (push + PR).
- **Local DB note:** in-sandbox Postgres 16.12, data dir `/tmp/pgdata2`
  (UTF8 — a C-locale/SQL_ASCII cluster breaks psycopg text decoding);
  `DATABASE_URL` in `.env.development.local` on its own line.
  Sandbox-only; duplicated workspaces redo §7.1. CI is authoritative.
