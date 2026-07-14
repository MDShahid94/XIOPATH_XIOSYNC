# XIOPATH v5.0 — API Developer Guide

## Quick Start

### Base URL
```
http://localhost:8000
```

### Documentation
| Format | URL |
|--------|-----|
| Swagger UI | [/docs](http://localhost:8000/docs) |
| ReDoc | [/redoc](http://localhost:8000/redoc) |
| OpenAPI JSON | [/openapi.json](http://localhost:8000/openapi.json) |

### Authentication
```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret123", "role": "admin"}'

# Login (returns JWT)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret123"}'

# Use token
export TOKEN="<jwt_from_login>"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v2/actors
```

---

## v2 API Reference

### Actors (`/api/v2/actors`)

Actors are the core entities — humans, AI agents, and compute nodes.

```bash
# List all actors
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/actors

# Create an actor
curl -X POST http://localhost:8000/api/v2/actors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_type": "ai",
    "actor_subtype": "llm_engine",
    "role": "Content Writer",
    "alias": "GPT Writer"
  }'

# Get actor with edges
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/actors/{actor_id}/edges
```

**Actor Types:** `human`, `ai`, `compute`

---

### Type Registry (`/api/v2/types`)

Dynamic type system — 10 categories, 65+ builtin types.

```bash
# List all types in a category
curl http://localhost:8000/api/v2/types?category=actor_type

# Validate a type
curl "http://localhost:8000/api/v2/types/validate?category=actor_type&name=human"
# → {"valid": true}

# Register a custom type
curl -X POST http://localhost:8000/api/v2/types \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "actor_subtype",
    "name": "my_custom_bot",
    "display_name": "My Custom Bot",
    "description": "A specialized automation bot"
  }'
```

**Categories:** `actor_type`, `actor_subtype`, `lifecycle_state`, `lifecycle_phase`, `operation_type`, `edge_type`, `event_type`, `severity`, `capability_type`, `action_type`

---

### Organizations (`/api/v2/orgs`)

Multi-tenant collaboration with role-based access.

```bash
# Create an organization
curl -X POST http://localhost:8000/api/v2/orgs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "acme-corp",
    "display_name": "Acme Corporation",
    "plan": "pro"
  }'

# Add a member
curl -X POST http://localhost:8000/api/v2/orgs/{org_id}/members \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"actor_id": "...", "role": "admin"}'
```

**Roles:** `owner`, `admin`, `member`, `viewer`
**Plans:** `free` (50 actors), `pro` (500 actors), `enterprise` (unlimited)

---

### Workflows (`/api/v2/workflows`)

Versioned, shareable workflow definitions with execution tracking.

```bash
# Create a workflow
curl -X POST http://localhost:8000/api/v2/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Login Automation",
    "steps": [
      {"order": 1, "action_type": "browser", "action_spec": {"action": "navigate", "url": "https://example.com/login"}},
      {"order": 2, "action_type": "browser", "action_spec": {"action": "type", "selector": "#email", "text": "user@example.com"}},
      {"order": 3, "action_type": "browser", "action_spec": {"action": "click", "selector": "#submit"}}
    ],
    "description": "Automates login flow"
  }'

# Execute a workflow
curl -X POST http://localhost:8000/api/v2/workflows/{wf_id}/execute \
  -H "Authorization: Bearer $TOKEN"

# Check execution status
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/{exec_id}

# Pause / Resume / Cancel
curl -X POST http://localhost:8000/api/v2/executions/{exec_id}/pause
curl -X POST http://localhost:8000/api/v2/executions/{exec_id}/resume
curl -X POST http://localhost:8000/api/v2/executions/{exec_id}/cancel

# Fork a workflow
curl -X POST http://localhost:8000/api/v2/workflows/{wf_id}/fork \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Improved Login"}'

# Get workflow analytics
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/workflows/{wf_id}/stats
```

**Execution States:** `pending` → `running` → `completed` | `failed` | `cancelled`
**Workflow States:** `draft` → `active` → `archived`

---

### Marketplace (`/api/v1/marketplace`)

Publish and install any entity type.

```bash
# Publish a workflow to marketplace
curl -X POST http://localhost:8000/api/v1/marketplace/publish/entity \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "workflow",
    "entity_id": "...",
    "title": "Login Automation Pro",
    "description": "Battle-tested login automation",
    "version": "1.0.0",
    "tags": ["login", "automation"]
  }'
```

**Entity Types:** `workflow`, `knowledge`, `bundle`, `environment`

---

## Database Schema

26 tables across 5 domains:

| Domain | Tables |
|--------|--------|
| Core | `actors`, `actor_edges`, `operations`, `capabilities`, `capability_grants`, `connections`, `actor_profiles`, `actor_versions`, `bundles`, `events` |
| Type System | `type_registry` |
| Knowledge | `knowledge_nodes`, `client_vote_counts`, `client_votes` |
| Workflows | `workflows`, `workflow_executions`, `execution_policies` |
| Multi-Tenant | `organizations`, `org_memberships`, `auth_identities` |
| Marketplace | `marketplace_listings`, `marketplace_reviews` |
| Legacy | `users`, `memory_nodes`, `scheduled_jobs` |

---

## Running the Server

```bash
cd /path/to/XIOPATH
source .venv/bin/activate

# Apply migrations
alembic upgrade head

# Start development server
uvicorn api.main:app --reload --port 8000

# Export OpenAPI spec
python3 scripts/export_openapi.py docs/openapi.json
```
