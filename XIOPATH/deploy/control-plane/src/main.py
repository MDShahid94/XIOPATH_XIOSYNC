"""
XIOPATH Control Plane — Main Worker Entry Point
=================================================
This is the central orchestrator that runs on the admin's Cloudflare account.
It handles: auth, node registry, task dispatch, memory sync, and WebSocket hub.

Deployed as a Python Worker using Cloudflare's ASGI interface.
"""

from datetime import datetime, timezone, timedelta
from js import Response, JSON, Object, Headers  # CF Workers JS FFI
import json
import hashlib
import hmac
import base64
import re
import uuid


# ════════════════════════════════════════════════
# JWT (Minimal implementation for CF Workers)
# ════════════════════════════════════════════════

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)

def jwt_encode(payload: dict, secret: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url_encode(json.dumps(payload).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(signature)}"

def jwt_decode(token: str, secret: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT")
    header, body, sig = parts
    expected = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_decode(sig), expected):
        raise ValueError("Invalid signature")
    payload = json.loads(_b64url_decode(body))
    if "exp" in payload and datetime.fromtimestamp(payload["exp"], tz=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("Token expired")
    return payload


def uuid7() -> str:
    """Generate a UUIDv7 (timestamp-ordered) as string."""
    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rand = uuid.uuid4().bytes
    b = ts_ms.to_bytes(6, "big") + rand[6:]
    b = bytearray(b)
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # variant 10
    return str(uuid.UUID(bytes=bytes(b)))


# ════════════════════════════════════════════════
# Request Helpers
# ════════════════════════════════════════════════

def json_response(data, status=200):
    return Response.new(
        json.dumps(data),
        status=status,
        headers=Object.fromEntries([["content-type", "application/json"], ["access-control-allow-origin", "*"]])
    )

def error_response(message, status=400):
    return json_response({"error": message}, status=status)

async def read_body(request):
    try:
        text = await request.text()
        return json.loads(text) if text else {}
    except Exception:
        return {}

def get_bearer_token(request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return None

def require_auth(request, env) -> dict | None:
    token = get_bearer_token(request)
    if not token:
        return None
    try:
        return jwt_decode(token, env.JWT_SECRET)
    except Exception:
        return None

def require_admin(user: dict) -> bool:
    return user and user.get("role") == "admin"


# ════════════════════════════════════════════════
# Route Handlers
# ════════════════════════════════════════════════

# ── Auth ─────────────────────────────────────────

async def handle_signup(request, env):
    body = await read_body(request)
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or len(password) < 8:
        return error_response("Username required, password must be 8+ chars")
    
    # Check if exists
    existing = await env.DB.prepare("SELECT id FROM users WHERE username = ?").bind(username).first()
    if existing:
        return error_response("Username already taken", 409)
    
    # Hash password (SHA-256 — production should use bcrypt via external service)
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    user_id = uuid7()
    
    await env.DB.prepare(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)"
    ).bind(user_id, username, pw_hash, "member").run()
    
    token = jwt_encode({
        "sub": user_id, "username": username, "role": "member",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=24)).timestamp())
    }, env.JWT_SECRET)
    
    return json_response({"token": token, "user_id": user_id, "role": "member"}, 201)


async def handle_login(request, env):
    body = await read_body(request)
    username = body.get("username", "")
    password = body.get("password", "")
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    
    user = await env.DB.prepare(
        "SELECT id, username, role, password_hash FROM users WHERE username = ?"
    ).bind(username).first()
    
    if not user or user.password_hash != pw_hash:
        return error_response("Invalid credentials", 401)
    
    token = jwt_encode({
        "sub": user.id, "username": user.username, "role": user.role,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=24)).timestamp())
    }, env.JWT_SECRET)
    
    return json_response({"token": token, "user_id": user.id, "role": user.role})


