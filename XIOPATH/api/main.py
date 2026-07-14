from fastapi import FastAPI
from contextlib import asynccontextmanager

from core.database import DatabaseManager
from core.memory_manager import MemoryManager, ServerMemoryAPI
from core.secret_manager import SecretManager
from api.routers import memory, agent, vault, dlq, auth, seed, health, session, schedule, ws, admin
from api.routers import agents_v2, actors_v2, metrics, workflows, marketplace
from api.routers import types as types_router
from api.routers import orgs as orgs_router
from api.routers import workflows_v2 as workflows_v2_router
from api.routers import plugins as plugins_router, actions as actions_router
from api.routers import sync as sync_router

# S.3: Structured logging (replaces logging.basicConfig)
from core.structured_logging import configure_logging, get_logger
configure_logging()
logger = get_logger("API_MAIN")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    
    # DB Fix: Auto-apply Alembic migrations so all tables exist on fresh installs.
    try:
        from alembic.config import Config
        from alembic import command
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        
        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        head = script.get_current_head()
        
        engine = create_engine("sqlite:///data/xiopath.db")
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
        engine.dispose()
        
        if current != head:
            command.upgrade(alembic_cfg, "head")
            logger.info(f"Alembic migrations applied: {current} → {head}")
        else:
            logger.info(f"Alembic: already at head ({head})")
    except Exception as e:
        logger.warning(f"Alembic migration skipped (may not be configured): {e}")
    
    # Single unified database: data/xiopath.db
    from pathlib import Path
    db = DatabaseManager(Path("data/xiopath.db"))
    
    # Start the system memory manager (uses unified DB)
    system_memory = MemoryManager(session_id="system_api", db=db, start_sync=True)
    chroma_client = system_memory.chroma_client
    server_api = ServerMemoryAPI(db)
    secret_manager = SecretManager()
    
    # Store heavy singletons globally
    app.state.db = db
    app.state.chroma_client = chroma_client
    app.state.server_api = server_api
    app.state.system_memory = system_memory
    app.state.secret_manager = secret_manager
    
    # O.5: Initialize ontology layer and seed foundational actors
    from core.ontology_ops import OntologyManager
    ontology = OntologyManager(db)
    try:
        ontology.seed_initial_actors()
    except Exception as e:
        logger.warning(f"Ontology seed skipped (tables may not exist yet): {e}")
    app.state.ontology = ontology
    
    # P.2: Initialize Type Registry and seed builtin types
    from core.type_registry import TypeRegistry
    type_registry = TypeRegistry(db)
    try:
        type_registry.seed_builtins()
    except Exception as e:
        logger.warning(f"TypeRegistry seed skipped (table may not exist yet): {e}")
    app.state.type_registry = type_registry
    
    # P.5: Initialize Knowledge Manager
    from core.knowledge_manager import KnowledgeManager
    knowledge_manager = KnowledgeManager(db, type_registry=type_registry)
    app.state.knowledge_manager = knowledge_manager
    
    # P.6: Initialize Workflow Manager
    from core.workflow_manager import WorkflowManager
    workflow_manager = WorkflowManager(db, knowledge_manager=knowledge_manager)
    app.state.workflow_manager = workflow_manager
    
    # W.4: Initialize Workflow Orchestrator
    from core.gemini_engine import GeminiEngine
    from core.workflow_orchestrator import WorkflowOrchestrator
    try:
        llm = GeminiEngine()
        from core.agent_loop import AgentLoop
        workflow_agent_loop = AgentLoop(
            session_id="api_workflow_agent", llm=llm, headless_mode="true"
        )
        workflow_orchestrator = WorkflowOrchestrator(workflow_agent_loop)
        app.state.workflow_orchestrator = workflow_orchestrator
        app.state.llm = llm
        logger.info("Workflow orchestrator initialized.")
    except Exception as e:
        logger.warning(f"Workflow orchestrator init skipped: {e}")
        app.state.workflow_orchestrator = None
        app.state.llm = None

    # MWA: Lazy — initialized on first /workflows/goal request (needs browser)
    app.state.master_workflow_agent = None
    
    # Store the WS connection manager for broadcasting from other routers
    app.state.ws_manager = ws.manager
    
    logger.info("FastAPI Backend started successfully.")
    yield
    # Shutdown
    logger.info("Shutting down FastAPI Backend...")
    if system_memory.sync_worker:
        system_memory.sync_worker.stop()

from fastapi.middleware.cors import CORSMiddleware

