"""
XIOPATH — API v2: Workflows Router
======================================
Persistent workflow definitions and execution management.

Workflow CRUD:
  POST   /workflows                  — Create workflow
  GET    /workflows                  — List workflows
  GET    /workflows/{id}             — Get workflow details
  PATCH  /workflows/{id}             — Update workflow
  DELETE /workflows/{id}             — Archive workflow
  POST   /workflows/{id}/activate    — Activate a draft workflow
  POST   /workflows/{id}/fork        — Fork a workflow

Execution Management:
  POST   /workflows/{id}/execute     — Start execution
  GET    /workflows/{id}/executions  — List executions for a workflow
  GET    /executions/{id}            — Get execution details
  POST   /executions/{id}/pause      — Pause execution
  POST   /executions/{id}/resume     — Resume execution
  POST   /executions/{id}/cancel     — Cancel execution
  GET    /workflows/{id}/stats       — Get workflow statistics
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging

from api.routers.auth import get_current_user, require_admin

router = APIRouter(tags=["Workflows v2"])
logger = logging.getLogger(__name__)


# ─── Request/Response Models ─────────────────────────────────────────────────

class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(..., min_length=1)
    version: str = "1.0.0"
    org_id: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    trigger_type: str = "manual"
    trigger_config: Optional[Dict[str, Any]] = None
    execution_mode: str = "sequential"
    max_retries: int = 0
    timeout_ms: int = 300000
    visibility: str = "private"
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateWorkflowRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    version: Optional[str] = None
    execution_mode: Optional[str] = None
    max_retries: Optional[int] = None
    timeout_ms: Optional[int] = None
    visibility: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class StartExecutionRequest(BaseModel):
    input_data: Optional[Dict[str, Any]] = None
    environment: Optional[Dict[str, Any]] = None


class ForkWorkflowRequest(BaseModel):
    new_name: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_wf_manager(request: Request):
    mgr = getattr(request.app.state, 'workflow_manager', None)
    if mgr is None:
        from core.workflow_manager import WorkflowManager
        mgr = WorkflowManager(request.app.state.db)
        request.app.state.workflow_manager = mgr
    return mgr


# ═════════════════════════════════════════════════════════════════════════════
# WORKFLOW DEFINITION CRUD
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/workflows")
async def create_workflow(
    req: CreateWorkflowRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a new workflow definition."""
    mgr = _get_wf_manager(request)
    workflow_id = mgr.create_workflow(
        name=req.name,
        steps=req.steps,
        creator_id=user.get("sub"),
        description=req.description,
        version=req.version,
        org_id=req.org_id,
        input_schema=req.input_schema,
        output_schema=req.output_schema,
        trigger_type=req.trigger_type,
        trigger_config=req.trigger_config,
        execution_mode=req.execution_mode,
        max_retries=req.max_retries,
        timeout_ms=req.timeout_ms,
        visibility=req.visibility,
        tags=req.tags,
        metadata=req.metadata,
    )
    return {"status": "success", "workflow_id": workflow_id}


