from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from api.schemas import ExecutionRequest, InferenceRequest, WorkerTokenRequest
from api.routers.auth import get_current_user, require_admin, SECRET_KEY, ALGORITHM
from core.agent_loop import AgentLoop
from core.gemini_engine import GeminiEngine
from core.memory_manager import MemoryManager
import logging
import uuid
import asyncio
import json
import jwt
import datetime
import os
from typing import Dict, Any, Optional, List

# Lazy import to avoid circular dependency — ws.manager is set in app.state
def _get_ws_manager():
    """Get the WS connection manager from the ws router module."""
    try:
        from api.routers.ws import manager
        return manager
    except Exception:
        return None

try:
    from redis import Redis
    from rq import Queue
    redis_conn = Redis(host='localhost', port=6379, db=0, socket_connect_timeout=1)
    redis_conn.ping() # Actually test the connection
    task_queue = Queue('agent_tasks', connection=redis_conn)
    USE_REDIS = True
except Exception:
    USE_REDIS = False
    AGENT_STATUSES: Dict[str, Dict[str, Any]] = {}

router = APIRouter(prefix="/agent", tags=["Agent"])
logger = logging.getLogger(__name__)

# --- Worker Configuration ---
WORKER_SECRET = os.environ.get("WORKER_SECRET", "default-worker-secret-change-me")
# C9 Fix: Fail hard on default secrets in production
if WORKER_SECRET == "default-worker-secret-change-me" and os.environ.get("XIOPATH_ENV") == "production":
    raise RuntimeError("CRITICAL: WORKER_SECRET must be set in production. Refusing to start with default secret.")
HEARTBEAT_CHECK_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60  # seconds

# --- Zero-Shot LLM Worker Orchestration ---
# Each entry: { 'ws': WebSocket, 'info': WorkerInfo dict }
active_workers: Dict[str, dict] = {}
pending_inferences: Dict[str, asyncio.Event] = {}
inference_results: Dict[str, dict] = {}
_heartbeat_task: Optional[asyncio.Task] = None


def _make_worker_info(worker_type: str = "general", system_info: dict = None) -> dict:
    """Creates a new WorkerInfo metadata dictionary."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "worker_type": worker_type,
        "connected_at": now.isoformat(),
        "last_heartbeat": now.isoformat(),
        "tasks_completed": 0,
        "current_task": None,
        "system_info": system_info or {}
    }


async def _heartbeat_monitor():
    """Background task that checks for stale workers every HEARTBEAT_CHECK_INTERVAL seconds."""
    while True:
        await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
        now = datetime.datetime.now(datetime.timezone.utc)
        stale_workers = []
        for wid, entry in list(active_workers.items()):
            last_hb = datetime.datetime.fromisoformat(entry["info"]["last_heartbeat"])
            if (now - last_hb).total_seconds() > HEARTBEAT_TIMEOUT:
                stale_workers.append(wid)
        for wid in stale_workers:
            logger.warning(f"Evicting stale worker {wid} (no heartbeat in {HEARTBEAT_TIMEOUT}s)")
            try:
                await active_workers[wid]["ws"].close(code=4001, reason="Heartbeat timeout")
            except Exception:
                pass
            active_workers.pop(wid, None)


def _ensure_heartbeat_monitor():
    """Start the heartbeat monitor if not already running."""
    global _heartbeat_task
    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = asyncio.get_event_loop().create_task(_heartbeat_monitor())

@router.post("/worker-token")
async def get_worker_token(req: WorkerTokenRequest):
    """
    Authenticates a worker via shared secret and returns a JWT with role='worker'.
    """
    if req.worker_secret != WORKER_SECRET:
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    payload = {
        "sub": f"worker-{uuid.uuid4()}",
        "role": "worker",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"status": "success", "token": token}


@router.get("/workers")
async def list_workers(user: dict = Depends(require_admin)):
    """
    Returns a list of all connected workers with their metadata.
    Includes calculated uptime. Excludes raw WebSocket objects.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    workers = []
    for wid, entry in active_workers.items():
        info = entry["info"].copy()
        connected_at = datetime.datetime.fromisoformat(info["connected_at"])
        info["uptime_seconds"] = round((now - connected_at).total_seconds(), 1)
        info["worker_id"] = wid
        workers.append(info)
    return {"workers": workers, "count": len(workers)}


