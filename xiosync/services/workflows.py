"""Workflow / run / task / dead-letter use cases (docs 03 §§2.11, 4.4; 07).

``WorkflowService`` is the sanctioned entry point for the durable-execution
spine. It orchestrates the pure DAG predicate (``domain/workflows``) over the
tenant-scoped ORM models, enforcing on write:

* **INV-WF-1 — a workflow may only be published with a valid DAG (doc 03 §3).**
  ``publish_workflow`` runs ``validate_workflow_dag`` over the stored ``spec``
  *before* flipping the row to ``published``; a cyclic or malformed spec is
  rejected with a domain error and the row stays ``draft``. The schema cannot
  express acyclicity, so this service is the gate.
* **INV-DLQ-1 — a failed task lands in ``dead_letters`` in state ``open`` and
  nothing auto-resolves it (doc 07 §4).** ``dead_letter_task`` moves the task to
  the terminal ``dead_letter`` state and inserts the dead-letter record in the
  landing state named by the domain (``DEAD_LETTER_LANDING_STATE``); advancing
  it to ``resolved`` is a later, governed act (INV-DLQ-2/3), never done here.

This is an intentionally thin "stub" service for Phase 3 Step 1: it covers the
create/publish/run/enqueue/dead-letter surface the invariants are proven
against and will grow the lease protocol (doc 04 §3.1) in a later step. It
follows the ``EventService`` shape — it takes the caller's ``Session`` directly
(the caller owns the transaction via ``org_scoped_session``), flushes each write
within it, and returns frozen record values so the service holds no live ORM
state. ``organization_id`` always comes from the context, never the caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from xiosync.domain.context import OrgContext
from xiosync.domain.workflows import (
    DEAD_LETTER_LANDING_STATE,
    TASK_STATE_DEAD_LETTER,
    TASK_STATE_QUEUED,
    WORKFLOW_RUN_STATE_QUEUED,
    WORKFLOW_STATE_DRAFT,
    WORKFLOW_STATE_PUBLISHED,
    WorkflowCycleError,
    WorkflowSpecError,
    validate_workflow_dag,
)
from xiosync.persistence.models.workflows import (
    DeadLetter,
    Task,
    Workflow,
    WorkflowRun,
)
from xiosync.platform.ids import new_id

__all__ = [
    "DeadLetterRecord",
    "TaskNotFoundError",
    "TaskRecord",
    "WorkflowCycleError",
    "WorkflowNotFoundError",
    "WorkflowRecord",
    "WorkflowRunRecord",
    "WorkflowService",
    "WorkflowSpecError",
]


class WorkflowNotFoundError(Exception):
    """The referenced workflow does not exist in this organization."""

    def __init__(self, workflow_id: uuid.UUID) -> None:
        super().__init__(f"workflow {workflow_id} not found in organization")
        self.workflow_id = workflow_id


class TaskNotFoundError(Exception):
    """The referenced task does not exist in this organization."""

    def __init__(self, task_id: uuid.UUID) -> None:
        super().__init__(f"task {task_id} not found in organization")
        self.task_id = task_id


@dataclass(frozen=True, slots=True)
class WorkflowRecord:
    """One ``workflows`` row, detached from the ORM."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    version: int
    spec: dict[str, Any]
    state: str
    created_by: uuid.UUID


@dataclass(frozen=True, slots=True)
class WorkflowRunRecord:
    """One ``workflow_runs`` row, detached from the ORM."""

    id: uuid.UUID
    organization_id: uuid.UUID
    workflow_id: uuid.UUID
    state: str
    initiated_by: uuid.UUID


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """One ``tasks`` row, detached from the ORM."""

    id: uuid.UUID
    organization_id: uuid.UUID
    run_id: uuid.UUID
    node_id: str
    capability_id: uuid.UUID
    state: str
    attempts: int


@dataclass(frozen=True, slots=True)
class DeadLetterRecord:
    """One ``dead_letters`` row, detached from the ORM."""

    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID
    state: str
    failure_reason: str | None


def _workflow_record(row: Workflow) -> WorkflowRecord:
    return WorkflowRecord(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        version=row.version,
        spec=row.spec,
        state=row.state,
        created_by=row.created_by,
    )


def _run_record(row: WorkflowRun) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        id=row.id,
        organization_id=row.organization_id,
        workflow_id=row.workflow_id,
        state=row.state,
        initiated_by=row.initiated_by,
    )


def _task_record(row: Task) -> TaskRecord:
    return TaskRecord(
        id=row.id,
        organization_id=row.organization_id,
        run_id=row.run_id,
        node_id=row.node_id,
        capability_id=row.capability_id,
        state=row.state,
        attempts=row.attempts,
    )


def _dead_letter_record(row: DeadLetter) -> DeadLetterRecord:
    return DeadLetterRecord(
        id=row.id,
        organization_id=row.organization_id,
        task_id=row.task_id,
        state=row.state,
        failure_reason=row.failure_reason,
    )


