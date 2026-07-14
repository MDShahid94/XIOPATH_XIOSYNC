from fastapi import APIRouter, HTTPException, Depends
from api.routers.auth import get_current_user
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dlq", tags=["DLQ"])

@router.get("/list")
async def list_dlq_incidents(user: dict = Depends(get_current_user)):
    """
    Scans the data/dlq/ directory for failed circuit breaker dumps and returns them.
    """
    dlq_dir = Path("data/dlq")
    incidents = []
    
    if not dlq_dir.exists():
        return {"incidents": []}
        
    try:
        for file_path in dlq_dir.glob("*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    
                # The CircuitBreaker dumps standard context
                # Add filename so we can uniquely identify it
                incidents.append({
                    "id": file_path.name,
                    "url": data.get("url", "Unknown"),
                    "intent": data.get("intent", "Unknown"),
                    "timestamp": data.get("timestamp", "Unknown"),
                    "context": data.get("context", {}),
                    "volatility_type": data.get("volatility_type", "static"),
                    "fallback_plugin": data.get("fallback_plugin", None)
                })
            except Exception as e:
                logger.warning(f"Failed to read DLQ file {file_path}: {e}")
                
        # Sort by timestamp descending (newest first)
        incidents.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"incidents": incidents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
