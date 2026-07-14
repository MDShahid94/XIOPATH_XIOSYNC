"""
Admin Configuration Router
============================
Runtime-adjustable security and system parameters.
All endpoints require admin role.

This provides the "adjust from admin panel" capability requested by the user
for rate limits, SSRF allowlists, and plugin execution settings.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from api.routers.auth import require_admin
from api.middleware.rate_limiter import RateLimitMiddleware
import logging

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = logging.getLogger(__name__)


# ==============================================================================
# Runtime Security Configuration (in-memory, persists until restart)
# ==============================================================================

class SecurityConfig:
    """Centralized runtime-adjustable security configuration."""

    # Rate limiting
    general_rpm: int = 60
    auth_rpm: int = 10
    agent_rpm: int = 5
    sync_rpm: int = 30

    # SSRF protection
    block_private_ips: bool = True
    blocked_hosts: List[str] = ["169.254.169.254", "metadata.google.internal"]
    allowed_domains: List[str] = []  # Empty = allow all public domains

    # Plugin execution
    allowed_plugin_extensions: List[str] = [".py", ".sh"]
    plugin_timeout_seconds: int = 30

    @classmethod
    def to_dict(cls) -> dict:
        return {
            "rate_limits": {
                "general_rpm": cls.general_rpm,
                "auth_rpm": cls.auth_rpm,
                "agent_rpm": cls.agent_rpm,
                "sync_rpm": cls.sync_rpm,
            },
            "ssrf_protection": {
                "block_private_ips": cls.block_private_ips,
                "blocked_hosts": cls.blocked_hosts,
                "allowed_domains": cls.allowed_domains,
            },
            "plugin_execution": {
                "allowed_extensions": cls.allowed_plugin_extensions,
                "timeout_seconds": cls.plugin_timeout_seconds,
            },
        }

    @classmethod
    def update(cls, **kwargs):
        for key, value in kwargs.items():
            if hasattr(cls, key) and value is not None:
                setattr(cls, key, value)
                logger.info(f"SecurityConfig updated: {key}={value}")


# ==============================================================================
# Pydantic Models for Config Updates
# ==============================================================================

class RateLimitUpdate(BaseModel):
    general_rpm: Optional[int] = Field(None, ge=1, le=1000, description="General endpoint RPM")
    auth_rpm: Optional[int] = Field(None, ge=1, le=100, description="Auth endpoint RPM")
    agent_rpm: Optional[int] = Field(None, ge=1, le=50, description="Agent execution RPM")
    sync_rpm: Optional[int] = Field(None, ge=1, le=200, description="Sync endpoint RPM")


class SSRFUpdate(BaseModel):
    block_private_ips: Optional[bool] = None
    blocked_hosts: Optional[List[str]] = None
    allowed_domains: Optional[List[str]] = None


class PluginUpdate(BaseModel):
    allowed_extensions: Optional[List[str]] = None
    timeout_seconds: Optional[int] = Field(None, ge=5, le=300)


# ==============================================================================
# Endpoints
# ==============================================================================

@router.get("/config")
async def get_config(user: dict = Depends(require_admin)):
    """Returns the current runtime security configuration."""
    return {"status": "success", "config": SecurityConfig.to_dict()}


@router.put("/config/rate-limits")
async def update_rate_limits(update: RateLimitUpdate, user: dict = Depends(require_admin)):
    """Update rate limiting thresholds at runtime."""
    updates = update.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    SecurityConfig.update(**updates)
    # Propagate to middleware
    RateLimitMiddleware.update_config(**updates)

    return {"status": "success", "updated": updates, "config": SecurityConfig.to_dict()["rate_limits"]}


@router.put("/config/ssrf")
async def update_ssrf_config(update: SSRFUpdate, user: dict = Depends(require_admin)):
    """Update SSRF protection configuration at runtime."""
    updates = {}
    if update.block_private_ips is not None:
        updates["block_private_ips"] = update.block_private_ips
    if update.blocked_hosts is not None:
        updates["blocked_hosts"] = update.blocked_hosts
    if update.allowed_domains is not None:
        updates["allowed_domains"] = update.allowed_domains

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    SecurityConfig.update(**updates)
    return {"status": "success", "updated": updates, "config": SecurityConfig.to_dict()["ssrf_protection"]}


@router.put("/config/plugins")
async def update_plugin_config(update: PluginUpdate, user: dict = Depends(require_admin)):
    """Update plugin execution configuration at runtime."""
    updates = {}
    if update.allowed_extensions is not None:
        updates["allowed_plugin_extensions"] = update.allowed_extensions
    if update.timeout_seconds is not None:
        updates["plugin_timeout_seconds"] = update.timeout_seconds

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    SecurityConfig.update(**updates)
    return {"status": "success", "updated": updates, "config": SecurityConfig.to_dict()["plugin_execution"]}
