# CHECKPOINT — live micro-state (crash-recovery cursor)

> Unlike HANDOFF-LOG.md (append-only ledger), this file is **overwritten
> freely** and describes only the *current instant*. It exists so that an
> agent killed mid-task loses at most ONE step of work. Rules in
> SESSION-PROTOCOL.md §5. Keep it under ~25 lines — it is a cursor, not a log.

- **Status:** IN-PROGRESS
- **Session:** 014
- **Task:** Phase 0 exit-gate proof (recovered from crashed session 013).
- **Recovery findings:** workspace was credit-cycle duplicated into a NEW
  repo `chainaanantapurasha-rgb/XIO_SYNC_V0` (history squashed to `b4bb356`
  + `aaa3f22`); session 013's step-1 commit (`5c73927`) is gone. The tracked
  `ci.yml.pending` survived and already carries the `push.branches: [main]`
  fix. Sentinel set 9.71, guard → continue. gh CLI authenticated; repo
  default branch `main`.
- **Step plan:**
  1. Redo 013-step-1: copy `ci.yml.pending` → `.github/workflows/ci.yml`,
     delete pending, verify yaml parse + job list, commit on head branch
     `v0/shahidraiganj-7383-804ea72a` (never commit to main directly).
  2. Push the head branch; open PR to `main` (pull_request trigger fires
     CI). If push rejects workflow files (token scope), fall back to
     restoring ci.yml.pending + operator instruction.
  3. Poll PR check-runs until all 3 jobs conclude; record green run ID +
     SHA per D-017. If red, fix and repeat.
  4. Handoff per §3 (operator items: merge PR, branch protection requiring
     all 3 jobs, Gate 10 scanner choice); checkpoint → IDLE.
- **Cursor:** step 1.
