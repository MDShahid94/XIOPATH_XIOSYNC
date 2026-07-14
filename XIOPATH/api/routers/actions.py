"""
XIOPATH — Action Builder API (Phase E.2)
==========================================
REST endpoints for custom action CRUD, templates, and step types.
"""

import uuid
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional

from api.routers.auth import get_current_user
from core.action_builder import ActionBuilder, CustomAction, ActionStep

router = APIRouter(prefix="/actions", tags=["Action Builder"])
logger = logging.getLogger(__name__)

# ─── Shared instance ──────────────────────────────────
_builder = ActionBuilder()


class StepModel(BaseModel):
    step_type: str
    params: dict = Field(default_factory=dict)
    label: str = ""
    on_error: str = "fail"


class CreateActionRequest(BaseModel):
    name: str
    description: str = ""
    steps: List[StepModel]
    tags: List[str] = Field(default_factory=list)


class UpdateActionRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[StepModel]] = None
    tags: Optional[List[str]] = None


@router.get("/step-types")
async def get_step_types(user: dict = Depends(get_current_user)):
    """List all available step types for building actions."""
    return {"step_types": _builder.get_step_types()}


@router.get("/templates")
async def get_templates(user: dict = Depends(get_current_user)):
    """Get built-in action templates."""
    return {"templates": _builder.get_templates()}


@router.get("/")
async def list_actions(user: dict = Depends(get_current_user)):
    """List all custom actions for the current user."""
    actions = _builder.list_actions(creator_id=user.get("user_id", ""))
    return {"actions": actions, "total": len(actions)}


@router.post("/")
async def create_action(body: CreateActionRequest, user: dict = Depends(get_current_user)):
    """Create a new custom action."""
    action = CustomAction(
        id=f"act_{uuid.uuid4().hex[:12]}",
        name=body.name,
        description=body.description,
        creator_id=user.get("user_id", ""),
        steps=[ActionStep(s.step_type, s.params, s.label, s.on_error) for s in body.steps],
        tags=body.tags,
    )
    result = _builder.create(action)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["errors"])
    return result["action"]


@router.get("/{action_id}")
async def get_action(action_id: str, user: dict = Depends(get_current_user)):
    """Get a specific custom action."""
    action = _builder.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action.to_dict()


@router.put("/{action_id}")
async def update_action(
    action_id: str,
    body: UpdateActionRequest,
    user: dict = Depends(get_current_user),
):
    """Update an existing custom action."""
    updates = body.model_dump(exclude_none=True)
    if "steps" in updates:
        updates["steps"] = [s.model_dump() for s in body.steps]
    action = _builder.update(action_id, updates)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action.to_dict()


@router.delete("/{action_id}")
async def delete_action(action_id: str, user: dict = Depends(get_current_user)):
    """Delete a custom action (cannot delete templates)."""
    if _builder.delete(action_id):
        return {"status": "deleted", "id": action_id}
    raise HTTPException(status_code=400, detail="Cannot delete action (may be a built-in template)")
