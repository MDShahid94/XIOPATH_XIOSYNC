# AGENTS.md — Boot Sequence for Any Incoming Agent

> **Read this first. Every time. No exceptions.**
> This file is the mandatory entry point for any agent session on this project.

---

## 1. Understand What This Project Is

XIOSYNC is a **ground-up rebuild** of XIOPATH — a multi-tenant workflow
orchestration platform. The rebuild is governed by the blueprint in
`xiosync-blueprint/`. Every implementation decision is pre-recorded there.
You do not improvise structural choices; you execute the blueprint.

**Prime directive:** enforcement precedes features. No phase starts until the
prior phase's exit gate passes with attached proof.

---

## 2. Know the Current State (3 reads, in order)

### Read 1 — Where are we?
Open `xiosync-blueprint/10-build-roadmap-and-gates.md`.
This is the phase plan. Find the last phase marked ✅ complete.
The **current work** is the next phase after the last ✅ gate.

### Read 2 — What exactly is done vs. pending in this phase?
Open `xiosync-blueprint/11-acceptance-gates.md`.
Find the gate IDs for the current phase and check which ones have passing proof.
A gate without attached, reproducible proof is **not closed** — regardless of code.

### Read 3 — What are the architectural constraints?
Open `xiosync-blueprint/DECISIONS.md`.
All structural decisions are recorded here. Do not re-open a decided question.
If you believe a decision needs revision, record a new entry — do not patch silently.

---

## 3. Determine the Exact Next Action

After the three reads above, you should be able to state:

- The **current phase** (e.g. "Phase 4 — Workers & the execution plane")
- The **last closed gate** (e.g. "Step 4 COMPLETE — INV-TASK-SEC-1/2")
- The **next required output** and which gate IDs it closes

If you cannot state these without asking a human, re-read the three sources above.

---

## 4. Build Rules (always active)

- **Python backend only.** Do NOT generate React, Next.js, or any UI code.
  Do NOT create `app/`, `components/`, or any `package.json`.
- **PostgreSQL only.** No SQLite anywhere (code, config, tests).
- **Alembic migrations only** — no runtime DDL (`CREATE TABLE`, `create_all`).
  All schema changes go in `migrations/`.
- **Single test command:** `pytest` from the repo root.
  Tests live in `tests/unit/` and `tests/integration/`.
- **Linting:** `ruff check .` and `mypy xiosync/` must both pass clean.
- **No fabricated test fixtures** — tests run against the migrated schema
  (see `xiosync-blueprint/06-persistence-schema.md`).
- **INV-ROADMAP-3:** You may use `unittest.mock.MagicMock` or add
  `# type: ignore` on test double instantiations to avoid burning tokens
  on mypy-strict compliance inside test files.
- **No parallel vocabulary:** never use `agent`/`actor` aliases,
  `_v2` twins, or any term from the XIOPATH legacy forbidden list
  (`xiosync-blueprint/GLOSSARY.md`).

---

## 5. When You Are Done

You are done when:
1. The exit gate(s) specified in `xiosync-blueprint/10-build-roadmap-and-gates.md`
   for the current phase/step **pass reproducibly**.
2. The exact command and its output are recorded as proof.
3. `ruff check .` and `mypy xiosync/` are clean.
4. `pytest` passes without new failures.

Do not claim a gate closed without attached, reproducible proof.
A gate without proof is open — see `xiosync-blueprint/11-acceptance-gates.md §1`.

---

## 6. Reference Map

| Need | Read |
|---|---|
| Full phase plan + exit gates | `xiosync-blueprint/10-build-roadmap-and-gates.md` |
| Per-gate proof requirements | `xiosync-blueprint/11-acceptance-gates.md` |
| All architectural decisions | `xiosync-blueprint/DECISIONS.md` |
| Domain model + invariants | `xiosync-blueprint/03-ontology-formal-spec.md` |
| Security model | `xiosync-blueprint/05-security-identity-tenancy.md` |
| Schema authority | `xiosync-blueprint/06-persistence-schema.md` |
| Workers & execution plane | `xiosync-blueprint/07-execution-workers-phantom.md` |
| Investigation method | `xiosync-blueprint/12-investigation-playbook.md` |
| Vocabulary (forbidden terms) | `xiosync-blueprint/GLOSSARY.md` |
| Legacy evidence (read-only) | `XIOPATH/` (committed, do not modify) |
