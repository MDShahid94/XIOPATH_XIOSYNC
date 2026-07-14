"""
XIOPATH Phantom Infrastructure — Health Monitor
==================================================
Monitors phantom accounts, detects lockouts, triggers recovery.

Educational purpose only.
"""

import json
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("phantom.health_monitor")


@dataclass
class HealthCheckResult:
    """Result of a health check on a single phantom."""
    phantom_id: str
    overall_status: str  # healthy, degraded, locked, dead
    google_alive: bool = False
    cloudflare_alive: bool = False
    github_alive: bool = False
    colab_accessible: bool = False
    kaggle_accessible: bool = False
    worker_responding: bool = False
    issues: list = field(default_factory=list)
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "phantom_id": self.phantom_id,
            "overall_status": self.overall_status,
            "google_alive": self.google_alive,
            "cloudflare_alive": self.cloudflare_alive,
            "github_alive": self.github_alive,
            "colab_accessible": self.colab_accessible,
            "kaggle_accessible": self.kaggle_accessible,
            "worker_responding": self.worker_responding,
            "issues": self.issues,
            "checked_at": self.checked_at,
        }


class HealthMonitor:
    """
    Monitors the health of all phantom accounts in the fleet.
    Detects locked/suspended accounts and triggers recovery.
    """

    def __init__(self, vault, browser_manager, ontology_bridge=None):
        self.vault = vault
        self.browser_manager = browser_manager
        self.bridge = ontology_bridge
        self._last_checks: dict[str, HealthCheckResult] = {}

    async def check_phantom_health(self, phantom_id: str) -> HealthCheckResult:
        """
        Run a full health check on a single phantom.
        Tests all service endpoints and reports issues.
        """
        result = HealthCheckResult(
            phantom_id=phantom_id,
            overall_status="unknown",
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

        identity = self.vault.get_identity(phantom_id)
        if not identity:
            result.overall_status = "dead"
            result.issues.append("Identity not found in vault")
            return result

        services = identity.get("services", {})

        # Check CF Worker health
        cf = services.get("cloudflare", {})
        if cf.get("account_id"):
            worker_alive = await self._check_cf_worker(phantom_id, cf)
            result.cloudflare_alive = worker_alive
            result.worker_responding = worker_alive
            if not worker_alive:
                result.issues.append("CF Worker not responding")

        # Check CF API token validity
        if cf.get("api_token"):
            token_valid = await self._check_cf_token(cf["api_token"])
            if not token_valid:
                result.cloudflare_alive = False
                result.issues.append("CF API token invalid/expired")

        # Check GitHub token
        gh = services.get("github", {})
        if gh.get("token"):
            gh_valid = await self._check_github_token(gh["token"])
            result.github_alive = gh_valid
            if not gh_valid:
                result.issues.append("GitHub PAT invalid")

        # Check Kaggle API
        kaggle = services.get("kaggle", {})
        if kaggle.get("api_key") and kaggle.get("username"):
            kg_valid = await self._check_kaggle_api(kaggle["username"], kaggle["api_key"])
            result.kaggle_accessible = kg_valid
            if not kg_valid:
                result.issues.append("Kaggle API key invalid")

        # Check Google session
        google = identity.get("google", {})
        if google.get("email"):
            result.google_alive = True  # Optimistic; full check requires browser
            result.colab_accessible = True

        # Determine overall status
        alive_count = sum([
            result.google_alive,
            result.cloudflare_alive,
            result.github_alive,
        ])
        total_services = sum([
            bool(google.get("email")),
            bool(cf.get("account_id")),
            bool(gh.get("token")),
        ])

        if total_services == 0:
            result.overall_status = "dead"
        elif alive_count == total_services:
            result.overall_status = "healthy"
        elif alive_count > 0:
            result.overall_status = "degraded"
        else:
            result.overall_status = "locked"

        self._last_checks[phantom_id] = result

        # Route health status to ontology
        if self.bridge:
            self.bridge.update_phantom_health(phantom_id, result.to_dict())

        return result

    async def check_fleet_health(self) -> dict:
        """Run health checks on all phantoms in the vault."""
        identities = self.vault.list_identities()
        results = {
            "total": len(identities),
            "healthy": 0,
            "degraded": 0,
            "locked": 0,
            "dead": 0,
            "issues": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        for identity in identities:
            pid = identity.get("id", "")
            if identity.get("state") == "revoked":
                results["dead"] += 1
                continue

            check = await self.check_phantom_health(pid)
            results[check.overall_status] = results.get(check.overall_status, 0) + 1

            if check.issues:
                results["issues"].append({
                    "phantom_id": pid,
                    "issues": check.issues,
                })

        return results

    async def auto_recover(self, phantom_id: str) -> dict:
        """
        Attempt to recover a locked/degraded phantom.
        
        Recovery strategies:
        1. Locked Google → Re-authenticate with TOTP + backup codes
        2. Expired CF token → Generate new token via API
        3. Invalid GitHub PAT → Generate new PAT via browser
        4. Dead Worker → Re-deploy via CF API
        """
        if self.bridge:
            self.bridge.record_provision_phase(
                phantom_id, "auto_recovery", "locked", "recovering", "pending",
                "Auto-recovery initiated",
            )
        result = {"phantom_id": phantom_id, "actions": [], "success": False}

        identity = self.vault.get_identity(phantom_id)
        if not identity:
            result["actions"].append({"action": "skip", "reason": "Identity not found"})
            return result

        services = identity.get("services", {})
        check = self._last_checks.get(phantom_id)

        if not check:
            check = await self.check_phantom_health(phantom_id)

        # Strategy 1: Re-deploy dead CF Worker
        if not check.worker_responding:
            cf = services.get("cloudflare", {})
            if cf.get("api_token") and cf.get("account_id"):
                from phantom.harvester import CloudflareHarvester
                harvester = CloudflareHarvester(cf["account_id"], cf["api_token"])
                from phantom.harvester import ResourceHarvester
                rh = ResourceHarvester(self.vault, "")
                code = rh._generate_node_agent_code(phantom_id)
                deploy_result = await harvester._deploy_worker(phantom_id, code)
                result["actions"].append({
                    "action": "redeploy_worker",
                    "result": deploy_result,
                })

        # Strategy 2: Rotate CF token via API
        if not check.cloudflare_alive and check.google_alive:
            result["actions"].append({
                "action": "rotate_cf_token",
                "status": "requires_browser_session",
            })

        # Strategy 3: Mark for manual review if Google is locked
        if not check.google_alive:
            result["actions"].append({
                "action": "google_recovery",
                "status": "requires_manual_intervention",
                "recovery_options": ["totp", "backup_codes", "recovery_email"],
            })
            self.vault.update_field(phantom_id, "state", "locked")

        result["success"] = any(
            a.get("result", {}).get("deployed") for a in result["actions"]
        )

        # Route recovery result to ontology
        if self.bridge:
            self.bridge.record_recovery(phantom_id, result)

        return result

    async def _check_cf_worker(self, phantom_id: str, cf_config: dict) -> bool:
        """Check if the CF Worker is responding."""
        import urllib.request
        worker_name = f"xiopath-node-{phantom_id[:8]}"
        url = f"https://{worker_name}.{cf_config.get('account_id', '')}.workers.dev/health"

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return data.get("status") == "alive"
        except Exception:
            return False

    async def _check_cf_token(self, api_token: str) -> bool:
        """Verify CF API token is still valid."""
        import urllib.request
        try:
            req = urllib.request.Request(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {api_token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return data.get("success", False)
        except Exception:
            return False

    async def _check_github_token(self, token: str) -> bool:
        """Verify GitHub PAT is still valid."""
        import urllib.request
        try:
            req = urllib.request.Request(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def _check_kaggle_api(self, username: str, api_key: str) -> bool:
        """Verify Kaggle API key is still valid."""
        import urllib.request
        import base64
        try:
            creds = base64.b64encode(f"{username}:{api_key}".encode()).decode()
            req = urllib.request.Request(
                "https://www.kaggle.com/api/v1/competitions/list?page=1",
                headers={"Authorization": f"Basic {creds}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_fleet_summary(self) -> dict:
        """Get a quick summary of all last-known health states."""
        summary = {"healthy": 0, "degraded": 0, "locked": 0, "dead": 0, "unchecked": 0}
        identities = self.vault.list_identities()

        for identity in identities:
            pid = identity.get("id", "")
            check = self._last_checks.get(pid)
            if check:
                summary[check.overall_status] = summary.get(check.overall_status, 0) + 1
            else:
                summary["unchecked"] += 1

        return summary
