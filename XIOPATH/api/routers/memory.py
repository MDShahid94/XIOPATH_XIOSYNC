from fastapi import APIRouter, HTTPException, Request, Depends
from api.schemas import PromotionRequest, RecordActionRequest
from api.routers.auth import get_current_user
from core.memory_manager import MemoryManager
import logging

router = APIRouter(prefix="/memory", tags=["Memory"])
logger = logging.getLogger(__name__)

@router.post("/record")
async def record_action(req: RecordActionRequest, request: Request, user: dict = Depends(get_current_user)):
    """
    Directly injects a recorded action from the Teacher Extension into the user's isolated memory graph.
    """
    memory_manager = MemoryManager(
        session_id=user["sub"], 
        db=request.app.state.db, 
        chroma_client=request.app.state.chroma_client, 
        start_sync=False
    )
    
    try:
        # In a real scenario, we might want to attach a previous_intent if part of a sequence,
        # but for now we'll record standalone actions or infer from the frontend.
        node_id = memory_manager.save_new_action(
            url=req.url,
            intent=req.intent,
            face_value=req.face_value,
            place_value=req.place_value,
            action_type=req.action_type,
            action_params=req.action_params,
            previous_node_id=req.previous_node_id
        )
        return {"status": "success", "node_id": node_id, "message": "Action recorded successfully"}
    except Exception as e:
        logger.error(f"Failed to record action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/promote")
async def promote_node(req: PromotionRequest, request: Request, user: dict = Depends(get_current_user)):
    """
    Submits a promotion request to the ServerMemoryAPI.
    If 3 unique clients vote, it reaches Global Primary consensus.
    """
    server_api = request.app.state.server_api
    try:
        server_api.submit_promotion(req.domain, req.node_id, req.action_data, req.client_id)
        
        # Check if it achieved consensus by querying the DB
        node = request.app.state.db.get_node(req.node_id)
        tier = node["tier"] if node else "unknown"
        
        return {"status": "success", "node_id": req.node_id, "current_tier": tier}
    except Exception as e:
        logger.error(f"Promotion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/graph")
async def get_memory_graph(url: str, intent: str, request: Request, user: dict = Depends(get_current_user)):
    """
    Retrieves the execution graph starting from the given intent, respecting Auth isolation.
    """
    memory_manager = MemoryManager(
        session_id=user["sub"], 
        db=request.app.state.db, 
        chroma_client=request.app.state.chroma_client, 
        start_sync=False
    )
    
    try:
        # We need context_dict to evaluate the 5-Tier Fallback Search on the root node
        # For this visualization endpoint, we'll use a broad default desktop context
        mock_context = {
            "device_type": "desktop",
            "os_name": "macintel",
            "browser": "chromium",
            "viewport": "1280x800"
        }
        graph = memory_manager.get_workflow_graph(url, intent, context=mock_context)
        if not graph:
            raise HTTPException(status_code=404, detail="Graph not found")
        return graph
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Graph retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
async def search_memory(query: str, request: Request, user: dict = Depends(get_current_user)):
    """
    Searches the memory graph for workflows matching the query.
    Returns intents ordered by primary/secondary tiers, isolated to user.
    """
    memory_manager = MemoryManager(
        session_id=user["sub"], 
        db=request.app.state.db, 
        chroma_client=request.app.state.chroma_client, 
        start_sync=False
    )
    try:
        results = memory_manager.search_intents(query)
        return {"status": "success", "data": results}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
