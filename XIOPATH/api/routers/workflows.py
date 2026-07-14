"""
XIOPATH — Workflow Management API (Phase W.4)
================================================
REST endpoints for workflow lifecycle management.
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from api.routers.auth import get_current_user
from typing import Optional, Dict
import logging

router = APIRouter(prefix="/workflows", tags=["Workflows"])
logger = logging.getLogger(__name__)


# ── Request/Response Models ────────────────────────────────────────────

class WorkflowStartRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=500, description="Workflow intent to execute")
    context: Optional[Dict] = Field(default=None, description="Execution context variables")


class WorkflowActionRequest(BaseModel):
    execution_id: str = Field(..., min_length=1, max_length=100)


# ── Helper ─────────────────────────────────────────────────────────────

def _get_orchestrator(request: Request):
    """Get the workflow orchestrator from app state."""
    orchestrator = getattr(request.app.state, 'workflow_orchestrator', None)
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Workflow orchestrator not initialized")
    return orchestrator


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("/execute")
async def start_workflow(
    req: WorkflowStartRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Start a new workflow execution."""
    orchestrator = _get_orchestrator(request)
    try:
        exec_id = await orchestrator.start_workflow(req.intent, req.context)
        return {
            "status": "started",
            "execution_id": exec_id,
            "intent": req.intent,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_id}/status")
async def get_workflow_status(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get the status of a workflow execution."""
    orchestrator = _get_orchestrator(request)
    status = orchestrator.get_status(execution_id)
    if not status:
        raise HTTPException(status_code=404, detail="Execution not found")
    return status


@router.post("/{execution_id}/cancel")
async def cancel_workflow(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Cancel a running workflow."""
    orchestrator = _get_orchestrator(request)
    success = await orchestrator.cancel_workflow(execution_id)
    if not success:
        raise HTTPException(status_code=400, detail="Workflow cannot be cancelled (not running or not found)")
    return {"status": "cancelled", "execution_id": execution_id}


@router.post("/{execution_id}/pause")
async def pause_workflow(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Pause a running workflow (best-effort)."""
    orchestrator = _get_orchestrator(request)
    success = await orchestrator.pause_workflow(execution_id)
    if not success:
        raise HTTPException(status_code=400, detail="Workflow cannot be paused (not running or not found)")
    return {"status": "paused", "execution_id": execution_id}


@router.post("/{execution_id}/resume")
async def resume_workflow(
    execution_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Resume a paused workflow."""
    orchestrator = _get_orchestrator(request)
    success = await orchestrator.resume_workflow(execution_id)
    if not success:
        raise HTTPException(status_code=400, detail="Workflow cannot be resumed (not paused or not found)")
    return {"status": "resumed", "execution_id": execution_id}


@router.get("/active")
async def list_active_workflows(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List all active workflow executions."""
    orchestrator = _get_orchestrator(request)
    active = orchestrator.list_active()
    return {"workflows": active, "count": len(active)}


@router.get("/history")
async def list_workflow_history(
    request: Request,
    user: dict = Depends(get_current_user),
    limit: int = 50,
):
    """List recent workflow executions (all statuses)."""
    orchestrator = _get_orchestrator(request)
    all_execs = orchestrator.list_all(limit=limit)
    return {"workflows": all_execs, "count": len(all_execs)}


# ── MasterWorkflowAgent: Goal Decomposition ───────────────────────────

class GoalRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=1000, description="High-level goal to decompose and execute")
    context: Optional[Dict] = Field(default=None, description="Additional context for the goal")


def _get_or_create_mwa(request: Request):
    """Lazy-initialize MasterWorkflowAgent on first request."""
    mwa = getattr(request.app.state, 'master_workflow_agent', None)
    if mwa is not None:
        return mwa

    # Lazy init: requires llm and a workflow_orchestrator agent_loop
    llm = getattr(request.app.state, 'llm', None)
    orchestrator = getattr(request.app.state, 'workflow_orchestrator', None)
    if not llm or not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="MasterWorkflowAgent cannot be initialized — LLM or orchestrator not available",
        )

    try:
        from core.master_workflow_agent import MasterWorkflowAgent
        mwa = MasterWorkflowAgent(llm, orchestrator.agent_loop)
        request.app.state.master_workflow_agent = mwa
        logger.info("MasterWorkflowAgent lazily initialized on first /goal request.")
        return mwa
    except Exception as e:
        logger.error(f"Failed to initialize MasterWorkflowAgent: {e}")
        raise HTTPException(status_code=503, detail=f"MasterWorkflowAgent init failed: {e}")


@router.post("/goal")
async def execute_goal(
    req: GoalRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Decompose a high-level goal into a workflow DAG and execute it."""
    mwa = _get_or_create_mwa(request)
    try:
        result = await mwa.execute_goal(req.goal, req.context)
        return {
            "status": "completed",
            "goal": req.goal,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Goal execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

