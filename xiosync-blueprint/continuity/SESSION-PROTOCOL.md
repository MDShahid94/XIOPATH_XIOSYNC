# SESSION-PROTOCOL — How Any Agent Boots, Works, and Hands Off

> Normative. This protocol is what makes agent-to-agent continuity lossless.
> An agent that skips it forfeits any claim its work is "done".

---

## 1. Boot (before any work)

1. Read root `AGENTS.md`.
2. Read `CHECKPOINT.md`. If **Status: IN-PROGRESS**, the previous agent was
   killed mid-task — go directly to **§5 Crash recovery** before anything
   else. If IDLE, continue.
3. Read `STATE.md`. Confirm its "Last updated" session matches the newest
   entry in `HANDOFF-LOG.md`. If it does not, the previous handoff was broken:
   reconstruct the true position from the log + `git log`, repair STATE.md,
   and record the repair as your session's first log item.
4. Read the governing blueprint docs named in STATE.md's "next action".
5. Run the cheap integrity checks:
   - `git status --short` — the tree should be clean at boot; a dirty tree
     with an IDLE checkpoint is itself a crash signal → §5.
   - README index link check (all `./*.md` links in `xiosync-blueprint/README.md`
     resolve).
6. State (to the user, or in your working notes) the task you are picking up,
   in one sentence, before touching a file.

## 2. Work discipline

- **Scope:** work only the task named in STATE.md unless the user redirects
  you; if redirected, record the redirection in your log entry.
- **Blueprint supremacy:** content conflicts resolve in favor of the blueprint
  docs; deliberate blueprint changes require editing the doc AND a
  `DECISIONS.md` entry (never a silent contradiction).
- **Legacy boundary:** `XIOPATH/` is read-only evidence. Cite it
  (file + line) when verifying doc 02 claims; never copy code out of it.
- **Verification:** every claim of completion carries the exact command run
  and its observed result. A blocked check is recorded verbatim as blocked.
- **Vocabulary:** GLOSSARY.md terms only. The forbidden-terms table applies to
  docs, code, comments, and commit messages.

## 3. Handoff (mandatory before stopping, even mid-task)

Execute in this order — the ordering is deliberate (log first, then position):

1. **Append a session entry to `HANDOFF-LOG.md`** using the template below.
2. **Update `STATE.md`**: milestone table, "Last updated", and rewrite
   "The exact next action" so a cold agent can continue without you.
3. **Record durable decisions** made this session in `DECISIONS.md`.
4. **Leave the tree committed.** Work-in-progress is fine; uncommitted and
   undescribed work is not — it will be lost or misread.

## 4. Budget interrupts and manual sentinel

Two separate mechanisms trigger the same safe handoff. Neither is an
authoritative v0 or Vercel billing API, and neither stores credentials or
account identity.

### 4.1 Prompt interrupt

When the operator sends the exact normalized message `BUDGET LOW` (ignoring
only surrounding whitespace and letter case), treat it as an out-of-band,
highest-priority interrupt rather than ordinary queued task input. It preempts
all queued messages: do not accept or start another task or step. If an edit is
already underway, finish only its smallest safe durable unit when possible,
then perform §3 in order, set CHECKPOINT to IDLE as the final continuity edit,
and stop. The prompt interrupt does not require, read, or mutate the numeric
snapshot.

### 4.2 Numeric snapshot sentinel

1. The operator refreshes the local, gitignored snapshot with
   `uv run python tools/budget_sentinel.py set <USD_AMOUNT>`. `set` validates,
   records the amount, and **returns the decision immediately**: below the
   threshold it prints `decision=handoff-required` plus the full handoff
   sequence and exits `20`, so `set 0` alone is a complete, unmissable stop
   order. At or above the threshold it prints `decision=continue` and exits `0`.
2. After boot/crash recovery and at every checkpoint step boundary, run
   `uv run python tools/budget_sentinel.py guard`.
3. For `set`, `guard`, `status`, and `handoff`, exit `0` means continue. Exit
   `20` means the amount is below the threshold (default USD 0.50). Exit `21`
   means the snapshot is absent, invalid, or stale (default maximum age:
   6 hours). Both nonzero results fail closed. `handoff` prints the
   graceful-stop checklist **unconditionally** — including when the snapshot
   is missing or stale (the post-duplication state, §7.1) — because the
   checklist is the point of the command, not a reward for a healthy snapshot.
4. On a nonzero result, do not begin another step. If a step is already in
   progress, finish only its smallest safe durable unit when possible, then
   perform §3 in order. Run `... budget_sentinel.py handoff` to print the
   checklist. Set CHECKPOINT to IDLE as the final continuity edit and stop.
5. Another authorized account or agent is started manually with the resume
   prompt in AGENTS.md. Never rotate credentials or accounts automatically.

Threshold and freshness can be changed per invocation with `--threshold` and
`--max-age-hours`; place these options before the command name.

### Session entry template

```md
## Session NNN — <one-line title>

- **Date:** YYYY-MM-DD
- **Scope:** what was attempted and why (tie to STATE.md's next action).
- **Produced:** files created/changed, migrations, decisions (IDs).
- **Verification:** exact commands + observed results; blocked checks verbatim.
- **Not done / known gaps at handoff:** anything a successor must know,
  including partial work, suspected issues, and open questions.
```

## 5. Crash recovery — resuming after an abrupt stop

Agents run under hard API/context limits and can be killed at any token.
This section makes the **maximum possible loss = one step of one task**.

### 5.1 Checkpoint discipline (while working)

1. **Before** starting any task expected to take more than one edit-and-verify
   cycle, overwrite `CHECKPOINT.md`: Status → IN-PROGRESS, the task, a
   numbered step plan, cursor at step 1.
