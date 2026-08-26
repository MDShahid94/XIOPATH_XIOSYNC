# Phase 7 Step 1: Application Lifecycle & Readiness Head-gates

## Overview

This document describes the implementation of Phase 7 Step 1, which hardens the backend application for production deployability through strict startup validation and readiness management.

**Normative references:**
- Phase 7 Step 1: Application Lifecycle & Readiness Head-gates
  - M5: Fail-fast startup with strict config validation
  - M7: Distinct /live and /ready endpoints  
  - C6: Migration-as-deploy-step with readiness head-gate

**Status:** ✅ Complete - All tests passing, code linted, types verified

## Implementation Summary

### 1. Health Check Module (`xiosync/core/health.py`)

**Purpose:** Core health check logic for verifying application readiness.

**Key Functions:**

- `verify_database_connection(engine)`: Tests database connectivity
- `get_alembic_head_revision(alembic_dir)`: Reads the head migration revision from the Alembic script directory
- `get_database_current_revision(engine)`: Queries the database to get the currently applied migration revision
- `verify_migrations_at_head(engine, alembic_dir)`: **C6 enforcement** - Verifies database migrations are at the exact head revision, fails fast if not
- `check_readiness(engine, alembic_dir)`: Returns a `ReadinessState` indicating current application readiness

**Key Exceptions:**

- `DatabaseConnectionError`: Raised when database operations fail
- `MigrationNotAtHeadError`: Raised when migrations are not at head (forces startup to fail)

### 2. Health Check Endpoints (`xiosync/api/routers/health.py`)

**Purpose:** HTTP endpoints for orchestrators to probe application health.

**Endpoints:**

#### `/live` (GET)
- **Purpose:** Liveness probe - indicates the process is running
- **Response:** Always returns 200 with `{"status": "alive", "message": "Process is running"}`
- **Use Case:** Container orchestrators use this to detect process crashes
- **Authentication:** Not required
- **Path:** Root path (not under `/api/v1`)

#### `/ready` (GET)
- **Purpose:** Readiness probe - indicates the application is fully capable of serving requests
- **Response on Ready:** 200 with `{"status": "ready", "message": "Fully operational"}`
- **Response on Not Ready:** 503 with error detail explaining why (e.g., migration not at head)
- **Checks:** Database connectivity + migrations at head revision
- **Use Case:** Container orchestrators use this to route traffic only to ready instances
- **Authentication:** Not required
- **Path:** Root path (not under `/api/v1`)

### 3. Fail-Fast Startup (`xiosync/api/app.py`)

**Purpose:** Enforce strict validation at startup before opening ports.

**Function:** `create_production_app()`

**Startup Validation Order (M5):**

1. **Config Loading & Validation**: `load_config()` validates all required environment variables and configuration (INV-CFG-1/2/3)
   - Fails immediately on missing `XIOSYNC_ENVIRONMENT`, `DATABASE_URL`, `XIOSYNC_AUTH_SECRET`
   - Validates log level is valid

2. **Logging Configuration**: `configure_logging()` sets up logging with validated level

3. **Database Engine Creation**: `create_database_engine()` creates SQLAlchemy engine
   - Validates database URL targets PostgreSQL + psycopg (C6)
   - Establishes initial connection to verify reachability

4. **Migration Verification**: `verify_migrations_at_head()` checks migrations are at head (C6, INV-STARTUP-1)
   - **Enforces:** Database must be at exact head revision or startup fails
   - This ensures deployments cannot proceed without migrations applied

5. **Service Wiring**: Creates `SessionService` and returns fully configured app

**Failure Behavior:** If any check fails, startup raises an exception and process exits non-zero before opening ports (INV-STARTUP-1). This prevents degraded service from starting.

**Logging:** Critical error messages are logged for each failure to aid debugging.

## Comprehensive Test Suite

**Total Tests:** 44 ✅ passing

### Unit Tests: Health Check Module (`test_health.py` - 18 tests)

- Database connection verification (success/failure cases)
- Current revision querying (no table, multiple versions, connection errors)
- Alembic head revision reading (success, invalid directory)
- Migration head verification (at head, not applied, behind, database errors)
- Readiness state checking (ready/not ready scenarios)
- Readiness state immutability
- Integration tests with real SQLite database

