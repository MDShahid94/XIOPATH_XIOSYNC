from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from api.schemas import DeployRequest
from api.routers.auth import get_current_user
from core.memory_manager import MemoryManager
from typing import Dict, Any, List
import logging
import json
import uuid
import os
from pathlib import Path

router = APIRouter(prefix="/seed", tags=["Graph Seeding"])
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
GRAPHS_DIR = DATA_DIR / "graphs"
SWARM_PROFILES_PATH = DATA_DIR / "swarm_profiles.json"


def _walk_dag_and_insert(node: Dict[str, Any], memory_manager: MemoryManager, client_id: str, visited: set = None) -> List[str]:
    """
    Recursively walks a DAG structure and inserts each node into the database
    via MemoryManager's underlying DatabaseManager.
    Returns a list of all inserted node IDs.
    """
    if visited is None:
        visited = set()

    node_id = node.get("id", str(uuid.uuid4()))
    if node_id in visited:
        return []

    visited.add(node_id)
    inserted_ids = []

    # Extract node fields with sensible defaults
    domain = node.get("domain", "seeded")
    intent = node.get("intent", "unknown")
    face_value = node.get("face_value", {})
    place_value = node.get("place_value", {})
    action_type = node.get("action_type", "navigate")
    action_params = node.get("action_params", {})
    previous_intent = node.get("previous_intent")
    next_node_refs = node.get("next_nodes", [])
    execution_mode = node.get("execution_mode", "sequential")
    context_hash = node.get("context_hash", "default")
    volatility_type = node.get("volatility_type", "static")
    fallback_plugin = node.get("fallback_plugin")
    output_var = node.get("output_var")
    condition = node.get("condition", "default")

    # Collect next_node IDs (they may be inline objects or string references)
    next_node_ids = []
    child_nodes = []
    for ref in next_node_refs:
        if isinstance(ref, dict):
            child_id = ref.get("id", str(uuid.uuid4()))
            ref["id"] = child_id  # Ensure ID is set
            next_node_ids.append(child_id)
            child_nodes.append(ref)
        elif isinstance(ref, str):
            next_node_ids.append(ref)

    # Insert this node into the database as client_primary (pre-trusted)
    memory_manager.db.upsert_node(
        node_id=node_id,
        tier="client_primary",
        domain=domain,
        intent=intent,
        device_type=node.get("device_type"),
        os_name=node.get("os_name"),
        browser=node.get("browser"),
        viewport_width=node.get("viewport_width"),
        viewport_height=node.get("viewport_height"),
        visibility=node.get("visibility", "public"),
        face_value=face_value,
        place_value=place_value,
        action_type=action_type,
        action_params=action_params,
        previous_intent=previous_intent,
        next_nodes=next_node_ids,
        promotions=0,
        client_id=client_id,
        volatility_type=volatility_type,
        fallback_plugin=fallback_plugin,
        output_var=output_var,
        execution_mode=execution_mode,
        context_hash=context_hash,
        ref_count=0,
        bayesian_score=1.0,  # Pre-trusted score
        ema_score=1.0,
        total_vote_weight=10.0,
        status="ACTIVE"
    )
    inserted_ids.append(node_id)
    logger.info(f"Seeded node '{node_id}' (intent: {intent}) as client_primary")

    # Recurse into child nodes
    for child in child_nodes:
        child_ids = _walk_dag_and_insert(child, memory_manager, client_id, visited)
        inserted_ids.extend(child_ids)

    return inserted_ids


def _count_nodes(node: Dict[str, Any], visited: set = None) -> int:
    """Count total nodes in a DAG structure."""
    if visited is None:
        visited = set()

    node_id = node.get("id", id(node))
    if node_id in visited:
        return 0

    visited.add(node_id)
    count = 1

    for ref in node.get("next_nodes", []):
        if isinstance(ref, dict):
            count += _count_nodes(ref, visited)

    return count


