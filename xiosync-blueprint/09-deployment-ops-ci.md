# 09 — Deployment, Ops & CI

> Normative. Defines deployment, CI gates, observability, backup/DR, and
> rollout/rollback. Remediates C4, C6, M1, M4, M5, M7, H9, L4, L5. RFC 2119
> keywords binding.

---

## 1. Environments & configuration

- Environments: `dev`, `ci`, `staging`, `production`. Each has an explicit,
  separate configuration; nothing is shared implicitly.
- **INV-CFG-1:** All secrets and environment-specific values come from
  configuration/secret backends (doc 05 §7). **No embedded defaults** — a
  missing required secret **fails startup in every environment** (kills L4's
  `"xiopath-dev-secret-change-in-production"`).
- **INV-CFG-2:** Configuration is validated at startup against a schema; unknown
  or missing required keys fail fast (mirrors M5's fix).
- **INV-CFG-3:** Exactly one package manager per ecosystem with one lockfile
  (pnpm for JS, uv/pip-tools for Python). Two lockfiles in one package is a CI
  failure (kills L5's dual `package-lock.json` + `pnpm-lock.yaml`).

---

## 2. CORS (C4 remediation)

**INV-CORS-1:** CORS uses a **single explicit origin allowlist** sourced from
per-environment configuration. There is **no** `allow_origin_regex` and **no**
wildcard. Credentialed CORS is enabled **only** for the enumerated origins
(kills C4's `allow_origin_regex=".*"` + `allow_credentials=True`).

- The allowlist is validated at startup (non-empty in staging/prod, no `*`).
- A **CORS configuration test** asserts a non-allowlisted origin is rejected and
  that no wildcard is present in any environment config (doc 11).

---

## 3. Migration as a deploy step (C6 remediation)

**INV-DEPLOY-1:** Migrations run as a **discrete, single, ordered job** against
the configured `DATABASE_URL`, **before** API rollout, **never** inside the API
process and **never** per replica (doc 06 §3). `start.sh`-style in-process
`alembic upgrade head` is forbidden.

```
release pipeline:
  build ─▶ migration-job (once) ─▶ assert head == expected
        ─▶ rollout API replicas (read-only on schema)
        ─▶ API readiness gate (head match) ─▶ traffic
```

- **INV-DEPLOY-2:** API replicas **verify** the DB is at the expected head at
  startup and **refuse to serve** otherwise (doc 06 INV-SCHEMA-2). They never
  apply migrations.
- Expand→contract for destructive changes (doc 06 §3) makes the migration job
  compatible with the still-running old replicas during rollout.

---

## 4. Startup preconditions & fail-fast (M5 remediation)

XIOPATH wrapped migration, seed, and orchestrator init in `try/except Exception`
that logged a warning and continued, so broken installs "booted successfully"
(M5). XIOSYNC inverts this:

- **INV-STARTUP-1:** Hard preconditions fail startup: DB reachable and at
  expected head, required `core.*` types present (doc 06 §8), signing keys and
  required secrets present (doc 05 §7), crypto available (M6).
- **INV-STARTUP-2:** Only genuinely optional subsystems may degrade, and they
  **report `degraded`** in readiness (§6) rather than silently continuing.
- **INV-STARTUP-3:** No broad `except Exception` masks a precondition. Startup
  failures are explicit, logged with the precise cause, and exit non-zero.

---

## 5. Rate limiting (M1 remediation)

**INV-RATE-1:** Rate limiting uses a **shared store** (Redis or equivalent),
keyed by identity/org, consistent across all replicas (kills M1's per-process
in-memory `defaultdict`). Limits are correct under horizontal scale and survive
restarts. Limits are configurable per environment and per route class.

---

## 6. Observability & health (M7 remediation)

- **INV-HEALTH-1:** Two **distinct** probes (kills M7's table-existence check):
  - **`/live`** — process is up (no dependencies checked).
  - **`/ready`** — DB at expected head, required dependencies reachable,
    required types seeded, no failed hard precondition. Degraded optional
    subsystems are reported but may still be `ready` if policy allows.
- **Structured logging:** every log line is JSON with `request_id`,
  `organization_id` (when resolved), `actor_id`, and event context. No secrets or
  full tokens in logs (M2 also forbids tokens in URLs that would land here).
- **Audit:** every state change emits an Event (doc 06 §6); every authorization
  emits a `policy_decision` Event (doc 05 §4). These are queryable, immutable.
- **Metrics:** request rate/latency/error, authz allow/deny counts, queue depth,
  lease/expire/retry/DLQ counts, worker health, migration head. Alert
  thresholds are defined for each SLO.
- **Tracing:** `request_id`/`correlation_id` propagate control-plane → lease API
  → worker → completion so one workflow run is traceable end to end.

---

## 7. CI gates (M4 remediation)

XIOPATH CI ran `compileall` + an import smoke test over fabricated-table tests
(M4) — green CI proved nothing about schema, isolation, or authz. XIOSYNC CI is a
set of **blocking** gates; merge is impossible if any fail:

1. **Lint & type** — Python type-check (strict), TS strict, format check, and an
   **architecture-rule check** (no cross-layer imports, no raw table access
   outside repositories, no banned aliases — doc 04 §7).
2. **Migration chain** — from empty DB: `upgrade → downgrade → upgrade` clean
   (doc 06 INV-MIG-3); autogenerate diff must be empty (no model↔migration
   drift); single head enforced.
3. **Unit** — domain invariants (doc 03) with no infrastructure.
4. **Integration** — services against a **migrated** PostgreSQL (no fabricated
   tables — doc 06 §10 / H2).
5. **Security-negative suite** — the doc 05 §8 threat tests: cross-tenant read/
   write MUST fail, unauthorized capability MUST fail, revoked session MUST fail,
   refresh reuse MUST revoke, signup MUST NOT yield elevated role, CORS
   non-allowlisted origin MUST fail, plugin sandbox escape MUST fail.
6. **Contract** — generated OpenAPI diff; breaking change without a version bump
   blocks; frontend client regenerated and consistent.
7. **Frontend** — component/behavior tests, axe a11y (doc 08 §7), Web Vitals
   budgets (doc 08 §8).
8. **Container smoke** — build image, run migration job + API against ephemeral
   Postgres/Redis, hit `/ready`, run a minimal end-to-end workflow.
9. **Coverage gate** — a defined threshold on `domain/`, `services/`, and the
   security suite; a drop blocks merge.
10. **Secret scan** — no secrets in the diff or history (retain the intent of
    `purge_git_secrets.sh` as a preventive gate, not a cleanup afterthought).

**INV-CI-1:** A change is not mergeable until all applicable gates pass. Green
compile/type-check alone is **never** sufficient (doc 01 §4.6).

---

## 8. Containers & orchestration

- One production Dockerfile per deployable (API, worker, migration job), minimal
  base, non-root user, read-only root filesystem where possible.
- **INV-CONTAINER-1:** No secrets, no `.vault_key`, no `secrets.json` baked into
  images or mounted from app-writable disk (kills H9). Secrets are injected from
  the managed backend at runtime.
- k8s/compose manifests reference the managed DB (`DATABASE_URL` → Postgres) and
  shared Redis; **no SQLite paths** in any manifest (kills C6's
  `DATABASE_PATH: memory.db` config). The migration job is a separate
  Job/init-step, not the API container's entrypoint.
- Resource requests/limits, liveness=`/live`, readiness=`/ready`, and a
  `PodDisruptionBudget` for the API.

---

## 9. Backup, DR & retention

- **INV-DR-1:** Automated, tested PostgreSQL backups (PITR where available) with
  a documented, **rehearsed** restore. An untested backup does not count.
- Defined RPO/RTO targets; restore drills run on a schedule and recorded.
- Event/audit retention and redaction are explicit, audited, privileged
  operations (doc 06 §6), never ad-hoc.
- The vector store and Redis have their own documented durability/rebuild
  expectations (Redis rate-limit/lease state is reconstructable; it is not the
  source of truth).

---

## 10. Rollout & rollback

- **INV-ROLLOUT-1:** Rollout is progressive (canary → full) with automated
  rollback on SLO/error-budget breach.
- **INV-ROLLOUT-2:** Because migrations are expand→contract (doc 06 §3), the
  previous release runs against the new schema, so an API rollback never requires
  a schema rollback under normal operation.
- Feature flags gate risky features (autonomy, isolation subsystem) so they can
  be disabled in production without a redeploy (doc 01 §6 non-goals stay off by
  default).

---

## 11. Ops anti-patterns (forbidden)

- Wildcard/regex CORS origin with credentials. **(C4)**
- Migration in the API process or per replica; any SQLite target in a manifest. **(C6)**
- Per-process in-memory rate limiting in a multi-replica deployment. **(M1)**
- CI that proves only syntax/imports, or tests over fabricated tables. **(M4/H2)**
- Broad `except Exception` masking a startup precondition. **(M5)**
- Health check that only verifies table existence. **(M7)**
- Secrets/keys baked into images or on app-writable disk. **(H9)**
- Embedded secret defaults; missing secrets that don't fail startup. **(L4)**
- More than one lockfile/package manager per ecosystem. **(L5)**

Any of these is an operational regression to be reverted.
