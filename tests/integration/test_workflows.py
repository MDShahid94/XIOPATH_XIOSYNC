"""Real-PostgreSQL tests for the Workflow service (docs 03 §§2.11, 4.4; 07).

Runs the full ``WorkflowService`` stack — pure DAG predicate + tenant-scoped
ORM writes — against a scratch database migrated by Alembic alone, entered
through the canonical ``org_scoped_session`` RLS gate. Seeding uses the admin
(superuser) connection (which bypasses RLS by design); every service call and
assertion runs as the plain application role inside the org scope.

These prove, on the real schema:

* INV-WF-1 — a workflow whose ``spec`` is a valid DAG can be published, and a
  cyclic (or otherwise malformed) spec is rejected on publish with the row left
  untouched in ``draft``; and
* INV-DLQ-1 — a failed task lands in ``dead_letters`` in state ``open`` while
  the task itself moves to the terminal ``dead_letter`` state, with nothing
  auto-resolving the record.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from xiosync.domain.context import MembershipRole, OrgContext, PlatformRole
from xiosync.domain.workflows import WorkflowCycleError, WorkflowSpecError
from xiosync.persistence.tenancy import org_scoped_session
from xiosync.platform.ids import new_id
from xiosync.services.workflows import WorkflowService

pytestmark = pytest.mark.integration


def _seed_org_actor_capability(
    admin_url: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed one active org, one active actor, and one capability.

    Returns ``(org_id, actor_id, capability_id)``. Tasks reference a capability
    and (when leased) an actor, so both must exist in the org before a run's
    tasks can be enqueued.
    """
    organization_id = new_id()
    actor_id = new_id()
    capability_id = new_id()
    engine = create_engine(admin_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations (id, slug, name, state) "
                    "VALUES (:id, :slug, 'Workflows Test', 'active')"
                ),
                {"id": organization_id, "slug": f"wf-{organization_id}"},
            )
            connection.execute(
                text(
                    "INSERT INTO actors (id, organization_id, actor_type, state, "
                    "lifecycle_phase, trust_tier, health_status) VALUES "
                    "(:id, :org, 'ai', 'active', 'operational', 'trusted', 'healthy')"
                ),
                {"id": actor_id, "org": organization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO capabilities (id, organization_id, name) "
                    "VALUES (:id, :org, 'fetch')"
                ),
                {"id": capability_id, "org": organization_id},
            )
    finally:
        engine.dispose()
    return organization_id, actor_id, capability_id


def _context(organization_id: uuid.UUID, actor_id: uuid.UUID) -> OrgContext:
    return OrgContext(
        auth_identity_id=new_id(),
        actor_id=actor_id,
        organization_id=organization_id,
        session_id=new_id(),
        platform_role=PlatformRole.NONE,
        membership_role=MembershipRole.ORG_MEMBER,
    )


# A minimal linear DAG: fetch -> transform -> load.
_LINEAR_DAG = {
    "nodes": [{"id": "fetch"}, {"id": "transform"}, {"id": "load"}],
    "edges": [
        {"from": "fetch", "to": "transform"},
        {"from": "transform", "to": "load"},
    ],
}

# The same three nodes closed into a cycle: load -> fetch.
_CYCLIC_DAG = {
    "nodes": [{"id": "fetch"}, {"id": "transform"}, {"id": "load"}],
    "edges": [
        {"from": "fetch", "to": "transform"},
        {"from": "transform", "to": "load"},
        {"from": "load", "to": "fetch"},
    ],
}


def _state(engine: Engine, context: OrgContext, table: str, row_id: uuid.UUID) -> str:
    with org_scoped_session(engine, context) as session:
        state = session.execute(
            text(f"SELECT state FROM {table} WHERE id = :id"),  # noqa: S608 - table is a literal
            {"id": row_id},
        ).scalar_one()
    return str(state)


def test_publish_valid_dag_succeeds(
    migrated_database_url: str, app_role_database_url: str
) -> None:
    """INV-WF-1: a workflow with an acyclic spec publishes cleanly."""
    organization_id, actor_id, _ = _seed_org_actor_capability(migrated_database_url)
    context = _context(organization_id, actor_id)
    engine = create_engine(app_role_database_url)
    try:
        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            workflow_id = service.create_workflow(
                context, name="etl", created_by=actor_id, spec=_LINEAR_DAG
            )

        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            service.publish_workflow(context, workflow_id)

        assert _state(engine, context, "workflows", workflow_id) == "published"
    finally:
        engine.dispose()


def test_publish_cyclic_spec_is_rejected(
    migrated_database_url: str, app_role_database_url: str
) -> None:
    """INV-WF-1: publishing a cyclic spec is rejected; the row stays draft."""
    organization_id, actor_id, _ = _seed_org_actor_capability(migrated_database_url)
    context = _context(organization_id, actor_id)
    engine = create_engine(app_role_database_url)
    try:
        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            workflow_id = service.create_workflow(
                context, name="cyclic", created_by=actor_id, spec=_CYCLIC_DAG
            )

        with pytest.raises(WorkflowCycleError):
            with org_scoped_session(engine, context) as session:
                service = WorkflowService(session)
                service.publish_workflow(context, workflow_id)

        # The rejected publish left the workflow untouched in draft.
        assert _state(engine, context, "workflows", workflow_id) == "draft"
    finally:
        engine.dispose()


def test_publish_malformed_spec_is_rejected(
    migrated_database_url: str, app_role_database_url: str
) -> None:
    """INV-WF-1: an edge referencing an unknown node is a spec error, not published."""
    organization_id, actor_id, _ = _seed_org_actor_capability(migrated_database_url)
    context = _context(organization_id, actor_id)
    engine = create_engine(app_role_database_url)
    try:
        dangling = {
            "nodes": [{"id": "fetch"}],
            "edges": [{"from": "fetch", "to": "ghost"}],
        }
        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            workflow_id = service.create_workflow(
                context, name="dangling", created_by=actor_id, spec=dangling
            )

        with pytest.raises(WorkflowSpecError):
            with org_scoped_session(engine, context) as session:
                service = WorkflowService(session)
                service.publish_workflow(context, workflow_id)

        assert _state(engine, context, "workflows", workflow_id) == "draft"
    finally:
        engine.dispose()


def test_failed_task_lands_in_dlq_open(
    migrated_database_url: str, app_role_database_url: str
) -> None:
    """INV-DLQ-1: a dead-lettered task lands 'open' and the task goes terminal."""
    organization_id, actor_id, capability_id = _seed_org_actor_capability(
        migrated_database_url
    )
    context = _context(organization_id, actor_id)
    engine = create_engine(app_role_database_url)
    try:
        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            workflow_id = service.create_workflow(
                context, name="etl", created_by=actor_id, spec=_LINEAR_DAG
            )
            run_id = service.start_run(context, workflow_id, initiated_by=actor_id)
            task_id = service.enqueue_task(
                context, run_id, node_id="fetch", capability_id=capability_id
            )

        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            dead_letter_id = service.dead_letter_task(
                context, task_id, failure_reason="capability timed out"
            )

        with org_scoped_session(engine, context) as session:
            service = WorkflowService(session)
            task = service.get_task(context, task_id)
            dead_letter = service.get_dead_letter(context, dead_letter_id)

        assert task is not None
        assert task.state == "dead_letter"
        assert dead_letter is not None
        assert dead_letter.task_id == task_id
        assert dead_letter.state == "open"
        assert dead_letter.failure_reason == "capability timed out"
    finally:
        engine.dispose()
