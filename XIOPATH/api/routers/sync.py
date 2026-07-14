"""
XIOPATH — Sync Router (Phase DB Fix)
=======================================
Implements the /sync/push and /sync/pull endpoints for federated
memory synchronization between clients and the global server.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from api.routers.auth import get_current_user

router = APIRouter(prefix="/sync", tags=["Sync"])
logger = logging.getLogger(__name__)


class SyncPushRequest(BaseModel):
    id: str
    domain: str
    intent: str
    action_type: str
    action_params: dict = Field(default_factory=dict)
    face_value: dict = Field(default_factory=dict)
    place_value: dict = Field(default_factory=dict)
    visibility: str = "public"
    previous_intent: Optional[str] = None
    next_nodes: list = Field(default_factory=list)


@router.post("/push")
async def sync_push(
    body: SyncPushRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Push a memory node to the global server.
    Only public nodes are accepted — private nodes are rejected with 400.
    """
    if body.visibility == "private":
        raise HTTPException(status_code=400, detail="Private nodes cannot be synced to the global server.")

    db = request.app.state.db
    try:
        db.upsert_node(
            node_id=body.id,
            tier="global",
            domain=body.domain,
            intent=body.intent,
            device_type="",
            os_name="",
            browser="",
            viewport_width=0,
            viewport_height=0,
            visibility=body.visibility,
            face_value=body.face_value,
            place_value=body.place_value,
            action_type=body.action_type,
            action_params=body.action_params,
            previous_intent=body.previous_intent,
            next_nodes=body.next_nodes or [],
            promotions=0,
            client_id=user.get("sub", user.get("user_id", "unknown")),
        )
        logger.info(f"Sync push: node {body.id} from {user.get('sub', 'unknown')} for {body.domain}")
        return {"status": "success", "node_id": body.id}
    except Exception as e:
        logger.error(f"Sync push failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pull")
async def sync_pull(
    domain: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Pull all public memory nodes for a given domain from the global server.
    """
    db = request.app.state.db
    try:
        all_nodes = db.get_nodes_by_domain(domain)
        nodes = [n for n in all_nodes if n.get("visibility") == "public"]
        return {
            "nodes": nodes,
            "domain": domain,
            "count": len(nodes),
        }
    except Exception as e:
        logger.error(f"Sync pull failed for {domain}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