class WorkflowService:
    """Use-case orchestration for the durable-execution spine (doc 04 §2.1)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- Workflow definitions ----------------------------------------------

    def create_workflow(
        self,
        context: OrgContext,
        *,
        name: str,
        created_by: uuid.UUID,
        spec: Mapping[str, Any] | None = None,
        version: int = 1,
    ) -> uuid.UUID:
        """Create a ``draft`` workflow definition, returning its id.

        A new definition always starts in ``draft`` (doc 03 §2.11); a spec is
        only required to be a valid DAG at publish time (INV-WF-1), so a draft
        may carry an incomplete or empty spec while it is being authored.
        """
        workflow_id = new_id()
        self._session.add(
            Workflow(
                id=workflow_id,
                organization_id=context.organization_id,
                name=name,
                version=version,
                spec={} if spec is None else dict(spec),
                state=WORKFLOW_STATE_DRAFT,
                created_by=created_by,
            )
        )
        self._session.flush()
        return workflow_id

    def publish_workflow(self, context: OrgContext, workflow_id: uuid.UUID) -> None:
        """Publish a workflow, rejecting any spec that is not a valid DAG.

        INV-WF-1: ``validate_workflow_dag`` runs over the stored spec first, so
        a cyclic or malformed graph raises (:class:`WorkflowCycleError` /
        :class:`WorkflowSpecError`) and the row is left untouched in ``draft``.
        Only a validated spec is promoted to ``published``.
        """
        row = self._session.scalar(
            select(Workflow).where(
                Workflow.organization_id == context.organization_id,
                Workflow.id == workflow_id,
            )
        )
        if row is None:
            raise WorkflowNotFoundError(workflow_id)

        validate_workflow_dag(row.spec)

        row.state = WORKFLOW_STATE_PUBLISHED
        self._session.flush()

    def get_workflow(
        self, context: OrgContext, workflow_id: uuid.UUID
    ) -> WorkflowRecord | None:
        """Fetch one workflow in this org, or ``None`` if it does not exist."""
        row = self._session.scalar(
            select(Workflow).where(
                Workflow.organization_id == context.organization_id,
                Workflow.id == workflow_id,
            )
        )
        return None if row is None else _workflow_record(row)

    # -- Runs --------------------------------------------------------------

    def start_run(
        self,
        context: OrgContext,
        workflow_id: uuid.UUID,
        *,
        initiated_by: uuid.UUID,
    ) -> uuid.UUID:
        """Queue a new run of an existing workflow, returning its id.

        The composite FK guarantees the workflow is in this org (INV-TABLE-1);
        an absent workflow is surfaced as a clean domain error rather than a raw
        ``IntegrityError``. Runs begin ``queued`` (doc 03 §4.4).
        """
        if self.get_workflow(context, workflow_id) is None:
            raise WorkflowNotFoundError(workflow_id)

        run_id = new_id()
        self._session.add(
            WorkflowRun(
                id=run_id,
                organization_id=context.organization_id,
                workflow_id=workflow_id,
                state=WORKFLOW_RUN_STATE_QUEUED,
                initiated_by=initiated_by,
            )
        )
        self._session.flush()
        return run_id

    def get_run(self, context: OrgContext, run_id: uuid.UUID) -> WorkflowRunRecord | None:
        """Fetch one run in this org, or ``None`` if it does not exist."""
        row = self._session.scalar(
            select(WorkflowRun).where(
                WorkflowRun.organization_id == context.organization_id,
                WorkflowRun.id == run_id,
            )
        )
        return None if row is None else _run_record(row)

    # -- Tasks -------------------------------------------------------------

    def enqueue_task(
        self,
        context: OrgContext,
        run_id: uuid.UUID,
        *,
        node_id: str,
        capability_id: uuid.UUID,
    ) -> uuid.UUID:
        """Enqueue a ``queued`` task for a run node, returning its id.

        A freshly enqueued task carries no lease (all lease fields null) and
        zero attempts; leasing is the control<->execution channel added in a
        later step (doc 04 §3.1 / INV-EXEC-1).
        """
        task_id = new_id()
        self._session.add(
            Task(
                id=task_id,
                organization_id=context.organization_id,
                run_id=run_id,
                node_id=node_id,
                capability_id=capability_id,
                state=TASK_STATE_QUEUED,
                attempts=0,
            )
        )
        self._session.flush()
        return task_id

    def get_task(self, context: OrgContext, task_id: uuid.UUID) -> TaskRecord | None:
        """Fetch one task in this org, or ``None`` if it does not exist."""
        row = self._session.scalar(
            select(Task).where(
                Task.organization_id == context.organization_id,
                Task.id == task_id,
            )
        )
        return None if row is None else _task_record(row)

    # -- Dead-letter queue -------------------------------------------------

    def dead_letter_task(
        self,
        context: OrgContext,
        task_id: uuid.UUID,
        *,
        failure_reason: str | None = None,
    ) -> uuid.UUID:
        """Route a failed task to the DLQ, returning the dead-letter id.

        INV-DLQ-1: the task moves to the terminal ``dead_letter`` state and a
        ``dead_letters`` row is created in the landing state ``open``. Nothing
        here resolves it — triage and any correction proposal are governed acts
        performed later (INV-DLQ-2/3), never a side effect of landing.
        """
        row = self._session.scalar(
            select(Task).where(
                Task.organization_id == context.organization_id,
                Task.id == task_id,
            )
        )
        if row is None:
            raise TaskNotFoundError(task_id)

        row.state = TASK_STATE_DEAD_LETTER

        dead_letter_id = new_id()
        self._session.add(
            DeadLetter(
                id=dead_letter_id,
                organization_id=context.organization_id,
                task_id=task_id,
                failure_reason=failure_reason,
                state=DEAD_LETTER_LANDING_STATE,
            )
        )
        self._session.flush()
        return dead_letter_id

    def get_dead_letter(
        self, context: OrgContext, dead_letter_id: uuid.UUID
    ) -> DeadLetterRecord | None:
        """Fetch one dead-letter record in this org, or ``None`` if absent."""
        row = self._session.scalar(
            select(DeadLetter).where(
                DeadLetter.organization_id == context.organization_id,
                DeadLetter.id == dead_letter_id,
            )
        )
        return None if row is None else _dead_letter_record(row)
