"""
XIOPATH — Tenant Context (Phase M.3)
=======================================
Tracks the current execution tenant (user/creator) for multi-tenancy.
Used by middleware and downstream handlers to scope data access.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """
    Represents the current execution tenant.
    
    Injected by TenantScopeMiddleware into request.state.tenant.
    Used downstream to:
    - Scope database queries to the user's data
    - Resolve vault:// references to the user's vault namespace
    - Enforce creator/user credential boundaries
    """
    user_id: str
    role: str = "user"                      # "creator" | "user" | "admin"
    vault_namespace: str = ""               # "vault_{user_id}"
    organization_id: Optional[str] = None   # Explicit active organization, when selected
    environment_id: Optional[str] = None    # If executing within an environment
    session_id: Optional[str] = None

    def __post_init__(self):
        if not self.vault_namespace:
            self.vault_namespace = f"vault_{self.user_id}"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_creator(self) -> bool:
        return self.role in ("creator", "admin")

    def can_publish(self) -> bool:
        """Check if this tenant can publish to the marketplace."""
        return self.role in ("creator", "admin")

    def can_manage_listing(self, creator_id: str) -> bool:
        """Check if this tenant can modify/delete a listing."""
        return self.is_admin or self.user_id == creator_id

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "vault_namespace": self.vault_namespace,
            "organization_id": self.organization_id,
            "environment_id": self.environment_id,
            "is_admin": self.is_admin,
            "is_creator": self.is_creator,
        }


def remap_vault_references(data: Dict, executor_namespace: str) -> Dict:
    """
    M.3: Recursively scan a dict and remap all vault:// references
    to the executor's vault namespace.
    
    Creator's vault://login_email → stays vault://login_email
    (same key name — but resolved against executor's vault at runtime)
    
    This function doesn't change the key names — it ensures that
    when the executor runs the workflow, their vault is used for resolution,
    not the creator's.
    
    Returns a copy of the data with vault refs annotated.
    """
    import copy
    result = copy.deepcopy(data)
    _remap_recursive(result, executor_namespace)
    return result


def _remap_recursive(obj, namespace: str):
    """Recursively walk and annotate vault:// references with executor namespace."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and value.startswith("vault://"):
                # Extract the key name and prefix with namespace for tenant isolation
                vault_key = value.replace("vault://", "").strip()
                # Only annotate if not already namespaced
                if "/" not in vault_key:
                    obj[key] = f"vault://{namespace}/{vault_key}"
            elif isinstance(value, (dict, list)):
                _remap_recursive(value, namespace)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _remap_recursive(item, namespace)


def extract_required_vault_keys(data: Dict) -> list:
    """Extract all vault:// key names from a data structure."""
    keys = set()
    _extract_vault_keys_recursive(data, keys)
    return sorted(keys)


def _extract_vault_keys_recursive(obj, keys: set):
    if isinstance(obj, dict):
        for value in obj.values():
            if isinstance(value, str) and value.startswith("vault://"):
                keys.add(value.replace("vault://", "").strip())
            elif isinstance(value, (dict, list)):
                _extract_vault_keys_recursive(value, keys)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _extract_vault_keys_recursive(item, keys)
