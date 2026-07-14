"""
XIOPATH — API v2: Types Router
===================================
CRUD endpoints for the Type Registry.
Enables runtime type extensibility without code changes.

GET    /types                     — List all types (filterable by category)
GET    /types/{category}          — List types in a category
GET    /types/{category}/{name}   — Get type details (including schema)
POST   /types                     — Register a new custom type (admin)
PATCH  /types/{category}/{name}   — Deprecate a type (admin)
DELETE /types/{category}/{name}   — Delete a user-created type (admin)
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

from api.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/types", tags=["Types v2"])
logger = logging.getLogger(__name__)


# ─── Request/Response Models ─────────────────────────────────────────────────

class RegisterTypeRequest(BaseModel):
    category: str = Field(..., description="Type category: actor_type, actor_subtype, edge_type, operation_type, lifecycle_state, event_type, capability_type, action_type, etc.")
    name: str = Field(..., description="Type identifier (lowercase_snake_case)")
    display_name: Optional[str] = Field(None, description="Human-readable label")
    description: Optional[str] = Field(None, description="Explanation of the type")
    parent_name: Optional[str] = Field(None, description="Parent type (for hierarchical types like actor_subtype)")
    schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for validation (e.g., action_type specs)")
    org_id: Optional[str] = Field(None, description="Organization scope (NULL = global)")
    sort_order: int = Field(100, description="Display ordering")
    metadata: Optional[Dict[str, Any]] = None


class ValidateActionSpecRequest(BaseModel):
    action_type: str = Field(..., description="The action type to validate against")
    action_spec: Dict[str, Any] = Field(..., description="The spec to validate")


# ─── Helper ──────────────────────────────────────────────────────────────────

def _get_registry(request: Request):
    """Get the TypeRegistry from app state."""
    registry = getattr(request.app.state, "type_registry", None)
    if registry is None:
        raise HTTPException(503, "TypeRegistry not initialized")
    return registry


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.get("")
async def list_all_types(
    request: Request,
    category: Optional[str] = None,
    user=Depends(get_current_user),
):
    """List all registered types, optionally filtered by category."""
    registry = _get_registry(request)
    registry._ensure_cache()

    if category:
        types = registry._cache.get(category, {})
        results = []
        for name, entry in types.items():
            results.append({
                "category": category,
                "name": name,
                "display_name": entry.get("display_name"),
                "description": entry.get("description"),
                "parent_name": entry.get("parent_name"),
                "is_builtin": entry.get("is_builtin"),
                "has_schema": bool(entry.get("schema")),
            })
        return {"category": category, "types": results, "total": len(results)}

    # All categories
    all_types = {}
    for cat, types in registry._cache.items():
        all_types[cat] = [
            {
                "name": name,
                "display_name": entry.get("display_name"),
                "is_builtin": entry.get("is_builtin"),
            }
            for name, entry in types.items()
        ]
    return {
        "categories": all_types,
        "total_categories": len(all_types),
        "total_types": sum(len(v) for v in all_types.values()),
    }


@router.get("/{category}")
async def list_types_by_category(
    request: Request,
    category: str,
    user=Depends(get_current_user),
):
    """List all types in a specific category."""
    registry = _get_registry(request)
    types_list = registry.get_types(category)
    details = []
    for name in types_list:
        entry = registry.get_type_details(category, name)
        if entry:
            details.append({
                "name": name,
                "display_name": entry.get("display_name"),
                "description": entry.get("description"),
                "parent_name": entry.get("parent_name"),
                "is_builtin": entry.get("is_builtin"),
                "has_schema": bool(entry.get("schema")),
                "state": entry.get("state"),
            })
    return {"category": category, "types": details, "total": len(details)}


@router.get("/{category}/{name}")
async def get_type_detail(
    request: Request,
    category: str,
    name: str,
    user=Depends(get_current_user),
):
    """Get full details for a specific type, including its JSON schema."""
    registry = _get_registry(request)
    entry = registry.get_type_details(category, name)
    if not entry:
        raise HTTPException(404, f"Type not found: {category}/{name}")

    result = dict(entry)
    # Parse schema from JSON string if needed
    if result.get("schema") and isinstance(result["schema"], str):
        import json
        result["schema"] = json.loads(result["schema"])
    return result


@router.post("")
async def register_type(
    request: Request,
    req: RegisterTypeRequest,
    user=Depends(require_admin),
):
    """Register a new custom type (admin only)."""
    registry = _get_registry(request)

    # Validate category is known
    valid_categories = {
        "actor_type", "actor_subtype", "edge_type", "operation_type",
        "lifecycle_state", "lifecycle_phase", "event_type", "severity",
        "capability_type", "action_type",
    }
    if req.category not in valid_categories:
        raise HTTPException(400, f"Invalid category. Must be one of: {sorted(valid_categories)}")

    # Check for duplicates
    if registry.is_valid(req.category, req.name, org_id=req.org_id):
        raise HTTPException(409, f"Type already exists: {req.category}/{req.name}")

    # For subtypes, validate parent exists
    if req.category == "actor_subtype" and req.parent_name:
        if not registry.is_valid("actor_type", req.parent_name):
            raise HTTPException(400, f"Parent actor_type not found: {req.parent_name}")

    try:
        type_id = registry.register_type(
            category=req.category,
            name=req.name,
            display_name=req.display_name,
            description=req.description,
            parent_name=req.parent_name,
            schema=req.schema,
            org_id=req.org_id,
            created_by=user.get("sub"),
            sort_order=req.sort_order,
            metadata=req.metadata,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to register type: {e}")

    return {
        "status": "success",
        "id": type_id,
        "category": req.category,
        "name": req.name,
    }


@router.patch("/{category}/{name}")
async def deprecate_type(
    request: Request,
    category: str,
    name: str,
    user=Depends(require_admin),
):
    """Deprecate a type (admin only). Deprecated types still validate but are hidden from UI."""
    registry = _get_registry(request)
    success = registry.deprecate_type(category, name)
    if not success:
        raise HTTPException(404, f"Type not found: {category}/{name}")
    return {"status": "success", "action": "deprecated", "type": f"{category}/{name}"}


@router.delete("/{category}/{name}")
async def delete_type(
    request: Request,
    category: str,
    name: str,
    user=Depends(require_admin),
):
    """Delete a user-created type (admin only). Builtin types cannot be deleted."""
    registry = _get_registry(request)

    # Check if it's builtin
    entry = registry.get_type_details(category, name)
    if entry and entry.get("is_builtin"):
        raise HTTPException(
            403,
            f"Cannot delete builtin type '{category}/{name}'. Use PATCH to deprecate instead."
        )

    success = registry.delete_type(category, name)
    if not success:
        raise HTTPException(404, f"Type not found: {category}/{name}")
    return {"status": "success", "action": "deleted", "type": f"{category}/{name}"}


@router.post("/validate-action-spec")
async def validate_action_spec(
    request: Request,
    req: ValidateActionSpecRequest,
    user=Depends(get_current_user),
):
    """Validate an action_spec against its registered JSON Schema."""
    registry = _get_registry(request)
    try:
        registry.validate_action_spec(req.action_type, req.action_spec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "valid", "action_type": req.action_type}
