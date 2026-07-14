"""
XIOPATH — Execution Policy Manager (Phase 7)
================================================
Sandboxing rules that govern what a workflow/action can do at runtime.

Policies control:
  - Network access (allow/block specific domains)
  - Filesystem access
  - Subprocess execution
  - Browser automation
  - LLM invocation
  - Step count, duration, and memory limits
"""
import json
import logging
from typing import Optional, List, Dict

from sqlalchemy import text

logger = logging.getLogger("PolicyManager")


def _uuid7() -> str:
    import uuid
    try:
        return str(uuid.uuid7())
    except AttributeError:
        return str(uuid.uuid4())


class PolicyManager:
    """Manages execution policies for sandboxed workflow execution."""

    def __init__(self, db):
        self.db = db

    def get_policy(self, policy_id: str) -> Optional[dict]:
        """Get a policy by ID."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM execution_policies WHERE id = :id"),
                {"id": policy_id}
            ).mappings().first()
            return dict(row) if row else None

    def get_policy_by_name(self, name: str) -> Optional[dict]:
        """Get a policy by name."""
        with self.db.SessionLocal() as session:
            row = session.execute(
                text("SELECT * FROM execution_policies WHERE name = :name"),
                {"name": name}
            ).mappings().first()
            return dict(row) if row else None

    def list_policies(self, org_id: Optional[str] = None) -> List[dict]:
        """List all active policies, optionally filtered by org."""
        conditions = ["state = 'active'"]
        params = {}
        if org_id:
            conditions.append("(org_id = :org_id OR is_builtin = 1)")
            params["org_id"] = org_id
        where = " AND ".join(conditions)

        with self.db.SessionLocal() as session:
            rows = session.execute(
                text(f"SELECT * FROM execution_policies WHERE {where} ORDER BY name"),
                params
            ).mappings().all()
            return [dict(r) for r in rows]

    def create_policy(
        self,
        name: str,
        description: Optional[str] = None,
        allow_network: bool = False,
        allow_filesystem: bool = False,
        allow_subprocess: bool = False,
        allow_browser: bool = True,
        allow_llm: bool = True,
        max_steps: int = 100,
        max_duration_ms: int = 600000,
        max_memory_mb: int = 512,
        max_retries: int = 3,
        allowed_domains: Optional[list] = None,
        blocked_domains: Optional[list] = None,
        allowed_action_types: Optional[list] = None,
        org_id: Optional[str] = None,
    ) -> str:
        """Create a custom execution policy. Returns policy ID."""
        from datetime import datetime, timezone
        policy_id = _uuid7()
        now = datetime.now(timezone.utc).isoformat()

        row = {
            "id": policy_id,
            "name": name,
            "description": description,
            "allow_network": allow_network,
            "allow_filesystem": allow_filesystem,
            "allow_subprocess": allow_subprocess,
            "allow_browser": allow_browser,
            "allow_llm": allow_llm,
            "max_steps": max_steps,
            "max_duration_ms": max_duration_ms,
            "max_memory_mb": max_memory_mb,
            "max_retries": max_retries,
            "allowed_domains": json.dumps(allowed_domains) if allowed_domains else None,
            "blocked_domains": json.dumps(blocked_domains) if blocked_domains else None,
            "allowed_action_types": json.dumps(allowed_action_types) if allowed_action_types else None,
            "is_builtin": False,
            "org_id": org_id,
            "state": "active",
            "created_at": now,
        }

        with self.db.safe_transaction() as session:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            session.execute(text(f"INSERT INTO execution_policies ({cols}) VALUES ({placeholders})"), row)

        return policy_id

    def check_permission(self, policy_id: str, permission: str) -> bool:
        """Check if a specific permission is allowed by a policy."""
        policy = self.get_policy(policy_id)
        if not policy:
            return False
        return bool(policy.get(f"allow_{permission}", False))

    def check_domain(self, policy_id: str, domain: str) -> bool:
        """Check if a domain is allowed by a policy."""
        policy = self.get_policy(policy_id)
        if not policy:
            return False

        # Check blocked domains
        blocked = policy.get("blocked_domains")
        if blocked:
            if isinstance(blocked, str):
                blocked = json.loads(blocked)
            for pattern in blocked:
                if pattern.startswith("*."):
                    if domain.endswith(pattern[1:]):
                        return False
                elif domain == pattern:
                    return False

        # Check allowed domains (if specified, only these are allowed)
        allowed = policy.get("allowed_domains")
        if allowed:
            if isinstance(allowed, str):
                allowed = json.loads(allowed)
            for pattern in allowed:
                if pattern.startswith("*."):
                    if domain.endswith(pattern[1:]):
                        return True
                elif domain == pattern:
                    return True
            return False  # Not in allowed list

        return True  # No allowed list = all allowed (minus blocked)

    def validate_execution(self, policy_id: str, action_type: str, step_count: int, domain: Optional[str] = None) -> Dict:
        """
        Validate whether an execution step is allowed by the policy.
        Returns {"allowed": bool, "reason": str}.
        """
        policy = self.get_policy(policy_id)
        if not policy:
            return {"allowed": False, "reason": "Policy not found"}

        # Check step limit
        max_steps = policy.get("max_steps", 100)
        if step_count > max_steps:
            return {"allowed": False, "reason": f"Step limit exceeded ({step_count}/{max_steps})"}

        # Check action type permissions
        action_perms = {
            "browser": "allow_browser",
            "api_call": "allow_network",
            "script": "allow_subprocess",
            "llm_prompt": "allow_llm",
        }
        perm_key = action_perms.get(action_type)
        if perm_key and not policy.get(perm_key, False):
            return {"allowed": False, "reason": f"Action type '{action_type}' not allowed by policy"}

        # Check allowed action types list
        allowed_types = policy.get("allowed_action_types")
        if allowed_types:
            if isinstance(allowed_types, str):
                allowed_types = json.loads(allowed_types)
            if action_type not in allowed_types:
                return {"allowed": False, "reason": f"Action type '{action_type}' not in allowed list"}

        # Check domain
        if domain and not self.check_domain(policy.get("id"), domain):
            return {"allowed": False, "reason": f"Domain '{domain}' blocked by policy"}

        return {"allowed": True, "reason": "OK"}
