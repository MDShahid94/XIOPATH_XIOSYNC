"""
XIOPATH — Environment Executor (Phase M.4)
=============================================
Validates prerequisites, restores a marketplace environment,
and executes the workflow with the executor's own credentials.
"""

import json
import logging
from typing import Dict, List, Optional, Any

from core.tenant_context import extract_required_vault_keys

logger = logging.getLogger(__name__)


class EnvironmentExecutor:
    """
    Executes a marketplace environment bundle.
    
    Lifecycle:
    1. validate_prerequisites() — check executor has required vault keys
    2. prepare() — load env, remap vault refs, restore workflow graph
    3. execute() — run the workflow via WorkflowOrchestrator
    """

    def __init__(self, env_manager, secret_manager=None, orchestrator=None):
        self.env_manager = env_manager
        self.secrets = secret_manager
        self.orchestrator = orchestrator

    def validate_prerequisites(self, env_id: str, executor_id: str) -> Dict:
        """
        Check if the executor has all required credentials to run this environment.
        
        Returns:
            {
                "ready": bool,
                "missing_keys": [...],
                "environment": {...},
            }
        """
        env = self.env_manager.get_environment(env_id)
        if not env:
            return {"ready": False, "missing_keys": [], "error": "Environment not found"}

        # Parse manifest to find required vault keys
        manifest_data = json.loads(env.get("manifest", "{}"))
        required_keys = []

        # Check workflow_vars for vault:// references
        workflow_vars = manifest_data.get("workflow_vars", {})
        required_keys.extend(extract_required_vault_keys(workflow_vars))

        # Check components for vault:// references
        for comp in manifest_data.get("components", []):
            if isinstance(comp.get("data"), dict):
                required_keys.extend(extract_required_vault_keys(comp["data"]))

        required_keys = sorted(set(required_keys))

        # Check which keys the executor has in their vault
        missing_keys = []
        if self.secrets and required_keys:
            for key_name in required_keys:
                try:
                    val = self.secrets.get_secret(executor_id, key_name)
                    if val is None:
                        missing_keys.append(key_name)
                except Exception:
                    missing_keys.append(key_name)
        else:
            # No secret manager — assume all keys are missing if any are required
            missing_keys = required_keys

        return {
            "ready": len(missing_keys) == 0,
            "missing_keys": missing_keys,
            "required_keys": required_keys,
            "environment_id": env_id,
            "environment_type": env.get("environment_type", "unknown"),
        }

    async def execute(
        self,
        env_id: str,
        executor_id: str,
        user_context: Dict = None,
    ) -> Dict:
        """
        Execute a marketplace environment:
        1. Load bundle from bundles table
        2. Validate executor has required vault keys
        3. Extract workflow intent from manifest
        4. Execute via WorkflowOrchestrator (if available) or return prepared state
        
        Returns:
            {"status": "completed"|"failed"|"prepared", "result": ..., "error": ...}
        """
        # Step 1: Validate prerequisites
        prereq = self.validate_prerequisites(env_id, executor_id)
        if not prereq["ready"] and prereq.get("missing_keys"):
            return {
                "status": "failed",
                "error": "Missing required vault keys",
                "missing_keys": prereq["missing_keys"],
            }

        # Step 2: Load environment
        env = self.env_manager.get_environment(env_id)
        if not env:
            return {"status": "failed", "error": "Environment not found"}

        manifest_data = json.loads(env.get("manifest", "{}"))

        # Step 3: Extract workflow intent from components
        workflow_intent = None
        workflow_url = None
        for comp in manifest_data.get("components", []):
            if comp.get("component_type") == "workflow_graph":
                workflow_intent = comp.get("metadata", {}).get("intent")
                workflow_url = comp.get("metadata", {}).get("url")
                break

        if not workflow_intent:
            # No workflow graph — just return the prepared environment
            return {
                "status": "prepared",
                "environment_id": env_id,
                "manifest": manifest_data,
                "message": "Environment loaded but no workflow graph found to execute",
            }

        # Step 4: Execute via orchestrator
        if self.orchestrator:
            try:
                context = user_context or {}
                # Merge workflow vars (with executor's vault namespace)
                context.update(manifest_data.get("workflow_vars", {}))

                exec_id = await self.orchestrator.start_workflow(
                    workflow_intent, context
                )
                return {
                    "status": "started",
                    "execution_id": exec_id,
                    "environment_id": env_id,
                    "workflow_intent": workflow_intent,
                }
            except Exception as e:
                logger.error(f"Environment execution failed: {e}")
                return {"status": "failed", "error": str(e)}
        else:
            # No orchestrator — return prepared state
            return {
                "status": "prepared",
                "environment_id": env_id,
                "workflow_intent": workflow_intent,
                "workflow_url": workflow_url,
                "message": "Environment prepared, orchestrator not available",
            }

    def get_execution_context(self, env_id: str, executor_id: str) -> Dict:
        """
        Build the full execution context for an environment,
        resolving vault:// references against the executor's vault.
        """
        env = self.env_manager.get_environment(env_id)
        if not env:
            return {}

        manifest_data = json.loads(env.get("manifest", "{}"))
        workflow_vars = manifest_data.get("workflow_vars", {})

        # Resolve vault:// references
        resolved = {}
        for key, value in workflow_vars.items():
            if isinstance(value, str) and value.startswith("vault://"):
                vault_key = value.replace("vault://", "").strip()
                if self.secrets:
                    try:
                        resolved[key] = self.secrets.get_secret(executor_id, vault_key)
                    except Exception:
                        resolved[key] = None
                else:
                    resolved[key] = f"<unresolved:{vault_key}>"
            else:
                resolved[key] = value

        return resolved