OPENAPI_TAGS = [
    {
        "name": "Actors v2",
        "description": "**Core entity management.** Create, read, update, and delete actors (humans, AI agents, compute nodes). Manage edges (relationships), operations, and capabilities.",
    },
    {
        "name": "Types v2",
        "description": "**Dynamic type registry.** Register, validate, and list types across 10 categories (actor_type, edge_type, action_type, etc.). Supports org-scoped custom types.",
    },
    {
        "name": "Organizations v2",
        "description": "**Multi-tenant organizations.** Create orgs, manage members with role-based access (owner/admin/member/viewer), and configure plan limits.",
    },
    {
        "name": "Workflows v2",
        "description": "**Persistent workflow engine.** Define versioned workflows, execute with full lifecycle (start/pause/resume/cancel/complete), fork workflows, and track analytics.",
    },
    {
        "name": "Marketplace",
        "description": "**Universal marketplace.** Publish and install any entity type (workflows, knowledge, bundles, environments). Includes ratings, reviews, and version management.",
    },
    {
        "name": "auth",
        "description": "**Authentication.** Register, login, and manage JWT tokens. Supports dual-table auth (auth_identities + actors) with account lockout protection.",
    },
    {
        "name": "Health",
        "description": "**System health.** Validates all 26 database tables, reports migration status, and checks service availability.",
    },
    {
        "name": "Memory",
        "description": "**Action memory management.** Tiered memory system (5-tier cascading fallback) for storing and retrieving browser actions with Bayesian scoring.",
    },
    {
        "name": "Workflows v1",
        "description": "**Legacy workflow execution.** Real-time workflow orchestration via the browser agent loop.",
    },
    {
        "name": "Vault",
        "description": "**Secret management.** Securely store and retrieve API keys, credentials, and sensitive configuration.",
    },
    {
        "name": "Admin",
        "description": "**Admin operations.** Worker management, DLQ triage, consensus voting, and system analytics.",
    },
]

app = FastAPI(
    title="XIOPATH API",
    description="""
# XIOPATH v5.0 — Universal Action Intelligence Platform

Enterprise-grade platform for defining, executing, and sharing automated actions across domains.

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Actor** | Any entity in the system (human, AI, compute) |
| **Knowledge Node** | A stored action with Bayesian-scored confidence |
| **Workflow** | A versioned, shareable sequence of steps |
| **Organization** | Multi-tenant group with role-based access |
| **Execution Policy** | Sandbox rules governing what a workflow can do |

## API Versioning

- **`/api/v1/*`** — Legacy endpoints (memory, vault, workflows, marketplace)
- **`/api/v2/*`** — v5.0 endpoints (actors, types, orgs, workflows)

## Authentication

All protected endpoints require a JWT Bearer token via the `Authorization` header:
```
Authorization: Bearer <token>
```
    """,
    version="5.0.0",
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "XIOPATH Platform",
        "url": "https://github.com/XIOPATH",
    },
    license_info={
        "name": "Proprietary",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# S.2: Tightened CORS — explicit methods and headers instead of wildcards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "chrome-extension://*"],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# S.2: Security headers (CSP, X-Frame-Options, etc.)
from api.middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# S.1: Request size limit (5 MB default)
from api.middleware.request_size import RequestSizeLimitMiddleware
app.add_middleware(RequestSizeLimitMiddleware)

# S.3: Request context (X-Request-ID correlation)
from api.middleware.request_context import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)

# S.4: Metrics collector (Prometheus counters/histograms)
from api.middleware.metrics_collector import MetricsMiddleware
app.add_middleware(MetricsMiddleware)

# C1 Fix: Register rate limiter (was defined but never wired)
from api.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# M.6: Multi-tenancy tenant scope
from api.middleware.tenant_scope import TenantScopeMiddleware
app.add_middleware(TenantScopeMiddleware)

# Include Routers
app.include_router(memory.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(vault.router, prefix="/api/v1")
app.include_router(dlq.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(seed.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(session.router, prefix="/api/v1")
app.include_router(schedule.router, prefix="/api/v1")
app.include_router(ws.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")  # C6 Fix: Wire admin router

# API v2 — Ontology endpoints (v5.0: Actors)
app.include_router(actors_v2.router, prefix="/api/v2")
# Backward-compat: keep /agents route alive via legacy router
app.include_router(agents_v2.router, prefix="/api/v2")

# P.2: Type Registry endpoints
app.include_router(types_router.router, prefix="/api/v2")

# P.4: Organization endpoints
app.include_router(orgs_router.router, prefix="/api/v2")

# P.6: Workflows v2 endpoints
app.include_router(workflows_v2_router.router, prefix="/api/v2")

# S.4: Prometheus metrics endpoint
app.include_router(metrics.router)

# W.4: Workflow management endpoints
app.include_router(workflows.router, prefix="/api/v1")

# M.2: Marketplace endpoints
app.include_router(marketplace.router, prefix="/api/v1")

# E.1: Plugin registry endpoints
app.include_router(plugins_router.router, prefix="/api/v1")

# E.2: Custom action builder endpoints
app.include_router(actions_router.router, prefix="/api/v1")

# DB Fix: Sync push/pull endpoints
app.include_router(sync_router.router, prefix="/api/v1")

@app.get("/", tags=["Root"])
async def root():
    """Developer landing page with API overview and documentation links."""
    return {
        "platform": "XIOPATH",
        "version": "5.0.0",
        "description": "Universal Action Intelligence Platform",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json",
        },
        "api": {
            "v2": {
                "actors": "/api/v2/actors",
                "types": "/api/v2/types",
                "organizations": "/api/v2/orgs",
                "workflows": "/api/v2/workflows",
            },
            "v1": {
                "auth": "/api/v1/auth",
                "health": "/api/v1/health",
                "memory": "/api/v1/memory",
                "marketplace": "/api/v1/marketplace",
                "vault": "/api/v1/vault",
                "workflows": "/api/v1/workflows",
            },
        },
        "status": "operational",
    }
