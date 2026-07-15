# CHECKPOINT — live micro-state (crash-recovery cursor)

> Unlike HANDOFF-LOG.md (append-only ledger), this file is **overwritten
> freely** and describes only the *current instant*. It exists so that an
> agent killed mid-task loses at most ONE step of work. Rules in
> SESSION-PROTOCOL.md §5. Keep it under ~25 lines — it is a cursor, not a log.

- **Status:** IN-PROGRESS
- **Session:** 024 (budget USD 5.0, sentinel set, guard=continue; recovered
  session 023's IN-PROGRESS checkpoint — clean tree, step-5 proof re-run
  green: `pytest tests/tools -q` → 26 passed; cursor at step 6 truthful,
  nothing lost. §7.1 drill redone: Postgres 16.12 UTF8 at /tmp/pgdata, db
  `xiosync`, DATABASE_URL appended; `pytest tests/integration -q` → 10
  passed).
- **Task:** Phase 1 slice 3 — session lifecycle (C8) + HTTP middleware
  wiring (docs 05 §2/§4, 04 §2/§6).
- **Branch:** `phase1/sessions-middleware` (off local main @ `4ab62f9`).
- **Step plan:**
  1–4. ✅ (session 021: threshold `6deaccc`, drill `55ddc3a`, design
     `8b3c332`, tokens+config+D-023 `a656f10`).
  5. ✅ Sentinel decay (D-024) — `440892d`; proof: ruff+format+mypy
     --strict clean, `pytest tests/tools -q` → 26 passed.
  6. `persistence/identity.py` repo + `services/identity.py`
     SessionService (login, refresh+rotation+reuse-revoke INV-SESSION-3,
     logout, revoke-all INV-SESSION-2, validate→OrgContext INV-SESSION-1)
     + unit/integration tests; commit.
  7. `api/app.py` + `api/middleware.py` (request_id → security_headers →
     body_size → authenticate) + auth router (login/refresh/logout) +
     contract tests; commit.
  8. Full gate (ruff, format, mypy --strict, import-linter, pytest all),
     push branch, PR, graceful handoff.
- **Cursor:** step 6.
- **Local DB note:** cluster must be UTF8; Postgres 16.12 running at
  /tmp/pgdata (UTF8, C.UTF-8), db `xiosync`, DATABASE_URL appended.