@router.websocket("/worker-stream")
async def websocket_worker_stream(websocket: WebSocket):
    await websocket.accept()
    worker_id = str(uuid.uuid4())

    # --- JWT Handshake: First message must contain a valid token ---
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        handshake = json.loads(raw)
        token = handshake.get("token")
        if not token:
            await websocket.close(code=4000, reason="Missing token in handshake")
            return
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("role") != "worker":
                await websocket.close(code=4003, reason="Token role is not 'worker'")
                return
        except jwt.ExpiredSignatureError:
            await websocket.close(code=4001, reason="Token expired")
            return
        except jwt.InvalidTokenError:
            await websocket.close(code=4002, reason="Invalid token")
            return
    except asyncio.TimeoutError:
        await websocket.close(code=4000, reason="Handshake timeout")
        return
    except Exception:
        await websocket.close(code=4000, reason="Handshake failed")
        return

    # Extract worker metadata from handshake
    worker_type = handshake.get("worker_type", "general")
    system_info = handshake.get("system_info", {})
    worker_info = _make_worker_info(worker_type=worker_type, system_info=system_info)

    active_workers[worker_id] = {"ws": websocket, "info": worker_info}
    logger.info(f"Worker {worker_id} authenticated and registered (type: {worker_type})")

    # Ensure the heartbeat monitor is running
    _ensure_heartbeat_monitor()

    # Broadcast worker join event to dashboard
    ws_mgr = _get_ws_manager()
    if ws_mgr:
        asyncio.ensure_future(ws_mgr.broadcast("workers", {
            "type": "worker_joined",
            "worker_id": worker_id,
            "worker_type": worker_type,
            "total_workers": len(active_workers),
        }))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message.get("type") == "register_worker":
                logger.info(f"Worker {worker_id} re-registered!")
            elif message.get("type") == "heartbeat":
                active_workers[worker_id]["info"]["last_heartbeat"] = (
                    datetime.datetime.now(datetime.timezone.utc).isoformat()
                )
            elif message.get("type") == "inference_result":
                task_id = message.get("task_id")
                inference_results[task_id] = message.get("action")
                # Mark worker as idle and increment completed tasks
                active_workers[worker_id]["info"]["current_task"] = None
                active_workers[worker_id]["info"]["tasks_completed"] += 1
                if task_id in pending_inferences:
                    pending_inferences[task_id].set()
    except WebSocketDisconnect:
        logger.info(f"Worker {worker_id} disconnected")
        if worker_id in active_workers:
            del active_workers[worker_id]
        # Broadcast worker leave event
        ws_mgr = _get_ws_manager()
        if ws_mgr:
            asyncio.ensure_future(ws_mgr.broadcast("workers", {
                "type": "worker_left",
                "worker_id": worker_id,
                "total_workers": len(active_workers),
            }))

@router.post("/infer")
async def request_inference(req: InferenceRequest):
    if not active_workers:
        raise HTTPException(status_code=503, detail="No LLM workers available. Waiting for admins to connect.")

    # --- Smart Routing: filter by worker_type, then pick least-loaded ---
    candidates = list(active_workers.items())

    if req.worker_type:
        typed = [(wid, entry) for wid, entry in candidates if entry["info"]["worker_type"] == req.worker_type]
        if typed:
            candidates = typed
        else:
            logger.warning(f"No workers of type '{req.worker_type}', falling back to any available")

    # Sort: idle workers first (current_task is None), then by tasks_completed ascending
    def _sort_key(item):
        info = item[1]["info"]
        is_busy = 0 if info["current_task"] is None else 1
        return (is_busy, info["tasks_completed"])

    candidates.sort(key=_sort_key)
    worker_id, worker_entry = candidates[0]
    websocket = worker_entry["ws"]

    task_id = str(uuid.uuid4())
    task_event = asyncio.Event()
    pending_inferences[task_id] = task_event

    # Mark worker as busy
    active_workers[worker_id]["info"]["current_task"] = task_id

    await websocket.send_text(json.dumps({
        "type": "inference_task",
        "task_id": task_id,
        "intent": req.intent,
        "dom": req.dom
    }))

    # Wait for response (timeout 90s)
    try:
        await asyncio.wait_for(task_event.wait(), timeout=90.0)
        action = inference_results.get(task_id)
        return {"status": "success", "action": action, "worker_id": worker_id}
    except asyncio.TimeoutError:
        # Clear the busy state on timeout
        if worker_id in active_workers:
            active_workers[worker_id]["info"]["current_task"] = None
        raise HTTPException(status_code=504, detail="LLM Inference Timeout")
    finally:
        pending_inferences.pop(task_id, None)
        inference_results.pop(task_id, None)
