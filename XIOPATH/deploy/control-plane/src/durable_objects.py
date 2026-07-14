"""
XIOPATH — XiopathHub Durable Object
=====================================
WebSocket hub using the Hibernation API for zero-cost idle connections.
Manages: dashboard streams, node worker streams, real-time events.

Each connected client is either a:
  - "dashboard" — receives broadcast events (node status, task updates)
  - "node"      — receives task assignments, sends heartbeats + results

Uses DO SQLite for persistent state (connection metadata survives hibernation).
"""

from js import Response, Object, WebSocketPair
import json
from datetime import datetime, timezone


class XiopathHub:
    """
    Durable Object that manages all WebSocket connections for the XIOPATH mesh.
    Uses the Hibernation API: connections persist even when DO is evicted from memory.
    """
    
    def __init__(self, state, env):
        self.state = state
        self.env = env
        self.sql = state.storage.sql
        
        # Create connection metadata table (persists across hibernation)
        self.sql.exec("""
            CREATE TABLE IF NOT EXISTS ws_connections (
                tag TEXT PRIMARY KEY,
                client_type TEXT NOT NULL,
                node_id TEXT,
                user_id TEXT,
                connected_at TEXT NOT NULL,
                last_message_at TEXT
            )
        """)
    
    async def fetch(self, request):
        """Handle WebSocket upgrade requests."""
        url = request.url
        
        if request.headers.get("Upgrade") != "websocket":
            return Response.new("Expected WebSocket upgrade", status=426)
        
        # Create WebSocket pair
        pair = WebSocketPair.new()
        server = pair[0]
        client = pair[1]
        
        # Extract auth from query params (e.g., ?token=xxx&type=dashboard)
        params = {}
        if "?" in url:
            query = url.split("?")[1]
            for part in query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v
        
        client_type = params.get("type", "dashboard")
        node_id = params.get("node_id", "")
        user_id = params.get("user_id", "anonymous")
        
        # Generate a unique tag for this connection
        tag = f"{client_type}:{node_id or user_id}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        # Accept with Hibernation API (DO can sleep while WS stays open)
        self.state.acceptWebSocket(server, [tag, client_type])
        
        # Store connection metadata
        now = datetime.now(timezone.utc).isoformat()
        self.sql.exec(
            "INSERT OR REPLACE INTO ws_connections (tag, client_type, node_id, user_id, connected_at, last_message_at) VALUES (?, ?, ?, ?, ?, ?)",
            tag, client_type, node_id, user_id, now, now
        )
        
        # Send welcome message
        server.send(json.dumps({
            "type": "connected",
            "tag": tag,
            "message": f"Connected to XIOPATH Mesh Hub as {client_type}"
        }))
        
        return Response.new(None, status=101, webSocket=client)
    
    async def webSocketMessage(self, ws, message):
        """
        Called when a hibernated WebSocket receives a message.
        The DO wakes up from hibernation to process it, then can go back to sleep.
        """
        tags = self.state.getTags(ws)
        tag = tags[0] if tags else "unknown"
        client_type = tags[1] if len(tags) > 1 else "unknown"
        now = datetime.now(timezone.utc).isoformat()
        
        # Update last_message_at
        self.sql.exec("UPDATE ws_connections SET last_message_at = ? WHERE tag = ?", now, tag)
        
        try:
            data = json.loads(message)
        except Exception:
            ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return
        
        msg_type = data.get("type", "")
        
        if msg_type == "heartbeat":
            # Node heartbeat — acknowledge
            ws.send(json.dumps({"type": "heartbeat_ack", "timestamp": now}))
            
            # Broadcast node status to dashboards
            self._broadcast_to_type("dashboard", {
                "type": "node_heartbeat",
                "node_id": data.get("node_id", ""),
                "timestamp": now,
                "metrics": data.get("metrics", {})
            })
        
        elif msg_type == "task_result":
            # Node completed a task — broadcast to dashboards
            self._broadcast_to_type("dashboard", {
                "type": "task_completed",
                "task_id": data.get("task_id"),
                "node_id": data.get("node_id"),
                "success": data.get("success", True),
                "timestamp": now
            })
        
        elif msg_type == "broadcast":
            # Admin broadcasting to all dashboards
            self._broadcast_to_type("dashboard", {
                "type": "broadcast",
                "message": data.get("message", ""),
                "timestamp": now
            })
        
        elif msg_type == "ping":
            ws.send(json.dumps({"type": "pong", "timestamp": now}))
        
        else:
            ws.send(json.dumps({"type": "echo", "received": data, "timestamp": now}))
    
    async def webSocketClose(self, ws, code, reason, wasClean):
        """Called when a WebSocket connection closes."""
        tags = self.state.getTags(ws)
        tag = tags[0] if tags else "unknown"
        
        # Remove from metadata
        self.sql.exec("DELETE FROM ws_connections WHERE tag = ?", tag)
        
        # Broadcast disconnection to dashboards
        self._broadcast_to_type("dashboard", {
            "type": "node_disconnected",
            "tag": tag,
            "code": code,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def webSocketError(self, ws, error):
        """Called on WebSocket error."""
        tags = self.state.getTags(ws)
        tag = tags[0] if tags else "unknown"
        self.sql.exec("DELETE FROM ws_connections WHERE tag = ?", tag)
    
    def _broadcast_to_type(self, target_type: str, message: dict):
        """Send a message to all WebSocket connections of a given type."""
        sockets = self.state.getWebSockets(target_type)
        payload = json.dumps(message)
        for ws in sockets:
            try:
                ws.send(payload)
            except Exception:
                pass  # Connection may have closed
    
    def _broadcast_all(self, message: dict):
        """Send a message to ALL connected WebSockets."""
        sockets = self.state.getWebSockets()
        payload = json.dumps(message)
        for ws in sockets:
            try:
                ws.send(payload)
            except Exception:
                pass


class NodeState:
    """
    Per-node Durable Object — stores individual node state and pending tasks.
    One instance per mesh node, addressed by node_id.
    """
    
    def __init__(self, state, env):
        self.state = state
        self.env = env
        self.sql = state.storage.sql
        
        self.sql.exec("""
            CREATE TABLE IF NOT EXISTS pending_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                assigned_at TEXT NOT NULL
            )
        """)
    
    async def fetch(self, request):
        """Handle internal requests (task assignments from the orchestrator)."""
        url = request.url
        
        if "/task" in url and request.method == "POST":
            body = await request.text()
            data = json.loads(body)
            
            now = datetime.now(timezone.utc).isoformat()
            self.sql.exec(
                "INSERT OR REPLACE INTO pending_tasks (task_id, task_type, payload, assigned_at) VALUES (?, ?, ?, ?)",
                data["task_id"], data["task_type"], json.dumps(data.get("payload", {})), now
            )
            
            return Response.new(json.dumps({"status": "queued"}), headers=Object.fromEntries([
                ["content-type", "application/json"]
            ]))
        
        if "/tasks" in url and request.method == "GET":
            cursor = self.sql.exec("SELECT * FROM pending_tasks ORDER BY assigned_at ASC")
            tasks = []
            for row in cursor:
                tasks.append({
                    "task_id": row.task_id, "task_type": row.task_type,
                    "payload": json.loads(row.payload), "assigned_at": row.assigned_at
                })
            return Response.new(json.dumps({"tasks": tasks}), headers=Object.fromEntries([
                ["content-type", "application/json"]
            ]))
        
        if "/task/" in url and request.method == "DELETE":
            task_id = url.split("/task/")[1].split("?")[0]
            self.sql.exec("DELETE FROM pending_tasks WHERE task_id = ?", task_id)
            return Response.new(json.dumps({"status": "removed"}), headers=Object.fromEntries([
                ["content-type", "application/json"]
            ]))
        
        return Response.new("Not found", status=404)