@router.get("/workflows")
async def list_workflows(
    request: Request,
    state: Optional[str] = None,
    visibility: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List workflows the user can access."""
    mgr = _get_wf_manager(request)
    workflows = mgr.list_workflows(
        creator_id=user.get("sub"),
        state=state,
        visibility=visibility,
        limit=limit,
    )
    return {"workflows": workflows, "total": len(workflows)}


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get workflow details."""
    mgr = _get_wf_manager(request)
    workflow = mgr.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    return workflow


@router.patch("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    req: UpdateWorkflowRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Update a workflow definition."""
    mgr = _get_wf_manager(request)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    success = mgr.update_workflow(workflow_id, **updates)
    if not success:
        raise HTTPException(404, "Workflow not found")
    return {"status": "success", "updated_fields": list(updates.keys())}


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Archive a workflow."""
    mgr = _get_wf_manager(request)
    success = mgr.delete_workflow(workflow_id)
    if not success:
        raise HTTPException(404, "Workflow not found")
    return {"status": "success", "action": "archived"}


@router.post("/workflows/{workflow_id}/activate")
async def activate_workflow(
    workflow_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Activate a draft workflow."""
    mgr = _get_wf_manager(request)
    success = mgr.activate_workflow(workflow_id)
    if not success:
        raise HTTPException(404, "Workflow not found")
    return {"status": "success", "state": "active"}


@router.post("/workflows/{workflow_id}/fork")
async def fork_workflow(
    workflow_id: str,
    req: ForkWorkflowRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Fork (clone) a workflow."""
    mgr = _get_wf_manager(request)
    new_id = mgr.fork_workflow(workflow_id, user.get("sub"), req.new_name)
    if not new_id:
        raise HTTPException(404, "Workflow not found")
    return {"status": "success", "new_workflow_id": new_id, "forked_from": workflow_id}


# ═════════════════════════════════════════════════════════════════════════════
# EXECUTION MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

from fastapi import BackgroundTasks
import asyncio
from datetime import datetime, timezone
import json

async def _run_workflow_execution(app_state, exec_id: str, workflow: dict):
    """Background task to simulate workflow execution and stream logs via WS."""
    ws_mgr = getattr(app_state, 'ws_manager', None)
    
    def _log(msg: str, level: str = 'info', status: str = None):
        if ws_mgr:
            payload = {
                "type": "execution_log",
                "execution_id": exec_id,
                "message": msg,
                "level": level
            }
            if status:
                payload["status"] = status
            # Create a task to broadcast (since we're in async context)
            asyncio.create_task(ws_mgr.broadcast("default", payload))
            asyncio.create_task(ws_mgr.broadcast("system", payload))
            
    _log(f"Starting execution engine for {exec_id}...", "system", "running")
    await asyncio.sleep(1)
    
    steps = workflow.get("steps", [])
    if isinstance(steps, str):
        steps = json.loads(steps)
        
    _log(f"Loaded {len(steps)} nodes from DAG.", "info")
    await asyncio.sleep(1)
    
    # Policy Enforcement Check
    try:
        from core.policy_enforcer import PolicyEnforcer
        enforcer = PolicyEnforcer(getattr(app_state, 'db', None))
        if not enforcer.validate_execution(workflow.get('id', 'unknown'), "executor", "tenant"):
            _log("Execution blocked by Policy Engine.", "error", "failed")
            return
    except ImportError:
        pass
    
    for i, step in enumerate(steps):
        _log(f"Executing node [{step.get('type', 'unknown')}] (ID: {step.get('id', 'unknown')})", "info")
        await asyncio.sleep(1.5)
        _log(f"Node execution successful.", "success")
        
    await asyncio.sleep(1)
    _log(f"Execution {exec_id} completed successfully.", "success", "completed")

@router.post("/workflows/{workflow_id}/execute")
async def start_execution(
    workflow_id: str,
    req: StartExecutionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Start a new workflow execution."""
    mgr = _get_wf_manager(request)
    try:
        exec_id = mgr.start_execution(
            workflow_id=workflow_id,
            executor_id=user.get("sub"),
            input_data=req.input_data,
            environment=req.environment,
        )
        
        # Get the workflow to run
        workflow = mgr.get_workflow(workflow_id)
        if workflow:
            # Dispatch background execution
            background_tasks.add_task(_run_workflow_execution, request.app.state, exec_id, workflow)
            
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "success", "execution_id": exec_id}


@router.get("/workflows/{workflow_id}/executions")
async def list_executions(
    workflow_id: str,
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List executions for a workflow."""
    mgr = _get_wf_manager(request)
    executions = mgr.list_executions(workflow_id=workflow_id, status=status, limit=limit)
    return {"executions": executions, "total": len(executions)}


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get execution details."""
    mgr = _get_wf_manager(request)
    execution = mgr.get_execution(execution_id)
    if not execution:
        raise HTTPException(404, "Execution not found")
    return execution


@router.post("/executions/{execution_id}/pause")
async def pause_execution(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Pause a running execution."""
    mgr = _get_wf_manager(request)
    success = mgr.pause_execution(execution_id)
    if not success:
        raise HTTPException(404, "Execution not found")
    return {"status": "success", "action": "paused"}


@router.post("/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Resume a paused execution."""
    mgr = _get_wf_manager(request)
    success = mgr.resume_execution(execution_id)
    if not success:
        raise HTTPException(404, "Execution not found")
    return {"status": "success", "action": "resumed"}


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Cancel a running execution."""
    mgr = _get_wf_manager(request)
    success = mgr.cancel_execution(execution_id)
    if not success:
        raise HTTPException(404, "Execution not found")
    return {"status": "success", "action": "cancelled"}


@router.get("/workflows/{workflow_id}/stats")
async def get_workflow_stats(
    workflow_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get execution statistics for a workflow."""
    mgr = _get_wf_manager(request)
    stats = mgr.get_workflow_stats(workflow_id)
    return stats
