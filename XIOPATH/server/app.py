from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import json
import os

app = FastAPI(title="Federated Memory Sync Server")

# In-memory storage for prototype
# In production, this would be a Redis/Postgres cluster
global_memory = {}
client_votes = {}

class MemoryNode(BaseModel):
    id: str
    domain: str
    intent: str
    action_type: str
    action_params: Dict
    face_value: Dict
    place_value: Dict
    visibility: str = "public"
    previous_intent: Optional[str] = None
    next_nodes: List[str] = []

@app.post("/sync/push")
async def push_memory(node: MemoryNode, client_id: str):
    """Clients push their locally promoted memory nodes to the server."""
    if node.visibility == 'private':
        raise HTTPException(status_code=400, detail="Cannot push private memory to global sync")
        
    node_id = node.id
    
    if node_id not in global_memory:
        global_memory[node_id] = node.dict()
        client_votes[node_id] = {client_id}
    else:
        client_votes[node_id].add(client_id)
        
    votes = len(client_votes[node_id])
    
    # Simple simulated consensus rule
    if votes >= 3:
        global_memory[node_id]['tier'] = 'server_primary'
    else:
        global_memory[node_id]['tier'] = 'server_secondary'
        
    return {"status": "success", "votes": votes, "tier": global_memory[node_id]['tier']}

@app.get("/sync/pull")
async def pull_memory(domain: str):
    """Clients pull all global memory nodes for a specific domain to cache locally."""
    domain_nodes = [node for node in global_memory.values() if node['domain'] == domain]
    return {"nodes": domain_nodes}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