# ------------------------------------------

def set_task_status(session_id: str, status_data: dict):
    if USE_REDIS:
        try:
            redis_conn.set(f"agent_status:{session_id}", json.dumps(status_data))
        except Exception:
            pass
    else:
        AGENT_STATUSES[session_id] = status_data

def get_task_status(session_id: str) -> dict:
    if USE_REDIS:
        try:
            data = redis_conn.get(f"agent_status:{session_id}")
            return json.loads(data) if data else None
        except Exception:
            return None
    return AGENT_STATUSES.get(session_id)

async def run_agent_task_async(session_id: str, start_url: str, start_intent: str, context: Dict[str, Any]):
    """
    Background task to execute a workflow graph using AgentLoop.
    """
    logger.info(f"Starting background AgentLoop task for session {session_id}")
    
    set_task_status(session_id, {
        "status": "running",
        "url": start_url,
        "intent": start_intent,
        "error": None
    })
    
    # Instantiate scoped MemoryManager
    memory_manager = MemoryManager(session_id=session_id, start_sync=False)
    
    # Real LLM Injection
    try:
        llm = GeminiEngine()
    except Exception:
        class DummyLLM:
            def ask_raw(self, prompt, **kwargs): return ""
            def get_embedding(self, text): return [0.0] * 768
        llm = DummyLLM()
        
    agent = AgentLoop(session_id=session_id, llm=llm, enable_screenshots=False)
    
    try:
        await agent.start()
        await agent.browser.page.goto(start_url)
        
        graph = memory_manager.get_workflow_graph(start_url, start_intent, context)
        if not graph:
            logger.error(f"Graph retrieval failed for {start_intent}")
            set_task_status(session_id, {"status": "failed", "error": "Graph not found"})
            return
            
        success = await agent._execute_workflow_graph(graph, context)
        if success:
            logger.info(f"Agent execution completed successfully for {session_id}")
            set_task_status(session_id, {"status": "completed"})
        else:
            logger.error(f"Agent execution failed for {session_id}")
            set_task_status(session_id, {"status": "failed"})
            
    except Exception as e:
        logger.error(f"Agent task failed: {e}")
        set_task_status(session_id, {"status": "failed", "error": str(e)})
    finally:
        await agent.stop()
        logger.info(f"Closed agent for session {session_id}")

def run_agent_task_sync(*args, **kwargs):
    asyncio.run(run_agent_task_async(*args, **kwargs))

@router.post("/execute")
async def execute_workflow(req: ExecutionRequest, background_tasks: BackgroundTasks, request: Request, user: dict = Depends(get_current_user)):
    """
    Spawns an AgentLoop in the background or via RQ to execute a Workflow Graph.
    """
    try:
        session_id = user["sub"]
        
        status_data = {
            "status": "queued",
            "url": req.url,
            "intent": req.start_intent,
            "error": None
        }
        set_task_status(session_id, status_data)
        
        if USE_REDIS:
            task_queue.enqueue(run_agent_task_sync, session_id, req.url, req.start_intent, req.context_dict)
        else:
            background_tasks.add_task(
                run_agent_task_async, 
                session_id, 
                req.url, 
                req.start_intent, 
                req.context_dict
            )
        
        return {
            "status": "success",
            "message": "Agent workflow initiated in background",
            "session_id": session_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{session_id}")
async def get_agent_status(session_id: str, user: dict = Depends(get_current_user)):
    """
    Returns the live status of an agent session.
    """
    status = get_task_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return status
