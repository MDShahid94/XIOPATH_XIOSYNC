"""Execution-plane API endpoints — task lease, heartbeat, and completion.

These are the **only** channel between the execution plane (workers) and the
control-plane database (INV-EXEC-1, doc 07 §1). Workers never read or write
the control-plane DB directly; they only call these three endpoints:

* ``POST /execution/tasks/{task_id}/lease``      — atomically acquire a lease
* ``POST /execution/tasks/{task_id}/heartbeat``  — extend an active lease
* ``POST /execution/tasks/{task_id}/complete``   — deliver a result and close

INV-EXEC-2: task delivery is at-least-once; a duplicate completion (idempotent
``task_id`` key) returns ``duplicate=true`` in the response body rather than
raising, so the calling worker can safely retry without risk of double-write.

INV-EXEC-3 (stub, Phase 4 Step 3): the result on completion is accepted as
untrusted input and recorded on the task row; full output-schema validation and
re-authorization are deferred to the scheduler-side result-validation step that
is the subject of a later step.

The router obtains the authenticated ``OrgContext`` and the already-opened
``org_scoped_session`` from ``request.state``, following the same pattern as
the auth router: the ``AuthenticationMiddleware`` wires both onto scope state
before any handler runs, so every endpoint here is implicitly tenant-scoped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as OrmSession

from xiosync.domain.context import OrgContext
from xiosync.platform.task_credentials import (
    load_task_credential_signing_key,
    mint_task_credential,
)
from xiosync.services.workflows import (
    InactiveLeaseError,
    NonCompletableError,
    TaskNotFoundError,
    UnleaseableError,
    WorkflowService,
)

router = APIRouter(prefix="/execution", tags=["execution"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _context(request: Request) -> OrgContext:
    return cast(OrgContext, request.state.org_context)


def _session(request: Request) -> OrmSession:
    return cast(OrmSession, request.state.org_session)


def _service(request: Request) -> WorkflowService:
    return WorkflowService(_session(request))


def _problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://xiosync.dev/problems/{code}",
        "title": title,
        "status": status,
        "code": code,
        "request_id": request.state.request_id,
    }
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status, media_type="application/problem+json", content=body)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class LeaseRequest(StrictModel):
    """Body for ``POST /execution/tasks/{task_id}/lease`` (INV-EXEC-1)."""

    leased_by: uuid.UUID = Field(
        description="The worker actor ID that is acquiring this lease."
    )
    duration_seconds: int | None = Field(
        default=None,
        ge=1,
        le=3600,
        description="Desired lease duration in seconds. Defaults to the service default (300s).",
    )


class LeaseResponse(StrictModel):
    task_id: uuid.UUID
    lease_id: uuid.UUID
    leased_by: uuid.UUID
    lease_expires_at: str  # ISO-8601 UTC
    attempts: int
    state: str
    # INV-TASK-SEC-1/2: a scoped, single-use credential minted at lease time,
    # bound to (task_id, worker_id) and expiring with the lease. The worker
    # presents this — never the raw stored secret — to a capability that needs
    # credentials.
    task_credential: str = Field(
        description=(
            "Signed, single-use task credential bound to this (task_id, "
            "worker_id) lease and expiring with it (INV-TASK-SEC-1/2). Signed "
            "with a key distinct from the user-session JWT secret."
        )
    )
    task_credential_expires_at: str  # ISO-8601 UTC; equals the lease expiry
    scoped_capabilities: list[uuid.UUID] = Field(
        description="The capability IDs this task credential is scoped to."
    )


class HeartbeatRequest(StrictModel):
    """Body for ``POST /execution/tasks/{task_id}/heartbeat``."""

    lease_id: uuid.UUID = Field(description="The lease_id returned by the lease endpoint.")
    duration_seconds: int | None = Field(
        default=None,
        ge=1,
        le=3600,
        description="Extension duration in seconds. Defaults to the service default (300s).",
    )


class HeartbeatResponse(StrictModel):
    task_id: uuid.UUID
    lease_id: uuid.UUID
    lease_expires_at: str  # ISO-8601 UTC


class CompleteRequest(StrictModel):
    """Body for ``POST /execution/tasks/{task_id}/complete`` (INV-EXEC-2)."""

    lease_id: uuid.UUID = Field(description="The lease_id returned by the lease endpoint.")
    result: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Untrusted result payload (INV-EXEC-3); recorded on the task row. "
            "Full output-schema validation is applied by the scheduler after completion."
        ),
    )


class CompleteResponse(StrictModel):
    task_id: uuid.UUID
    state: str
    duplicate: bool = Field(
        description=(
            "True when this task was already completed; the caller should treat "
            "this as a no-op (INV-EXEC-2 idempotency)."
        )
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/tasks/{task_id}/lease",
    response_model=LeaseResponse,
    summary="Atomically acquire a task lease (INV-EXEC-1)",
)
def lease_task(
    task_id: uuid.UUID,
    payload: LeaseRequest,
    request: Request,
) -> LeaseResponse | JSONResponse:
    """Transition a ``queued`` task to ``leased`` and return the lease token.

    Only ``queued`` tasks may be leased (INV-EXEC-1). A row-level lock prevents
    two workers from racing on the same task. An already-leased or terminal task
    returns 409.
    """
    context = _context(request)
    service = _service(request)
    duration = (
        timedelta(seconds=payload.duration_seconds)
        if payload.duration_seconds is not None
        else None
    )

    try:
        task = service.lease_task(
            context,
            task_id,
            leased_by=payload.leased_by,
            duration=duration,
        )
    except TaskNotFoundError:
        return _problem(request, 404, "task_not_found", "Task not found")
    except UnleaseableError as exc:
        return _problem(
            request,
            409,
            "task_not_leaseable",
            "Task is not in a leaseable state",
            detail=f"state={exc.state!r}",
        )

    assert task.lease_id is not None  # noqa: S101 — guaranteed by lease_task on success
    assert task.leased_by is not None  # noqa: S101
    assert task.lease_expires_at is not None  # noqa: S101

    # INV-TASK-SEC-1/2: mint the scoped, single-use credential at lease time,
    # bound to (task_id, worker_id) and expiring with the lease. Signing uses
    # the worker-credential key (distinct from the user JWT secret — H7); a
    # missing key fails loudly rather than downgrading security (INV-SEC-1).
    scoped_capabilities = [task.capability_id]
    token, credential = mint_task_credential(
        load_task_credential_signing_key(),
        task_id=task.id,
        worker_id=task.leased_by,
        lease_id=task.lease_id,
        organization_id=context.organization_id,
        scoped_capabilities=scoped_capabilities,
        now=datetime.now(UTC),
        expires_at=task.lease_expires_at,
    )

    return LeaseResponse(
        task_id=task.id,
        lease_id=task.lease_id,
        leased_by=task.leased_by,
        lease_expires_at=task.lease_expires_at.isoformat(),
        attempts=task.attempts,
        state=task.state,
        task_credential=token,
        task_credential_expires_at=credential.expires_at.isoformat(),
        scoped_capabilities=list(credential.scoped_capabilities),
    )


@router.post(
    "/tasks/{task_id}/heartbeat",
    response_model=HeartbeatResponse,
    summary="Extend an active task lease",
)
def heartbeat_task(
    task_id: uuid.UUID,
    payload: HeartbeatRequest,
    request: Request,
) -> HeartbeatResponse | JSONResponse:
    """Push the lease deadline forward to prevent mid-work expiry.

    The caller must present the exact ``lease_id`` returned by the lease
    endpoint; a mismatched or expired lease_id returns 409.
    """
    context = _context(request)
    service = _service(request)
    duration = (
        timedelta(seconds=payload.duration_seconds)
        if payload.duration_seconds is not None
        else None
    )

    try:
        task = service.heartbeat_task(
            context,
            task_id,
            lease_id=payload.lease_id,
            duration=duration,
        )
    except TaskNotFoundError:
        return _problem(request, 404, "task_not_found", "Task not found")
    except InactiveLeaseError as exc:
        return _problem(
            request,
            409,
            "lease_inactive",
            "Lease is expired or lease_id does not match",
            detail=str(exc),
        )

    assert task.lease_id is not None  # noqa: S101
    assert task.lease_expires_at is not None  # noqa: S101
    return HeartbeatResponse(
        task_id=task.id,
        lease_id=task.lease_id,
        lease_expires_at=task.lease_expires_at.isoformat(),
    )


@router.post(
    "/tasks/{task_id}/complete",
    response_model=CompleteResponse,
    summary="Complete a leased task and deliver its result (INV-EXEC-2)",
)
def complete_task(
    task_id: uuid.UUID,
    payload: CompleteRequest,
    request: Request,
) -> CompleteResponse | JSONResponse:
    """Mark a leased task ``completed`` and record its (untrusted) result.

    INV-EXEC-2: idempotent — a second completion with the same lease_id returns
    ``duplicate=true`` instead of raising. Any other non-completable state
    returns 409. The result is stored as-is (INV-EXEC-3 stub); scheduler-side
    output-schema validation is a separate, later step.
    """
    context = _context(request)
    service = _service(request)

    try:
        outcome = service.complete_task(
            context,
            task_id,
            lease_id=payload.lease_id,
            result=payload.result,
        )
    except TaskNotFoundError:
        return _problem(request, 404, "task_not_found", "Task not found")
    except InactiveLeaseError as exc:
        return _problem(
            request,
            409,
            "lease_inactive",
            "Lease is expired or lease_id does not match",
            detail=str(exc),
        )
    except NonCompletableError as exc:
        return _problem(
            request,
            409,
            "task_not_completable",
            "Task is not in a completable state",
            detail=f"state={exc.state!r}",
        )

    return CompleteResponse(
        task_id=outcome.task_id,
        state=outcome.state,
        duplicate=outcome.duplicate,
    )
