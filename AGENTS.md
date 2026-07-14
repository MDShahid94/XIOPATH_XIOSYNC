# AGENTS.md — XIOSYNC Rebuild: Agent Bootstrap (READ THIS FIRST)

> You are an agent joining the **XIOSYNC rebuild**. This file is the single
> entrypoint. Everything you need is in this repository — chat history from
> previous sessions is NOT available to you and MUST NOT be assumed.

---

## What this repository is

| Path | Role |
|------|------|
| `xiosync-blueprint/` | **Normative ground truth.** The complete rebuild blueprint (docs 00–12 + DECISIONS + GLOSSARY). Read `xiosync-blueprint/README.md` first. |
| `xiosync-blueprint/continuity/` | **Live position.** Where the rebuild currently stands, what happened in every prior session, and how to hand off. |
| `XIOPATH/` | **Legacy evidence, read-only.** The original XIOPATH codebase (~35,700 LOC). Consult it to verify audit claims (doc 02) or recover a good idea. **Never copy code from it.** It is evidence, not a source. |
| `app/`, `components/`, `lib/` | v0 sandbox Next.js scaffold. Not part of XIOSYNC yet; the XIOSYNC implementation layout is defined in blueprint doc 04 §6. |

## The resume prompt (what the user pastes to start any session)

> Read AGENTS.md at the repo root and follow its boot sequence. Continue the
> XIOSYNC rebuild from where continuity/CHECKPOINT.md and continuity/STATE.md
> say it stands — if the checkpoint is IN-PROGRESS or the tree is dirty, run
> crash recovery per SESSION-PROTOCOL §5 first. Work only the named next
> action, keep CHECKPOINT.md and step commits current as you go, and hand off
> per protocol before you stop.

That prompt is sufficient for any agent, cold or resuming from a crash. No
other chat context is required or assumed.

## Boot sequence (mandatory, in order)

1. Read `xiosync-blueprint/continuity/CHECKPOINT.md` — the live micro-state.
   **IN-PROGRESS status or a dirty git tree means the previous agent crashed
   mid-task: follow SESSION-PROTOCOL.md §5 (crash recovery) before anything.**
2. Read `xiosync-blueprint/continuity/STATE.md` — the current phase, the task
   in progress, and the exact next action. This is your position.
3. Read `xiosync-blueprint/continuity/HANDOFF-LOG.md` — the append-only ledger
   of every prior session. This is your history.
4. Read `xiosync-blueprint/README.md` — the prime directives and doc index.
   This is your law.
5. Read the blueprint doc(s) that govern the task named in `STATE.md`
   (STATE.md names them explicitly).
6. Check the operator-maintained budget sentinel after any required crash
   recovery: `uv run python tools/budget_sentinel.py guard`. Missing,
   malformed, stale, or sub-threshold snapshots fail closed; follow
   SESSION-PROTOCOL.md §4 instead of starting work. This snapshot is not an
   authoritative v0/Vercel billing balance.
7. Only then act. Follow
   `xiosync-blueprint/continuity/SESSION-PROTOCOL.md` for how to work and how
   to hand off when you stop.

## Operator budget interrupt (highest priority)

If the operator sends the exact normalized message `BUDGET LOW` (ignoring only
surrounding whitespace and letter case), treat it as an out-of-band interrupt,
not as ordinary queued task input. It preempts every queued message: do not
accept or start more work. If an edit is already underway, finish only its
smallest safe durable unit when possible, then immediately execute
SESSION-PROTOCOL.md §3 in order, set CHECKPOINT to IDLE as the final continuity
edit, and stop. This prompt signal neither requires nor mutates the numeric
budget snapshot and never authorizes automatic credential or account rotation.

## Non-negotiable rules (summary — full text in blueprint README)

- **Enforcement precedes features.** No phase's features before its exit gate
  prerequisites (doc 10, INV-ROADMAP-1).
- **One canonical vocabulary** (GLOSSARY.md). No `agent`/`actor` aliases, no
  `_v2` twins, no forbidden terms.
- **Never reintroduce a legacy pattern** cataloged in doc 02.
- **Verify, then claim.** Attach the exact command and result. Never claim a
  green you did not see.
- **Record durable decisions** in `xiosync-blueprint/DECISIONS.md`; record
  session outcomes in `HANDOFF-LOG.md`. Chat is not a record.
- **Update `STATE.md` before you stop.** An agent that leaves STATE.md stale
  has failed its handoff, regardless of how much code it wrote.

## If STATE.md conflicts with anything

`STATE.md` is authoritative for *position* (what's done, what's next).
The blueprint is authoritative for *content* (what must be built and how).
If they appear to conflict, the blueprint wins on content; fix STATE.md and log
the correction in HANDOFF-LOG.md.