@router.post("/graph")
async def seed_graph(graph: Dict[str, Any], request: Request, user: dict = Depends(get_current_user)):
    """
    Seeds a complete graph (DAG) into the memory database.
    Admin-only. Walks the entire DAG recursively, inserting each node
    as a pre-trusted client_primary entry.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required to seed graphs")

    root_node = graph.get("root") or graph
    client_id = user.get("sub", "admin_seeder")

    # Use the app's shared database via a scoped MemoryManager
    memory_manager = MemoryManager(
        session_id="graph_seeder",
        db=request.app.state.db,
        chroma_client=request.app.state.chroma_client,
        start_sync=False
    )

    try:
        inserted_ids = _walk_dag_and_insert(root_node, memory_manager, client_id)
        logger.info(f"Graph seeding complete: {len(inserted_ids)} nodes inserted")
        return {
            "status": "success",
            "nodes_inserted": len(inserted_ids),
            "node_ids": inserted_ids
        }
    except Exception as e:
        logger.error(f"Graph seeding failed: {e}")
        raise HTTPException(status_code=500, detail=f"Graph seeding failed: {str(e)}")


@router.get("/graphs")
async def list_graphs():
    """
    Lists all available pre-built graph JSON files from data/graphs/ directory.
    Returns filename, root intent, and node count for each graph.
    """
    if not GRAPHS_DIR.exists():
        return {"graphs": []}

    graphs = []
    for filepath in sorted(GRAPHS_DIR.glob("*.json")):
        try:
            with open(filepath, "r") as f:
                graph_data = json.load(f)

            root = graph_data.get("root", graph_data)
            root_intent = root.get("intent", "unknown")
            node_count = _count_nodes(root)

            graphs.append({
                "filename": filepath.name,
                "root_intent": root_intent,
                "node_count": node_count
            })
        except Exception as e:
            logger.warning(f"Failed to parse graph file {filepath.name}: {e}")
            graphs.append({
                "filename": filepath.name,
                "root_intent": "error_parsing",
                "node_count": 0
            })

    return {"graphs": graphs}


@router.post("/deploy")
async def deploy_graph(
    req: DeployRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Deploys a pre-built graph via the DeploymentOrchestrator.
    Admin-only. Runs deployment as a background task and returns
    a session_id for status tracking.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required for deployment")

    # Verify graph file exists
    graph_path = GRAPHS_DIR / req.graph_name
    if not graph_path.exists():
        # Try with .json extension
        graph_path = GRAPHS_DIR / f"{req.graph_name}.json"
        if not graph_path.exists():
            raise HTTPException(status_code=404, detail=f"Graph file '{req.graph_name}' not found in data/graphs/")

    session_id = str(uuid.uuid4())

    try:
        from core.deployment_orchestrator import DeploymentOrchestrator

        orchestrator = DeploymentOrchestrator(
            session_id=session_id,
            db=request.app.state.db,
            graph_path=str(graph_path),
            profile_mail_id=req.profile_mail_id
        )

        background_tasks.add_task(orchestrator.run)
        logger.info(f"Deployment initiated: session={session_id}, graph={req.graph_name}")

        return {
            "status": "success",
            "message": "Deployment initiated in background",
            "session_id": session_id,
            "graph_name": req.graph_name
        }
    except ImportError:
        logger.warning("DeploymentOrchestrator not yet implemented, returning placeholder")
        return {
            "status": "pending",
            "message": "DeploymentOrchestrator module not yet available",
            "session_id": session_id,
            "graph_name": req.graph_name
        }
    except Exception as e:
        logger.error(f"Deployment initiation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")


@router.get("/profiles")
async def get_swarm_profiles():
    """
    Returns the swarm profiles from data/swarm_profiles.json.
    """
    if not SWARM_PROFILES_PATH.exists():
        return {"profiles": [], "message": "No swarm_profiles.json found. Create one in data/ directory."}

    try:
        with open(SWARM_PROFILES_PATH, "r") as f:
            profiles = json.load(f)
        return profiles
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in swarm_profiles.json: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read profiles: {str(e)}")
