"""
XIOPATH — Workflow Manager (Phase 6)
========================================
Persistent workflow definitions and execution tracking.

A Workflow is a named, versioned, reusable sequence of actions (knowledge_nodes)
that can be shared, forked, and executed by any actor.

Architecture:
  WorkflowManager (this file)
    ├── CRUD for workflow definitions
    ├── Execution lifecycle (start, pause, resume, cancel)
    ├── Step-by-step execution tracking
    └── Statistics and analytics

  WorkflowOrchestrator (existing, core/workflow_orchestrator.py)
    └── In-memory runtime execution engine (delegates to ActorLoop)
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy import text

logger = logging.getLogger("WorkflowManager")


def _uuid7() -> str:
    import uuid
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowManager:
    """
    Persistent workflow management with full CRUD and execution tracking.
    """

    def __init__(self, db, knowledge_manager=None):
        self.db = db
        self.knowledge_manager = knowledge_manager

    # ═══════════════════════════════════════════════════════════════════════
    # WORKFLOW DEFINITION CRUD
    # ═══════════════════════════════════════════════════════════════════════

    def create_workflow(
        self,
        name: str,
        steps: list,
        creator_id: str,
        description: Optional[str] = None,
        version: str = "1.0.0",
        org_id: Optional[str] = None,
        input_schema: Optional[dict] = None,
        output_schema: Optional[dict] = None,
        trigger_type: str = "manual",
        trigger_config: Optional[dict] = None,
        execution_mode: str = "sequential",
        max_retries: int = 0,
        timeout_ms: int = 300000,
        visibility: str = "private",
        tags: Optional[list] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a new workflow definition. Returns the workflow ID."""
        workflow_id = _uuid7()
        now = _utcnow().isoformat()

        row = {
            "id": workflow_id,
            "name": name,
            "description": description,
            "version": version,
            "creator_id": creator_id,
            "org_id": org_id,
            "steps": json.dumps(steps),
            "input_schema": json.dumps(input_schema) if input_schema else None,
            "output_schema": json.dumps(output_schema) if output_schema else None,
            "trigger_type": trigger_type,
            "trigger_config": json.dumps(trigger_config) if trigger_config else None,
            "execution_mode": execution_mode,
            "max_retries": max_retries,
            "timeout_ms": timeout_ms,
            "state": "draft",
            "visibility": visibility,
            "tags": json.dumps(tags) if tags else None,
            "total_executions": 0,
            "success_rate": 0.0,
            "created_at": now,
            "metadata": json.dumps(metadata) if metadata else None,
        }

        with self.db.safe_transaction() as session:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            session.execute(text(f"INSERT INTO workflows ({cols}) VALUES ({placeholders})"), row)

        logger.info(f"Created workflow: '{name}' (id={workflow_id})")
        return workflow_id

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """Get a workflow definition by ID."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM workflows WHERE id = :id"),
                {"id": workflow_id}
            ).mappings().first()
            return dict(row) if row else None

    def list_workflows(
        self,
        creator_id: Optional[str] = None,
        org_id: Optional[str] = None,
        state: Optional[str] = None,
        visibility: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """List workflows with optional filters."""
        conditions = ["1=1"]
        params: dict = {"limit": limit}

        if creator_id:
            conditions.append("creator_id = :creator_id")
            params["creator_id"] = creator_id
        if org_id:
            conditions.append("(org_id = :org_id OR visibility = 'public')")
            params["org_id"] = org_id
        if state:
            conditions.append("state = :state")
            params["state"] = state
        if visibility:
            conditions.append("visibility = :visibility")
            params["visibility"] = visibility

        where = " AND ".join(conditions)

        with self.db.SessionLocal() as session:
            rows = session.execute(
                text(f"SELECT * FROM workflows WHERE {where} ORDER BY created_at DESC LIMIT :limit"),
                params
            ).mappings().all()
            return [dict(r) for r in rows]

    def update_workflow(self, workflow_id: str, **kwargs) -> bool:
        """Update a workflow definition."""
        if not kwargs:
            return False

        for key in ("steps", "input_schema", "output_schema", "trigger_config", "tags", "metadata"):
            if key in kwargs and isinstance(kwargs[key], (dict, list)):
                kwargs[key] = json.dumps(kwargs[key])

        kwargs["updated_at"] = _utcnow().isoformat()
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)
        kwargs["wf_id"] = workflow_id

        with self.db.safe_transaction() as session:
            result = session.execute(
                text(f"UPDATE workflows SET {set_clause} WHERE id = :wf_id"),
                kwargs
            )
            return result.rowcount > 0

    def delete_workflow(self, workflow_id: str) -> bool:
        """Soft-delete (archive) a workflow."""
        return self.update_workflow(workflow_id, state="archived")

    def activate_workflow(self, workflow_id: str) -> bool:
        """Transition a workflow from draft → active."""
        return self.update_workflow(workflow_id, state="active")

    def fork_workflow(self, workflow_id: str, new_creator_id: str, new_name: Optional[str] = None) -> Optional[str]:
        """Fork (clone) a workflow for a different creator."""
        original = self.get_workflow(workflow_id)
        if not original:
            return None

        steps = original.get("steps", "[]")
        if isinstance(steps, str):
            steps = json.loads(steps)

        return self.create_workflow(
            name=new_name or f"{original['name']} (fork)",
            steps=steps,
            creator_id=new_creator_id,
            description=f"Forked from {workflow_id}. {original.get('description', '')}",
            execution_mode=original.get("execution_mode", "sequential"),
            max_retries=original.get("max_retries", 0),
            timeout_ms=original.get("timeout_ms", 300000),
            metadata={"forked_from": workflow_id},
        )

    # ═══════════════════════════════════════════════════════════════════════
    # EXECUTION LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════

    def start_execution(
        self,
        workflow_id: str,
        executor_id: str,
        input_data: Optional[dict] = None,
        org_id: Optional[str] = None,
        environment: Optional[dict] = None,
        parent_execution_id: Optional[str] = None,
    ) -> str:
        """Start a new workflow execution. Returns the execution ID."""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        steps = workflow.get("steps", "[]")
        if isinstance(steps, str):
            steps = json.loads(steps)
        total_steps = len(steps)

        exec_id = _uuid7()
        now = _utcnow().isoformat()

        row = {
            "id": exec_id,
            "workflow_id": workflow_id,
            "executor_id": executor_id,
            "org_id": org_id,
            "status": "running",
            "current_step": 0,
            "total_steps": total_steps,
            "input_data": json.dumps(input_data) if input_data else None,
            "step_results": json.dumps([]),
            "environment": json.dumps(environment) if environment else None,
            "retry_count": 0,
            "parent_execution_id": parent_execution_id,
            "started_at": now,
            "created_at": now,
        }

        with self.db.safe_transaction() as session:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            session.execute(text(f"INSERT INTO workflow_executions ({cols}) VALUES ({placeholders})"), row)

            # Increment workflow execution count
            session.execute(
                text("UPDATE workflows SET total_executions = total_executions + 1 WHERE id = :wf_id"),
                {"wf_id": workflow_id}
            )

        logger.info(f"Started execution: {exec_id} for workflow {workflow_id}")
        return exec_id

    def update_execution(self, execution_id: str, **kwargs) -> bool:
        """Update execution state."""
        for key in ("output_data", "step_results", "environment", "metadata"):
            if key in kwargs and isinstance(kwargs[key], (dict, list)):
                kwargs[key] = json.dumps(kwargs[key])

        kwargs["updated_at"] = _utcnow().isoformat()
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)
        kwargs["exec_id"] = execution_id

        with self.db.safe_transaction() as session:
            result = session.execute(
                text(f"UPDATE workflow_executions SET {set_clause} WHERE id = :exec_id"),
                kwargs
            )
            return result.rowcount > 0

    def complete_execution(self, execution_id: str, output_data: Optional[dict] = None) -> bool:
        """Mark an execution as completed."""
        now = _utcnow()
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        started = execution.get("started_at")
        duration_ms = None
        if started:
            try:
                start_dt = datetime.fromisoformat(str(started))
                duration_ms = int((now - start_dt).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        success = self.update_execution(
            execution_id,
            status="completed",
            completed_at=now.isoformat(),
            duration_ms=duration_ms,
            output_data=output_data or {},
        )

        # Update workflow success rate
        if success and execution.get("workflow_id"):
            self._update_success_rate(execution["workflow_id"])

        return success

    def fail_execution(self, execution_id: str, error: str) -> bool:
        """Mark an execution as failed."""
        now = _utcnow()
        execution = self.get_execution(execution_id)
        duration_ms = None
        if execution and execution.get("started_at"):
            try:
                start_dt = datetime.fromisoformat(str(execution["started_at"]))
                duration_ms = int((now - start_dt).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        success = self.update_execution(
            execution_id,
            status="failed",
            error=error,
            completed_at=now.isoformat(),
            duration_ms=duration_ms,
        )

        if success and execution and execution.get("workflow_id"):
            self._update_success_rate(execution["workflow_id"])

        return success

    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        return self.update_execution(execution_id, status="cancelled", completed_at=_utcnow().isoformat())

    def pause_execution(self, execution_id: str) -> bool:
        """Pause a running execution."""
        return self.update_execution(execution_id, status="paused")

    def resume_execution(self, execution_id: str) -> bool:
        """Resume a paused execution."""
        return self.update_execution(execution_id, status="running")

    def record_step_result(self, execution_id: str, step_index: int, result: dict) -> bool:
        """Record the result of a single step in an execution."""
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        step_results = execution.get("step_results", "[]")
        if isinstance(step_results, str):
            step_results = json.loads(step_results)

        step_results.append({
            "step": step_index,
            "timestamp": _utcnow().isoformat(),
            **result,
        })

        return self.update_execution(
            execution_id,
            current_step=step_index + 1,
            step_results=step_results,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # READ EXECUTIONS
    # ═══════════════════════════════════════════════════════════════════════

    def get_execution(self, execution_id: str) -> Optional[dict]:
        """Get execution details by ID."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM workflow_executions WHERE id = :id"),
                {"id": execution_id}
            ).mappings().first()
            return dict(row) if row else None

    def list_executions(
        self,
        workflow_id: Optional[str] = None,
        executor_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """List executions with optional filters."""
        conditions = ["1=1"]
        params: dict = {"limit": limit}

        if workflow_id:
            conditions.append("workflow_id = :wf_id")
            params["wf_id"] = workflow_id
        if executor_id:
            conditions.append("executor_id = :exec_id")
            params["exec_id"] = executor_id
        if status:
            conditions.append("status = :status")
            params["status"] = status

        where = " AND ".join(conditions)

        with self.db.SessionLocal() as session:
            rows = session.execute(
                text(f"SELECT * FROM workflow_executions WHERE {where} ORDER BY created_at DESC LIMIT :limit"),
                params
            ).mappings().all()
            return [dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════
    # ANALYTICS
    # ═══════════════════════════════════════════════════════════════════════

    def _update_success_rate(self, workflow_id: str) -> None:
        """Recalculate and update the success rate for a workflow."""
        with self.db.safe_transaction() as session:
            total = session.execute(
                text("SELECT COUNT(*) FROM workflow_executions WHERE workflow_id = :wf_id AND status IN ('completed', 'failed')"),
                {"wf_id": workflow_id}
            ).scalar() or 0

            if total == 0:
                return

            successes = session.execute(
                text("SELECT COUNT(*) FROM workflow_executions WHERE workflow_id = :wf_id AND status = 'completed'"),
                {"wf_id": workflow_id}
            ).scalar() or 0

            rate = round(successes / total, 4)
            session.execute(
                text("UPDATE workflows SET success_rate = :rate WHERE id = :wf_id"),
                {"rate": rate, "wf_id": workflow_id}
            )

    def get_workflow_stats(self, workflow_id: str) -> dict:
        """Get execution statistics for a workflow."""
        with self.db.SessionLocal() as session:
            total = session.execute(
                text("SELECT COUNT(*) FROM workflow_executions WHERE workflow_id = :wf_id"),
                {"wf_id": workflow_id}
            ).scalar() or 0

            by_status = session.execute(
                text("SELECT status, COUNT(*) FROM workflow_executions WHERE workflow_id = :wf_id GROUP BY status"),
                {"wf_id": workflow_id}
            ).fetchall()

            avg_duration = session.execute(
                text("SELECT AVG(duration_ms) FROM workflow_executions WHERE workflow_id = :wf_id AND duration_ms IS NOT NULL"),
                {"wf_id": workflow_id}
            ).scalar()

        return {
            "total_executions": total,
            "by_status": {r[0]: r[1] for r in by_status},
            "avg_duration_ms": round(avg_duration or 0),
        }
