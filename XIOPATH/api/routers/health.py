"""
XIOPATH — Health Check Router
================================
Provides basic and deep health check endpoints for monitoring.
"""
from fastapi import APIRouter, Request
import time

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

router = APIRouter(prefix="/health", tags=["Health"])

_start_time = time.time()


@router.get("")
async def health_check():
    """Basic health check — returns OK if the API is responding."""
    return {
        "status": "healthy",
        "service": "xiopath-api",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/deep")
async def deep_health_check(request: Request):
    """
    Deep health check — validates connectivity to all subsystems:
    - Database (SQLite/PostgreSQL)
    - Vector Store (ChromaDB)
    - Secret Manager
    """
    checks = {}

    # Database check (with latency)
    try:
        db = request.app.state.db
        if db and hasattr(db, 'SessionLocal'):
            from sqlalchemy import text
            db_start = time.perf_counter()
            with db.SessionLocal() as session:
                session.execute(text("SELECT 1"))
            db_latency_ms = round((time.perf_counter() - db_start) * 1000, 2)
            
            # DB Fix: Verify all expected tables exist
            expected_tables = {
                "memory_nodes", "client_votes", "client_vote_counts", "users", "scheduled_jobs",
                "marketplace_listings", "marketplace_reviews",
                "actors", "operations", "actor_edges", "capabilities",
                "capability_grants", "events", "type_registry", "auth_identities",
                "connections", "actor_profiles", "bundles", "actor_versions",
                "organizations", "org_memberships", "knowledge_nodes",
                "workflows", "workflow_executions", "execution_policies",
            }
            existing = set()
            try:
                rows = session.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )).fetchall()
                existing = {r[0] for r in rows}
            except Exception:
                pass
            missing = expected_tables - existing
            
            checks["database"] = {
                "status": "healthy" if not missing else "degraded",
                "type": "sqlite",
                "latency_ms": db_latency_ms,
                "tables_verified": len(expected_tables - missing),
                "tables_expected": len(expected_tables),
            }
            if missing:
                checks["database"]["missing_tables"] = sorted(missing)
        else:
            checks["database"] = {"status": "not_configured"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    # ChromaDB check
    try:
        chroma = request.app.state.chroma_client
        if chroma:
            chroma.heartbeat()
            checks["vector_store"] = {"status": "healthy", "type": "chromadb"}
        else:
            checks["vector_store"] = {"status": "not_configured"}
    except Exception as e:
        checks["vector_store"] = {"status": "unhealthy", "error": str(e)}

    # Secret Manager check
    try:
        sm = request.app.state.secret_manager
        if sm:
            sm.list_keys()  # Simple read test
            checks["secret_manager"] = {"status": "healthy"}
        else:
            checks["secret_manager"] = {"status": "not_configured"}
    except Exception as e:
        checks["secret_manager"] = {"status": "unhealthy", "error": str(e)}

    # Worker connections check
    try:
        ws_manager = getattr(request.app.state, "ws_manager", None)
        if ws_manager is not None:
            count = len(getattr(ws_manager, "active_connections", []))
            checks["workers"] = {"status": "healthy", "connected": count}
        else:
            checks["workers"] = {"status": "not_configured"}
    except Exception as e:
        checks["workers"] = {"status": "unhealthy", "error": str(e)}

    # Memory usage check (psutil)
    try:
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            checks["memory"] = {
                "status": "healthy" if mem.percent < 90 else "degraded",
                "used_percent": mem.percent,
                "available_mb": round(mem.available / (1024 * 1024), 1),
            }
        else:
            checks["memory"] = {"status": "not_configured", "reason": "psutil not installed"}
    except Exception as e:
        checks["memory"] = {"status": "unhealthy", "error": str(e)}

    # Overall status: healthy → degraded → unhealthy
    statuses = [c.get("status") for c in checks.values()]
    if any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    elif any(s == "degraded" for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "service": "xiopath-api",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "checks": checks,
    }