2. **A step must be small enough to complete within a few tool calls** and
   must end in a *durable* state: files written + a verification command run.
3. **At every step boundary:** commit the work (`wip(<task>): step N — <what>`
   is a valid message; broken-but-described beats lost), then advance the
   CHECKPOINT cursor and record the step's proof (command + result + SHA).
   Commit-then-checkpoint, in that order — a checkpoint pointing past the
   commits is the one unrecoverable lie. Then run the §4 budget guard before
   beginning the next step.
4. **Never** hold >1 step of work uncommitted. The chat transcript, tool
   buffers, and the agent's memory are all assumed to evaporate at any moment;
   **git + the three continuity files are the only storage that exists.**
5. On graceful handoff (§3), set CHECKPOINT Status → IDLE as the final edit.

### 5.2 Recovery procedure (successor agent)

1. **Do not redo the whole task and do not trust the cursor blindly.** The
   crash window is between "cursor step N-1 done" and "step N proof recorded".
2. Establish ground truth: `git log --oneline -10` and `git status --short`.
   - Dirty tree → the crash happened mid-step. Read the diff; if it matches
     the cursor step and is completable in-context, finish and commit it as
     that step; otherwise `git stash` it, note the stash in your log entry,
     and redo the step cleanly.
   - Clean tree → re-run the **last recorded proof command** from
     CHECKPOINT.md. Green → cursor is truthful, continue at the next step.
     Red → step back one step and re-verify until green, then resume.
3. Resume executing the remaining steps under §5.1 discipline.
4. In your session's HANDOFF-LOG entry, record: "recovered from crashed
   session NNN at step N" + what was salvaged vs. redone. Do NOT fabricate a
   handoff entry for the crashed session.

### 5.3 Minimum context contract

The **only** state a successor may need is, in priority order:
1. `git log` + tree (the work itself),
2. `CHECKPOINT.md` (the cursor),
3. `STATE.md` (the phase position),
4. `HANDOFF-LOG.md` (history, on demand),
5. the governing blueprint docs (content, on demand).

Everything else — chat history, tool outputs, prior agents' reasoning — is
explicitly **non-load-bearing**. If completing a task would require context
outside this list, that context must first be written into one of these files.

## 7. Workspace duplication survival (v0 credit-cycle drill)

The operator's standing workflow: **when the chat's budget reaches zero, the
entire workspace is duplicated into a fresh v0 workspace** (to obtain new
credits) and work resumes there. Duplication copies the git repo and tracked
files but the new sandbox is otherwise cold. Everything the process depends on
must therefore live in **tracked files** — this section records what does NOT
survive and the exact restore drill (first proven live in Sessions 010→011).

### 7.1 What does NOT survive a duplication

| Lost artifact | Why | Restore |
|---|---|---|
| `.continuity-budget.json` (sentinel snapshot) | gitignored | Operator: `uv run python tools/budget_sentinel.py set <USD_AMOUNT>` (the resume prompt's `BUDGET USD <amount>` line carries the number); agent then runs `... guard` before any work (§4.2) |
| `.env.development.local` (`DATABASE_URL` etc.) | gitignored | Re-provided by the workspace's connected Neon integration; agent verifies with `GetOrRequestIntegration` and, if absent, requests reconnection before DB-touching steps |
| Python venv / installed deps | `.venv/` gitignored | `uv` recreates from the committed `pyproject.toml` + `uv.lock` on first `uv run ...` — no manual action |
| GitHub remote (once connected) | remote config may reset to a v0 bundle | Operator reconnects GitHub via v0 settings; agent records the state of `git remote -v` at boot |
| Chat history, tool buffers, agent memory | by design non-load-bearing (§5.3) | Nothing — git + the three continuity files are the only storage |

### 7.2 Rules that keep duplication lossless

1. **Never** let process-critical state exist only in a gitignored file, the
   chat, or the sandbox filesystem. If a session introduces such state, it
   MUST add a row to the §7.1 table (with its restore step) in the same
   session.
2. Secrets stay out of git regardless — the restore path for secrets is
   always the integration/operator, never a committed copy.
3. The resume prompt (AGENTS.md) + this drill are sufficient to cold-boot in
   a duplicated workspace: boot per §1, restore per §7.1, then continue from
   STATE.md. Session 010 is the precedent: the sentinel guard failed closed
   (exit 21) in the duplicate until the operator re-set it — that is the
   intended fail-closed behavior, not an error.
4. In-sandbox integration tests need the env exported first:
   `set -a; source .env.development.local; set +a`.

## 8. Failure modes this protocol exists to prevent

| Failure | Prevented by |
|---------|--------------|
| New agent re-derives context from scratch (slow, drifts) | AGENTS.md boot sequence + STATE.md position |
| Progress claimed but unproven | Verification-with-command rule (prime directive 7) |
| Two agents' work silently diverging | Single STATE.md authority + clean-tree-at-boot check |
| Decisions living only in chat | DECISIONS.md + HANDOFF-LOG.md as the only records |
| Legacy patterns leaking back in | Read-only XIOPATH boundary + doc 02 catalog + grep gates |
| Stale STATE.md poisoning the next session | Log-vs-STATE cross-check at boot (§1.3) |
| Agent killed mid-task loses the session's work | CHECKPOINT.md cursor + 1-step commit rule (§5.1) |
| Successor re-does finished work or trusts unfinished work | Proof re-run recovery procedure (§5.2) |
| Task depends on context that dies with the chat | Minimum context contract (§5.3) |
| Credit-cycle workspace duplication silently loses process state | Duplication survival drill + tracked-files-only rule (§7) |
