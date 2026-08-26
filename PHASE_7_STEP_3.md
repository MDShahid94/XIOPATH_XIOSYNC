# Phase 7 Step 3 — Origin Allowlist CORS (G-OPS-1 / C4)

## Gate Closed: G-OPS-1

**Invariant**: INV-CORS-1 (Blueprint doc 09 §2)  
**Bug closed**: C4 — XIOPATH used `allow_origin_regex=".*"` + `allow_credentials=True` (critical security bug)

## Files Changed

| File | Change |
|------|--------|
| `xiosync/api/middleware/cors.py` | NEW — `StrictCORSMiddleware`, `validate_origins()` |
| `xiosync/platform/config.py` | ADD `cors_allowed_origins: list[str]`, `CORS_ALLOWED_ORIGINS` env key, staging/prod validator |
| `xiosync/api/app.py` | ADD `cors_origins` param to `create_app()`; wire as outermost middleware; pass from `create_production_app()` |
| `tests/unit/test_cors.py` | NEW — 8 tests covering G-OPS-1 |

## Implementation

- `validate_origins(origins, environment)` — raises `ConfigError` if `"*"` present (any env) or list empty in `staging`/`production`
- `StrictCORSMiddleware(app, allowed_origins=...)` — subclasses Starlette's `CORSMiddleware` with explicit list, `allow_credentials=True`, no regex
- `CORS_ALLOWED_ORIGINS` env var — comma-separated, parsed at `load_config()` time
- `StrictCORSMiddleware` added **outermost** in the middleware stack so OPTIONS preflight never hits authentication

## Verification Commands

```bash
uv run ruff check .
uv run mypy xiosync/
uv run pytest tests/unit/test_cors.py -v
```

## Test Results

```
tests/unit/test_cors.py::test_wildcard_origin_rejected_at_config PASSED
tests/unit/test_cors.py::test_empty_origins_rejected_in_staging PASSED
tests/unit/test_cors.py::test_empty_origins_rejected_in_production PASSED
tests/unit/test_cors.py::test_empty_origins_allowed_in_dev PASSED
tests/unit/test_cors.py::test_empty_origins_allowed_in_ci PASSED
tests/unit/test_cors.py::test_allowed_origin_gets_cors_headers PASSED
tests/unit/test_cors.py::test_non_allowlisted_origin_rejected PASSED
tests/unit/test_cors.py::test_options_preflight_allowed_origin PASSED

8 passed in 0.43s
```

ruff: All checks passed  
mypy: No issues found in 68 source files
