"""
XIOPATH — WebSocket Dashboard Router
=======================================
Real-time WebSocket endpoint for the Dashboard and Extension.
Supports channel-based broadcasting with JWT authentication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import jwt
import json
import logging
import asyncio
from typing import Dict, Set, Optional
from datetime import datetime, timezone

from api.routers.auth import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/ws", tags=["WebSocket"])
logger = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 16 * 1024
ROLE_CHANNELS = {
    "client": frozenset({"system", "default", "agents", "sessions"}),
    "admin": frozenset({
        "system", "default", "workers", "memory", "dlq", "sessions",
        "agents", "analytics",
    }),
}


def allowed_channels(role: str) -> frozenset[str]:
    """Return the server-owned channel allowlist for a platform role."""
    return ROLE_CHANNELS.get(role, ROLE_CHANNELS["client"])


class ConnectionManager:
    """
    Manages active WebSocket connections for the dashboard.
    Supports role-based and channel-based broadcasting.
    """

    def __init__(self):
        # { connection_id: { ws, user_id, role, channels, connected_at } }
        self.connections: Dict[str, dict] = {}
        self._counter = 0

    @property
    def count(self) -> int:
        return len(self.connections)

    async def connect(self, websocket: WebSocket, user_id: str, role: str) -> str:
        """Accept a WebSocket connection and register it."""
        await websocket.accept()
        self._counter += 1
        conn_id = f"dash_{self._counter}"
        self.connections[conn_id] = {
            "ws": websocket,
            "user_id": user_id,
            "role": role,
            "channels": set(allowed_channels(role)),
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"Dashboard client {conn_id} connected (user={user_id}, role={role})")
        return conn_id

    def disconnect(self, conn_id: str):
        """Remove a connection from the registry."""
        if conn_id in self.connections:
            info = self.connections.pop(conn_id)
            logger.info(f"Dashboard client {conn_id} disconnected (user={info['user_id']})")

    async def send_personal(self, conn_id: str, data: dict):
        """Send a message to a specific connection."""
        conn = self.connections.get(conn_id)
        if conn:
            try:
                await conn["ws"].send_text(json.dumps(data))
            except Exception:
                self.disconnect(conn_id)

    async def broadcast(self, channel: str, payload: dict):
        """Broadcast a message to all connections subscribed to the given channel."""
        message = json.dumps({"channel": channel, "payload": payload, "ts": datetime.now(timezone.utc).isoformat()})
        dead = []
        for conn_id, conn in self.connections.items():
            if channel in conn["channels"]:
                try:
                    await conn["ws"].send_text(message)
                except Exception:
                    dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id)

    async def broadcast_to_role(self, role: str, channel: str, payload: dict):
        """Broadcast a message only to connections with the given role."""
        message = json.dumps({"channel": channel, "payload": payload, "ts": datetime.now(timezone.utc).isoformat()})
        dead = []
        for conn_id, conn in self.connections.items():
            if conn["role"] == role and channel in conn["channels"]:
                try:
                    await conn["ws"].send_text(message)
                except Exception:
                    dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id)

    def get_stats(self) -> dict:
        """Return current connection statistics."""
        roles = {}
        for conn in self.connections.values():
            roles[conn["role"]] = roles.get(conn["role"], 0) + 1
        return {
            "total": self.count,
            "by_role": roles,
        }


# Singleton — will be stored in app.state by main.py
manager = ConnectionManager()


def _verify_ws_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return the payload, or None if invalid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("WS auth failed: token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("WS auth failed: invalid token")
        return None


@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket, token: str = Query(default=None)):
    """
    Main WebSocket endpoint for dashboard clients.
    Authentication is via JWT token passed as query parameter.
    """
    # --- Auth ---
    if not token:
        await websocket.close(code=4000, reason="Missing token")
        return

    payload = _verify_ws_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = payload.get("sub", "unknown")
    role = payload.get("role", "client")

    # --- Connect ---
    conn_id = await manager.connect(websocket, user_id, role)

    # Send welcome message with connection info
    await manager.send_personal(conn_id, {
        "channel": "system",
        "payload": {
            "type": "connected",
            "conn_id": conn_id,
            "role": role,
            "channels": list(manager.connections[conn_id]["channels"]),
            "dashboard_clients": manager.count,
        }
    })

    # Broadcast to all: new client connected (for live dashboard count)
    await manager.broadcast("system", {
        "type": "client_joined",
        "dashboard_clients": manager.count,
        "role": role,
    })

    # --- Message loop ---
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="Message too large")
                break
            try:
                message = json.loads(raw)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await manager.send_personal(conn_id, {
                        "channel": "system",
                        "payload": {"type": "pong"}
                    })
                elif msg_type == "subscribe":
                    channel = message.get("channel")
                    permitted = allowed_channels(role)
                    if channel in permitted and conn_id in manager.connections:
                        manager.connections[conn_id]["channels"].add(channel)
                    else:
                        await manager.send_personal(conn_id, {
                            "channel": "system",
                            "payload": {"type": "subscription_denied"},
                        })
                elif msg_type == "unsubscribe":
                    channel = message.get("channel")
                    if channel and conn_id in manager.connections:
                        manager.connections[conn_id]["channels"].discard(channel)
                else:
                    logger.debug(f"WS {conn_id} sent unknown message type: {msg_type}")

            except json.JSONDecodeError:
                logger.warning(f"WS {conn_id} sent invalid JSON")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS {conn_id} error: {e}")
    finally:
        manager.disconnect(conn_id)
        # Broadcast: client left
        await manager.broadcast("system", {
            "type": "client_left",
            "dashboard_clients": manager.count,
        })
