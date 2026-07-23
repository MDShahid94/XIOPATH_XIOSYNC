"""FastAPI composition root for the XIOSYNC control plane."""

from __future__ import annotations

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
from xiosync.api.routers.plugins import router as plugins_router
from xiosync.persistence.database import create_database_engine
from xiosync.persistence.identity import IdentityRepository
from xiosync.platform.clock import Clock, SystemClock
from xiosync.platform.config import load_config
from xiosync.platform.telemetry import configure_logging
from xiosync.services.identity import SessionService


def create_app(
    *,
    session_service: SessionService,
    engine: Engine,
    clock: Clock,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> FastAPI:
    """Compose an app from explicit dependencies (the contract-test seam)."""
    application = FastAPI(title="XIOSYNC API", version="1.0.0")
    application.state.session_service = session_service
    application.state.engine = engine
    application.state.clock = clock

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
    """Load validated configuration and wire production dependencies fail-fast."""
    config = load_config()
    configure_logging(config.log_level)
    engine = create_database_engine(config.database_url)
    service = SessionService(IdentityRepository(engine), config.auth_secret)
    return create_app(session_service=service, engine=engine, clock=SystemClock())


class _LazyProductionApp:
    """Delay environment loading until ASGI startup while retaining fail-fast boot."""

    _application: FastAPI | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._application is None:
            self._application = create_production_app()
        await self._application(scope, receive, send)


app: Any = _LazyProductionApp()