### Unit Tests: Health Endpoints (`test_health_endpoints.py` - 17 tests)

**Liveness Probe Tests:**
- Always returns 200
- Returns proper JSON structure
- Cannot fail (resilience test)
- Correct content-type

**Readiness Probe Tests:**
- Returns 200 when ready
- Returns 503 when not ready
- Includes error details on failure
- Calls check_readiness with engine
- Correct content-type

**Realistic Scenarios:**
- Migration failure scenario
- Database connection failure scenario
- All checks passing scenario

**Endpoint Routing:**
- Endpoints exist at root path (not `/api/v1`)
- No authentication required

### Unit Tests: App Startup (`test_app_startup.py` - 9 tests)

**Fail-Fast Validation:**
- Fails on missing config
- Fails on invalid database URL
- Fails on migrations not at head (C6)
- Succeeds when all checks pass

**Startup Order:**
- Config validated before DB connection
- DB verified before migration check

**Startup Logging:**
- Logs environment
- Logs success message
- Logs failure reasons

## Code Quality

**Linting:** ✅ All checks passed with ruff
- No unused imports
- No style violations
- No security issues detected

**Type Checking:** ✅ All checks passed with mypy (strict mode)
- No type errors
- Full type annotations on all functions

**Architecture Compliance:**
- `xiosync.core.health` is domain-agnostic (no FastAPI/SQLAlchemy framework specifics except Engine)
- `xiosync.api.routers.health` properly layers health checks (uses `xiosync.core.health`)
- `xiosync.api.app` orchestrates startup with proper error handling

## Deployment Checklist

When deploying to production:

1. ✅ Environment variables set correctly:
   - `XIOSYNC_ENVIRONMENT` = `production`
   - `DATABASE_URL` = PostgreSQL connection string
   - `XIOSYNC_AUTH_SECRET` = minimum 32-character secret (e.g., `openssl rand -base64 48`)
   - `XIOSYNC_LOG_LEVEL` = `INFO` or `WARNING` (optional, defaults to `INFO`)

2. ✅ Database migrations applied:
   - `alembic upgrade head` must run as a deploy step
   - Application refuses to start if migrations are not at head (C6)

3. ✅ Health checks configured in orchestrator:
   - Liveness probe: `GET /live`
   - Readiness probe: `GET /ready`
   - Container should not receive traffic until `/ready` returns 200

4. ✅ Error handling:
   - If application doesn't start, check logs for:
     - Missing environment variables (reported in config phase)
     - Database connection errors (reported in engine phase)
     - Migration verification failures (reported with specific revision mismatch)

## Architecture Decisions

### Why Distinct `/live` and `/ready`?

- **`/live`** indicates the process is alive but may not be ready (e.g., during startup, migrations running)
- **`/ready`** indicates full capability and readiness to serve traffic
- This allows orchestrators to:
  - Keep the container running during migrations (liveness passes)
  - Hold traffic until ready (readiness passes)

### Why Fail-Fast on Migrations?

- Migration drift is a serious production issue that indicates deployment mismatch
- Early failure prevents partial startup in degraded state
- Makes the deployment process auditable: either migrations succeeded (app started) or failed (app did not start)

### Why Check at Startup vs. Request-Time?

- Startup checks: Caught immediately before opening ports, prevents bad deployments
- Request-time checks: `/ready` endpoint checks again, allowing graceful degradation if migrations are later reverted (unlikely but possible)

## Files Changed

### Core Implementation
- `xiosync/core/health.py` - New module for health checks
- `xiosync/api/routers/health.py` - New router for HTTP endpoints
- `xiosync/api/app.py` - Updated to integrate health checks and enforce fail-fast startup

### Tests
- `tests/unit/test_health.py` - 18 comprehensive unit tests
- `tests/unit/test_health_endpoints.py` - 17 endpoint tests
- `tests/unit/test_app_startup.py` - 9 startup validation tests

## Next Steps (Phase 7 Step 2+)

With Phase 7 Step 1 complete:
- Application now fails fast on startup if requirements not met
- Orchestrators can reliably use `/live` and `/ready` for deployment
- Database migrations are guaranteed to be at head for running instances

Future phases will add:
- Metrics collection from readiness checks
- Graceful shutdown procedures
- Deployment coordination between multiple instances