async def handle_me(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    return json_response({"user": user})


# ── Node Registry ───────────────────────────────

async def handle_node_register(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    
    body = await read_body(request)
    node_id = uuid7()
    now = datetime.now(timezone.utc).isoformat()
    
    await env.DB.prepare("""
        INSERT INTO mesh_nodes (id, agent_subtype, alias, owner_id, capabilities, endpoint_url, state, joined_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
    """).bind(
        node_id,
        body.get("agent_subtype", "edge_node"),
        body.get("alias", f"node-{node_id[:8]}"),
        user["sub"],
        json.dumps(body.get("capabilities", [])),
        body.get("endpoint_url", ""),
        now, now, now
    ).run()
    
    # Issue node-specific JWT
    node_token = jwt_encode({
        "sub": user["sub"], "node_id": node_id, "role": "node",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    }, env.JWT_SECRET)
    
    # Log event
    await env.DB.prepare("""
        INSERT INTO event_log (id, node_id, event_type, severity, summary, created_at)
        VALUES (?, ?, 'node_registered', 'info', ?, ?)
    """).bind(uuid7(), node_id, f"Node {body.get('alias', node_id[:8])} registered by {user['username']}", now).run()
    
    return json_response({"node_id": node_id, "node_token": node_token, "status": "registered"}, 201)


async def handle_node_heartbeat(request, env):
    user = require_auth(request, env)
    if not user or not user.get("node_id"):
        return error_response("Node token required", 401)
    
    node_id = user["node_id"]
    now = datetime.now(timezone.utc).isoformat()
    body = await read_body(request)
    
    await env.DB.prepare("""
        UPDATE mesh_nodes SET last_heartbeat = ?, state = 'active',
            contributed_compute_requests = contributed_compute_requests + ?,
            updated_at = ?
        WHERE id = ?
    """).bind(now, body.get("requests_since_last", 0), now, node_id).run()
    
    return json_response({"status": "ok", "timestamp": now})


async def handle_list_nodes(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    
    result = await env.DB.prepare("""
        SELECT id, agent_subtype, alias, capabilities, endpoint_url, trust_score, trust_tier,
               state, region, ws_connected, last_heartbeat, task_success_count, task_failure_count,
               contributed_storage_gb, contributed_compute_requests, joined_at
        FROM mesh_nodes WHERE state != 'terminated'
        ORDER BY trust_score DESC
    """).all()
    
    nodes = []
    for row in result.results:
        nodes.append({
            "id": row.id, "subtype": row.agent_subtype, "alias": row.alias,
            "capabilities": json.loads(row.capabilities or "[]"),
            "endpoint_url": row.endpoint_url, "trust_score": row.trust_score,
            "trust_tier": row.trust_tier, "state": row.state, "region": row.region,
            "ws_connected": bool(row.ws_connected), "last_heartbeat": row.last_heartbeat,
            "tasks": {"success": row.task_success_count, "failed": row.task_failure_count},
            "contributed": {"storage_gb": row.contributed_storage_gb, "requests": row.contributed_compute_requests},
            "joined_at": row.joined_at
        })
    
    return json_response({"nodes": nodes, "count": len(nodes)})


# ── Task Dispatch ────────────────────────────────

async def handle_submit_task(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    
    body = await read_body(request)
    task_id = uuid7()
    now = datetime.now(timezone.utc).isoformat()
    
    required_cap = body.get("required_capability", "inference")
    min_trust = body.get("min_trust_tier", "newcomer")
    
    # Find best available node
    candidates = await env.DB.prepare("""
        SELECT id, alias, endpoint_url, trust_score, task_success_count, task_failure_count,
               capabilities, last_heartbeat
        FROM mesh_nodes
        WHERE state = 'active'
          AND trust_tier >= ?
          AND capabilities LIKE ?
        ORDER BY trust_score DESC
        LIMIT 10
    """).bind(min_trust, f"%{required_cap}%").all()
    
    assigned_node = None
    if candidates.results:
        # Pick least-loaded among top candidates (simple: lowest task count)
        best = min(candidates.results, key=lambda n: (n.task_success_count + n.task_failure_count))
        assigned_node = best.id
    
    await env.DB.prepare("""
        INSERT INTO task_queue (id, task_type, payload, required_capability, min_trust_tier,
                                assigned_node_id, assigned_at, state, priority, submitted_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """).bind(
        task_id, body.get("task_type", "inference"), json.dumps(body.get("payload", {})),
        required_cap, min_trust,
        assigned_node, now if assigned_node else None,
        "assigned" if assigned_node else "pending",
        body.get("priority", 5), user["sub"], now
    ).run()
    
    # If assigned, notify the node via its Durable Object
    if assigned_node:
        node_do = env.NODE_STATE.get(env.NODE_STATE.idFromName(assigned_node))
        await node_do.fetch("http://internal/task", method="POST", body=json.dumps({
            "task_id": task_id, "task_type": body.get("task_type", "inference"),
            "payload": body.get("payload", {})
        }))
    
    return json_response({
        "task_id": task_id,
        "state": "assigned" if assigned_node else "pending",
        "assigned_to": assigned_node
    }, 201)


async def handle_task_result(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    
    body = await read_body(request)
    task_id = body.get("task_id")
    now = datetime.now(timezone.utc).isoformat()
    
    success = body.get("success", True)
    new_state = "completed" if success else "failed"
    
    await env.DB.prepare("""
        UPDATE task_queue SET state = ?, result = ?, error = ?, completed_at = ?
        WHERE id = ?
    """).bind(new_state, json.dumps(body.get("result", {})), body.get("error"), now, task_id).run()
    
    # Update node stats
    node_id = user.get("node_id")
    if node_id:
        if success:
            await env.DB.prepare("UPDATE mesh_nodes SET task_success_count = task_success_count + 1 WHERE id = ?").bind(node_id).run()
        else:
            await env.DB.prepare("UPDATE mesh_nodes SET task_failure_count = task_failure_count + 1 WHERE id = ?").bind(node_id).run()
    
    return json_response({"status": "recorded", "task_id": task_id})


# ── Memory Sync ──────────────────────────────────

async def handle_sync_push(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    
    body = await read_body(request)
    node_id = body.get("id", uuid7())
    now = datetime.now(timezone.utc).isoformat()
    
    if body.get("visibility") == "private":
        return error_response("Private nodes cannot sync to global tier", 400)
    
    await env.DB.prepare("""
        INSERT OR REPLACE INTO memory_nodes
            (id, tier, domain, intent, visibility, face_value, place_value,
             action_type, action_params, previous_intent, next_nodes,
             client_id, owner_node_id, status, created_at, updated_at)
        VALUES (?, 'server_secondary', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
    """).bind(
        node_id, body.get("domain", ""), body.get("intent", ""),
        body.get("visibility", "public"),
        json.dumps(body.get("face_value", {})), json.dumps(body.get("place_value", {})),
        body.get("action_type", ""), json.dumps(body.get("action_params", {})),
        body.get("previous_intent"), json.dumps(body.get("next_nodes", [])),
        user.get("sub", "unknown"), user.get("node_id"),
        now, now
    ).run()
    
    return json_response({"status": "synced", "node_id": node_id})


async def handle_sync_pull(request, env):
    user = require_auth(request, env)
    if not user:
        return error_response("Unauthorized", 401)
    
    url = request.url
    domain = ""
    if "domain=" in url:
        domain = url.split("domain=")[1].split("&")[0]
    
    result = await env.DB.prepare("""
        SELECT * FROM memory_nodes WHERE domain = ? AND visibility = 'public' AND status = 'active'
        ORDER BY bayesian_score DESC LIMIT 100
    """).bind(domain).all()
    
    nodes = []
    for row in result.results:
        nodes.append({
            "id": row.id, "tier": row.tier, "domain": row.domain, "intent": row.intent,
            "face_value": json.loads(row.face_value or "{}"),
            "place_value": json.loads(row.place_value or "{}"),
            "action_type": row.action_type,
            "action_params": json.loads(row.action_params or "{}"),
            "bayesian_score": row.bayesian_score,
        })
    
    return json_response({"nodes": nodes, "domain": domain, "count": len(nodes)})


# ── Health ───────────────────────────────────────

async def handle_health(request, env):
    active = await env.DB.prepare("SELECT COUNT(*) as cnt FROM mesh_nodes WHERE state = 'active'").first()
    pending = await env.DB.prepare("SELECT COUNT(*) as cnt FROM task_queue WHERE state = 'pending'").first()
    
    return json_response({
        "status": "healthy",
        "service": "xiopath-control-plane",
        "version": "2.1.0-swarm",
        "mesh": {
            "active_nodes": active.cnt if active else 0,
            "pending_tasks": pending.cnt if pending else 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


# ── WebSocket Hub (via Durable Object) ───────────

async def handle_ws_upgrade(request, env):
    """Upgrade HTTP to WebSocket, forwarding to the XiopathHub Durable Object."""
    hub_id = env.WS_HUB.idFromName("global-hub")
    hub = env.WS_HUB.get(hub_id)
    return await hub.fetch(request)


# ════════════════════════════════════════════════
# Phantom Fleet Management
# ════════════════════════════════════════════════

async def handle_phantom_fleet(request, env):
    """GET /api/v1/phantom/fleet — List all phantom nodes from ontology."""
    auth = await _require_auth(request, env)
    if isinstance(auth, type(Response)):
        return auth

    db = env.DB
    state_filter = _get_query_param(request, "state")

    if state_filter:
        rows = await db.prepare(
            "SELECT id, agent_subtype, alias, state, trust_score, trust_tier, "
            "last_heartbeat, capabilities, metadata FROM mesh_nodes "
            "WHERE agent_type = 'compute' AND agent_subtype = 'phantom_node' AND state = ? "
            "ORDER BY created_at DESC"
        ).bind(state_filter).all()
    else:
        rows = await db.prepare(
            "SELECT id, agent_subtype, alias, state, trust_score, trust_tier, "
            "last_heartbeat, capabilities, metadata FROM mesh_nodes "
            "WHERE agent_type = 'compute' AND agent_subtype = 'phantom_node' "
            "ORDER BY created_at DESC"
        ).all()

    phantoms = []
    for row in (rows.results or []):
        phantoms.append({
            "id": row.id,
            "alias": row.alias,
            "state": row.state,
            "trust_score": row.trust_score,
            "trust_tier": row.trust_tier,
            "last_heartbeat": row.last_heartbeat,
            "capabilities": json.loads(row.capabilities) if row.capabilities else [],
        })

    return json_response({"phantoms": phantoms, "total": len(phantoms)})


async def handle_phantom_fleet_health(request, env):
    """GET /api/v1/phantom/fleet/health — Fleet-wide health summary."""
    auth = await _require_auth(request, env)
    if isinstance(auth, type(Response)):
        return auth

    db = env.DB

    # Aggregate states
    stats = await db.prepare(
        "SELECT state, COUNT(*) as cnt FROM mesh_nodes "
        "WHERE agent_type = 'compute' AND agent_subtype = 'phantom_node' "
        "GROUP BY state"
    ).all()

    health = {"total": 0, "by_state": {}, "checked_at": datetime.now(timezone.utc).isoformat()}
    for row in (stats.results or []):
        health["by_state"][row.state] = row.cnt
        health["total"] += row.cnt

    # Count child resources
    children = await db.prepare(
        "SELECT agent_subtype, COUNT(*) as cnt FROM mesh_nodes "
        "WHERE agent_subtype IN ('edge_worker', 'gpu_node', 'ci_runner') "
        "GROUP BY agent_subtype"
    ).all()

    health["resources"] = {}
    for row in (children.results or []):
        health["resources"][row.agent_subtype] = row.cnt

    return json_response(health)


async def handle_phantom_capacity(request, env):
    """GET /api/v1/phantom/capacity — Aggregate mesh capacity from phantoms."""
    auth = await _require_auth(request, env)
    if isinstance(auth, type(Response)):
        return auth

    db = env.DB

    # Count active phantoms and their resources
    active = await db.prepare(
        "SELECT COUNT(*) as cnt FROM mesh_nodes "
        "WHERE agent_type = 'compute' AND agent_subtype = 'phantom_node' AND state = 'active'"
    ).first()

    workers = await db.prepare(
        "SELECT COUNT(*) as cnt FROM mesh_nodes "
        "WHERE agent_subtype = 'edge_worker' AND state = 'active'"
    ).first()

    gpus = await db.prepare(
        "SELECT COUNT(*) as cnt FROM mesh_nodes "
        "WHERE agent_subtype = 'gpu_node' AND state = 'active'"
    ).first()

    capacity = {
        "active_phantoms": active.cnt if active else 0,
        "active_workers": workers.cnt if workers else 0,
        "active_gpus": gpus.cnt if gpus else 0,
        "estimated_requests_per_day": (workers.cnt if workers else 0) * 100_000,
        "estimated_d1_storage_gb": (active.cnt if active else 0) * 5,
        "estimated_r2_storage_gb": (active.cnt if active else 0) * 10,
        "estimated_gpu_hours_per_day": (gpus.cnt if gpus else 0) * 12,
    }

    return json_response(capacity)


async def handle_phantom_provision(request, env):
    """POST /api/v1/phantom/provision — Queue a new phantom provisioning job."""
    auth = await _require_auth(request, env, require_admin=True)
    if isinstance(auth, type(Response)):
        return auth

    body = json.loads(await request.text())
    member_donor_id = body.get("member_donor_id")
    locale = body.get("locale", "en-US")

    if not member_donor_id:
        return error_response("member_donor_id required", 400)

    job_id = uuid7()
    now = datetime.now(timezone.utc).isoformat()

    # Create provisioning job record
    await env.DB.prepare(
        "INSERT INTO provisioning_jobs (id, phantom_id, member_donor_id, status, "
        "current_phase, config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).bind(job_id, job_id, member_donor_id, "queued", "identity_forge",
           json.dumps({"locale": locale}), now).run()

    return json_response({"job_id": job_id, "status": "queued", "phantom_id": job_id}, 201)


async def handle_phantom_verify(request, env):
    """POST /api/v1/phantom/verify — Submit verification for a pending phantom."""
    auth = await _require_auth(request, env)
    if isinstance(auth, type(Response)):
        return auth

    body = json.loads(await request.text())
    phantom_id = body.get("phantom_id")
    verification_type = body.get("type")  # otp, link
    verification_value = body.get("value")

    if not all([phantom_id, verification_type, verification_value]):
        return error_response("phantom_id, type, and value required", 400)

    # Update job status
    await env.DB.prepare(
        "UPDATE provisioning_jobs SET status = 'verified', "
        "verification_data = ?, updated_at = ? WHERE phantom_id = ?"
    ).bind(json.dumps({"type": verification_type, "value": verification_value}),
           datetime.now(timezone.utc).isoformat(), phantom_id).run()

    return json_response({"phantom_id": phantom_id, "status": "verified"})


async def handle_phantom_aging_tick(request, env):
    """POST /api/v1/phantom/aging/daily — Trigger daily aging for all phantoms in aging state."""
    auth = await _require_auth(request, env, require_admin=True)
    if isinstance(auth, type(Response)):
        return auth

    db = env.DB

    # Find all phantoms in aging state
    aging = await db.prepare(
        "SELECT id, alias FROM mesh_nodes "
        "WHERE agent_type = 'compute' AND agent_subtype = 'phantom_node' AND state = 'aging'"
    ).all()

    aged = []
    for row in (aging.results or []):
        # Log aging event
        await db.prepare(
            "INSERT INTO event_log (id, agent_id, event_type, severity, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ).bind(uuid7(), row.id, "state_change", "info",
               f"Daily aging tick for {row.alias or row.id[:8]}",
               datetime.now(timezone.utc).isoformat()).run()
        aged.append(row.id)

    return json_response({"aged_count": len(aged), "phantom_ids": aged})


def _get_query_param(request, name):
    """Extract a query parameter from the request URL."""
    url = request.url
    if "?" not in url:
        return None
    query = url.split("?", 1)[1]
    for param in query.split("&"):
        if "=" in param:
            k, v = param.split("=", 1)
            if k == name:
                return v
    return None


async def _require_auth(request, env, require_admin=False):
    """Authenticate request. Returns user dict or Response on failure."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return error_response("Authorization required", 401)
    try:
        token = auth_header[7:]
        secret = getattr(env, 'JWT_SECRET', 'xiopath-dev-secret-change-in-production')
        user = jwt_decode(token, secret)
        if require_admin and user.get("role") != "admin":
            return error_response("Admin required", 403)
        return user
    except Exception:
        return error_response("Invalid token", 401)


# ════════════════════════════════════════════════
# Router
# ════════════════════════════════════════════════

ROUTES = {
    ("POST", "/api/v1/auth/signup"):       handle_signup,
    ("POST", "/api/v1/auth/login"):        handle_login,
    ("GET",  "/api/v1/auth/me"):           handle_me,
    ("POST", "/api/v1/mesh/nodes"):        handle_node_register,
    ("POST", "/api/v1/mesh/heartbeat"):    handle_node_heartbeat,
    ("GET",  "/api/v1/mesh/nodes"):        handle_list_nodes,
    ("POST", "/api/v1/mesh/tasks"):        handle_submit_task,
    ("POST", "/api/v1/mesh/tasks/result"): handle_task_result,
    ("POST", "/api/v1/sync/push"):         handle_sync_push,
    ("GET",  "/api/v1/sync/pull"):         handle_sync_pull,
    ("GET",  "/api/v1/health"):            handle_health,
    ("GET",  "/api/v1/ws"):                handle_ws_upgrade,
    # Phantom fleet management
    ("GET",  "/api/v1/phantom/fleet"):         handle_phantom_fleet,
    ("GET",  "/api/v1/phantom/fleet/health"):  handle_phantom_fleet_health,
    ("GET",  "/api/v1/phantom/capacity"):      handle_phantom_capacity,
    ("POST", "/api/v1/phantom/provision"):     handle_phantom_provision,
    ("POST", "/api/v1/phantom/verify"):        handle_phantom_verify,
    ("POST", "/api/v1/phantom/aging/daily"):   handle_phantom_aging_tick,
}



async def on_fetch(request, env):
    """Main fetch handler — routes requests to handlers."""
    url = request.url
    method = request.method
    
    # CORS preflight
    if method == "OPTIONS":
        return Response.new("", status=204, headers=Object.fromEntries([
            ["access-control-allow-origin", "*"],
            ["access-control-allow-methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"],
            ["access-control-allow-headers", "Content-Type, Authorization"],
            ["access-control-max-age", "86400"],
        ]))
    
    # Extract path from URL
    path = "/" + url.split("//", 1)[1].split("/", 1)[1] if "//" in url else url
    path = path.split("?")[0]  # Remove query string
    
    # Match route
    handler = ROUTES.get((method, path))
    if handler:
        try:
            return await handler(request, env)
        except Exception as e:
            return error_response(f"Internal error: {str(e)}", 500)
    
    # Root
    if path == "/" or path == "":
        return json_response({
            "message": "XIOPATH Control Plane — Decentralized Mesh Orchestrator",
            "version": "2.1.0-swarm",
            "docs": "/api/v1/health"
        })
    
    return error_response("Not found", 404)
