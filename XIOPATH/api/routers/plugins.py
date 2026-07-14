"""
XIOPATH — Plugin API (Phase E.1)
===================================
REST endpoints for plugin registry: list, detail, enable/disable, execute.
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from api.routers.auth import get_current_user

router = APIRouter(prefix="/plugins", tags=["Plugins"])
logger = logging.getLogger(__name__)


class PluginActionRequest(BaseModel):
    action_params: dict = Field(default_factory=dict)
    workflow_vars: dict = Field(default_factory=dict)


def _get_registry(request: Request):
    registry = getattr(request.app.state, "plugin_registry", None)
    if not registry:
        from core.plugin_registry import PluginRegistry
        registry = PluginRegistry()
        registry.load_all()
        request.app.state.plugin_registry = registry
    return registry


@router.get("/")
async def list_plugins(
    request: Request,
    state: Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List all registered plugins."""
    registry = _get_registry(request)
    if category:
        plugins = registry.get_by_category(category)
    else:
        plugins = registry.list_plugins(state=state)
    return {
        "plugins": plugins,
        "total": len(plugins),
        "enabled": registry.enabled_count,
    }


@router.get("/{name}")
async def get_plugin(name: str, request: Request, user: dict = Depends(get_current_user)):
    """Get a single plugin's details."""
    registry = _get_registry(request)
    plugin = registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.post("/{name}/enable")
async def enable_plugin(name: str, request: Request, user: dict = Depends(get_current_user)):
    """Enable a plugin for execution."""
    registry = _get_registry(request)
    if registry.enable(name):
        return {"status": "enabled", "plugin": name}
    raise HTTPException(status_code=400, detail=f"Cannot enable plugin '{name}'")


@router.post("/{name}/disable")
async def disable_plugin(name: str, request: Request, user: dict = Depends(get_current_user)):
    """Disable a plugin."""
    registry = _get_registry(request)
    if registry.disable(name):
        return {"status": "disabled", "plugin": name}
    raise HTTPException(status_code=400, detail=f"Cannot disable plugin '{name}'")


@router.post("/{name}/reload")
async def reload_plugin(name: str, request: Request, user: dict = Depends(get_current_user)):
    """Unload and re-load a plugin."""
    registry = _get_registry(request)
    registry.unload(name)
    if registry.load(name) and registry.enable(name):
        return {"status": "reloaded", "plugin": name}
    raise HTTPException(status_code=500, detail=f"Failed to reload plugin '{name}'")


@router.post("/discover")
async def discover_plugins(request: Request, user: dict = Depends(get_current_user)):
    """Re-scan the plugins directory for new plugins."""
    registry = _get_registry(request)
    discovered = registry.discover()
    return {"discovered": discovered, "total": registry.count}
