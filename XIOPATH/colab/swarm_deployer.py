"""
Swarm Deployer — Autonomous Colab worker swarm orchestrator.

Spawns multiple Colab worker instances by:
  1. Launching a stealth browser (using the Mac's/deployer's Chrome profile)
  2. Navigating to the pre-created Colab notebook on Drive
  3. Using colab_automator to inject + run worker bootstrap code
  4. Repeating for each worker in the swarm configuration

"No Physical Hands" — the entire deployment is autonomous.

Usage:
    deployer = SwarmDeployer()
    deployer.deploy_swarm([
        {"worker_id": "bot_1", "exit_node": "100.98.229.77"},
        {"worker_id": "bot_2", "exit_node": "100.115.42.33"},
    ])
"""

import os
import sys
import time
import logging
import json
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("swarm_deployer")

# Hardcoded per user specification
from .notebook_template import (
    COLAB_NOTEBOOK_URL,
    DRIVE_PROFILES_FOLDER_ID,
    generate_bootstrap,
)


@dataclass
class WorkerConfig:
    """Configuration for a single Colab worker."""
    worker_id: str
    exit_node: str = ""
    email: str = ""
    central_ws: str = "ws://localhost:8000/api/v1/agent/worker-stream"
    repo_url: str = "https://github.com/MDShahid94/Browser-Automation-Test.git"
    drive_folder_id: str = DRIVE_PROFILES_FOLDER_ID


@dataclass
class SwarmResult:
    """Result of deploying a single worker."""
    worker_id: str
    success: bool
    error: Optional[str] = None
    duration_seconds: float = 0.0


class SwarmDeployer:
    """
    Autonomous swarm deployment orchestrator.

    Uses the deployer's local Chrome browser (with signed-in Google account)
    to navigate to Colab and spawn worker instances.
    """

    def __init__(
        self,
        colab_url: str = COLAB_NOTEBOOK_URL,
        headless: bool = False,
        deployer_email: str = "1x2xx3xxx4xxxx5xxxxx6xxxxxx789@gmail.com",
    ):
        """
        Args:
            colab_url: URL of the pre-created Colab notebook template.
            headless: Whether to run the deployer browser headless.
            deployer_email: The Google account used in the local Chrome
                           browser to access Colab (NOT a worker account).
        """
        self.colab_url = colab_url
        self.headless = headless
        self.deployer_email = deployer_email
        self.results: list[SwarmResult] = []

    def deploy_swarm(self, workers: list[dict | WorkerConfig]) -> list[SwarmResult]:
        """
        Deploy multiple workers to Colab sequentially.

        Args:
            workers: List of worker configurations. Each can be a dict
                     or WorkerConfig instance.

        Returns:
            List of SwarmResult for each worker.
        """
        configs = []
        for w in workers:
            if isinstance(w, dict):
                configs.append(WorkerConfig(**w))
            else:
                configs.append(w)

        logger.info(f"{'=' * 60}")
        logger.info(f"🐝 SWARM DEPLOYMENT — {len(configs)} workers")
        logger.info(f"   Notebook: {self.colab_url}")
        logger.info(f"   Deployer: {self.deployer_email}")
        logger.info(f"{'=' * 60}")

        self.results = []

        for i, config in enumerate(configs):
            logger.info(f"\n{'─' * 40}")
            logger.info(f"🤖 Worker {i + 1}/{len(configs)}: {config.worker_id}")
            logger.info(f"{'─' * 40}")

            result = self._deploy_single_worker(config)
            self.results.append(result)

            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            logger.info(f"{status} — {config.worker_id} "
                         f"({result.duration_seconds:.1f}s)")

            if result.error:
                logger.error(f"   Error: {result.error}")

            # Brief pause between deployments
            if i < len(configs) - 1:
                logger.info("⏳ Waiting 10s before next deployment...")
                time.sleep(10)

        # ── Summary ──────────────────────────────────────────
        succeeded = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)
        logger.info(f"\n{'=' * 60}")
        logger.info(f"🐝 SWARM DEPLOYMENT COMPLETE")
        logger.info(f"   ✅ Succeeded: {succeeded}/{len(configs)}")
        logger.info(f"   ❌ Failed:    {failed}/{len(configs)}")
        logger.info(f"{'=' * 60}")

        return self.results

    def _deploy_single_worker(self, config: WorkerConfig) -> SwarmResult:
        """
        Deploy a single worker: create browser → open Colab → inject → run.
        """
        start_time = time.time()
        driver = None

        try:
            # ── Create stealth browser ───────────────────────
            from .stealth_browser import StealthBrowser

            browser = StealthBrowser(
                headless=self.headless,
                exit_node_ip=config.exit_node,
            )
            driver = browser.start()

            if not driver:
                return SwarmResult(
                    worker_id=config.worker_id,
                    success=False,
                    error="Failed to start stealth browser",
                    duration_seconds=time.time() - start_time,
                )

            # ── Generate bootstrap code ──────────────────────
            bootstrap_code = generate_bootstrap(
                worker_id=config.worker_id,
                exit_node=config.exit_node,
                central_ws=config.central_ws,
                repo_url=config.repo_url,
                drive_folder_id=config.drive_folder_id,
            )

            # ── Run Colab automator ──────────────────────────
            from .colab_automator import run_colab_notebook

            success = run_colab_notebook(
                driver=driver,
                colab_url=self.colab_url,
                bootstrap_code=bootstrap_code,
                max_rounds=8,
                cell_timeout=3600,
            )

            return SwarmResult(
                worker_id=config.worker_id,
                success=success,
                duration_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"❌ Deployment failed for {config.worker_id}: {e}")
            import traceback
            traceback.print_exc()

            return SwarmResult(
                worker_id=config.worker_id,
                success=False,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


# ═══════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════

def main():
    """CLI entry point for swarm deployment."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Example: deploy 3 workers
    deployer = SwarmDeployer(headless=False)

    deployer.deploy_swarm([
        {"worker_id": "bot_1", "exit_node": ""},
        {"worker_id": "bot_2", "exit_node": ""},
        {"worker_id": "bot_3", "exit_node": ""},
    ])


if __name__ == "__main__":
    main()
