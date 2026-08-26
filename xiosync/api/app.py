"""FastAPI composition root for the XIOSYNC control plane.

Normative references:
- Phase 7 Step 1: Application Lifecycle & Readiness Head-gates
  - M5: Fail-fast startup with strict config validation
  - M7: Distinct /live and /ready endpoints
  - C6: Migration-as-deploy-step with readiness head-gate
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from starlette.types import Receive, Scope, Send

from xiosync.api.middleware import (
    DEFAULT_MAX_BODY_BYTES,
    AuthenticationMiddleware,
    BodySizeLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from xiosync.api.routers.auth import router as auth_router
from xiosync.api.routers.dlq import router as dlq_router
from xiosync.api.routers.execution import router as execution_router
from xiosync.api.routers.health import router as health_router
from xiosync.api.routers.plugins import router as plugins_router
from xiosync.core.health import verify_migrations_at_head
from xiosync.persistence.database import create_database_engine
from xiosync.persistence.identity import IdentityRepository
from xiosync.platform.clock import Clock, SystemClock
from xiosync.platform.config import ConfigError, load_config
from xiosync.platform.telemetry import configure_logging
from xiosync.services.identity import SessionService

logger = logging.getLogger(__name__)


def create_app(
    *,
    session_service: SessionService,
    engine: Engine,
    clock: Clock,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> FastAPI:
    """Compose an app from explicit dependencies (the contract-test seam).

    Health check endpoints are registered at the root path (not under /api/v1)
    so orchestrators can easily probe them without authentication.
    """
    application = FastAPI(title="XIOSYNC API", version="1.0.0")
    application.state.session_service = session_service
    application.state.engine = engine
    application.state.clock = clock

    # Health check endpoints (no auth required, no /api/v1 prefix)
    application.include_router(health_router)

    # API routers under /api/v1 with full authentication and middleware
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(execution_router, prefix="/api/v1")
    application.include_router(dlq_router, prefix="/api/v1")
    application.include_router(plugins_router, prefix="/api/v1")

    @application.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "https://xiosync.dev/problems/invalid_request",
                "title": "Invalid request",
                "status": 422,
                "code": "invalid_request",
                "request_id": request.state.request_id,
            },
        )

    # Starlette wraps each newly-added middleware around the previous stack.
    # Add in reverse so the effective order is request-id -> security -> size -> auth.
    application.add_middleware(
        AuthenticationMiddleware,
        session_service=session_service,
        engine=engine,
        clock=clock,
    )
    application.add_middleware(BodySizeLimitMiddleware, max_body_bytes=max_body_bytes)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestIDMiddleware)
    return application


def create_production_app() -> FastAPI:
    """Load validated configuration and wire production dependencies fail-fast (M5).

    Startup enforces strict validation:
    1. All environment variables must be present and valid (INV-CFG-1/2/3)
    2. Database must be connectable
    3. Database migrations must be at head revision (C6)

    If any check fails, the process exits non-zero before opening ports (INV-STARTUP-1).
    """
    # Step 1: Load and validate configuration (INV-CFG-1/2/3, INV-STARTUP-1)
    try:
        config = load_config()
    except ConfigError as exc:
        logger.critical(f"Configuration validation failed: {exc}")
        raise

    # Step 2: Configure logging with validated level
    configure_logging(config.log_level)
    logger.info(f"Starting XIOSYNC in {config.environment} environment")

    # Step 3: Create database engine (will fail fast if URL is invalid)
    try:
        engine = create_database_engine(config.database_url)
    except Exception as exc:
        logger.critical(f"Failed to create database engine: {exc}")
        raise

    # Step 4: Verify migrations are at head (C6, INV-STARTUP-1)
    # This MUST succeed before the app opens ports. If migrations are not applied,
    # startup fails immediately rather than starting a degraded service.
    try:
        verify_migrations_at_head(engine)
        logger.info("Database migrations verified at head")
    except Exception as exc:
        logger.critical(f"Migration verification failed (C6): {exc}")
        raise

    # Step 5: Wire remaining services
    service = SessionService(IdentityRepository(engine), config.auth_secret)
    logger.info("All startup checks passed; application ready")
    return create_app(session_service=service, engine=engine, clock=SystemClock())


class _LazyProductionApp:
    """Delay environment loading until ASGI startup while retaining fail-fast boot."""

    _application: FastAPI | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._application is None:
            self._application = create_production_app()
        await self._application(scope, receive, send)


app: Any = _LazyProductionApp()
