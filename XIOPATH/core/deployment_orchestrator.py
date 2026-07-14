"""
XIOPATH Orchestrator - Deployment Orchestrator (Phase 21)
=============================================================
High-level orchestrator that deploys swarm workers to Google Colab
by executing browser-automated workflow graphs.

Loads DAG definitions from data/graphs/, resolves swarm profiles,
injects runtime variables, and drives the AgentLoop to execute
the full deployment sequence.
"""

import asyncio
import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.agent_loop import AgentLoop
from core.gemini_engine import GeminiEngine
from core.memory_manager import MemoryManager

console = Console()

# ─── Constants ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GRAPHS_DIR = DATA_DIR / "graphs"
SCRIPTS_DIR = DATA_DIR / "scripts"
PROFILES_FILE = DATA_DIR / "swarm_profiles.json"
DLQ_DIR = DATA_DIR / "dlq"


class DeploymentOrchestrator:
    """
    Orchestrates the deployment of swarm workers to Google Colab.
    
    Reads workflow DAGs from data/graphs/, resolves available browser profiles
    from data/swarm_profiles.json, injects runtime variables (bootstrap script,
    server URL), seeds the action memory, and drives the AgentLoop through
    the full deployment graph.
    """

    def __init__(self, graph_name: str, profile_mail_id: str = None, server_url: str = None):
        self.graph_name = graph_name
        self.profile_mail_id = profile_mail_id
        self.server_url = server_url or "ws://localhost:8000/api/v1/agent/worker-stream"
        self.deploy_logs: List[str] = []
        self.start_time = None

    # ─── Graph Loading ──────────────────────────────────────────────────

    def load_graph(self) -> Dict[str, Any]:
        """Reads the workflow DAG from data/graphs/{graph_name}.json."""
        graph_path = GRAPHS_DIR / f"{self.graph_name}.json"
        if not graph_path.exists():
            raise FileNotFoundError(f"Graph not found: {graph_path}")

        with open(graph_path, "r") as f:
            graph_data = json.load(f)

        self._log("📊", f"Loaded graph: {graph_data.get('name', self.graph_name)} v{graph_data.get('version', '?')}")
        return graph_data

    # ─── Profile Management ─────────────────────────────────────────────

    def load_swarm_profiles(self) -> List[Dict[str, Any]]:
        """Reads data/swarm_profiles.json and returns the profiles list."""
        if not PROFILES_FILE.exists():
            raise FileNotFoundError(f"Swarm profiles not found: {PROFILES_FILE}")

        with open(PROFILES_FILE, "r") as f:
            data = json.load(f)

        profiles = data.get("profiles", [])
        self._log("👥", f"Loaded {len(profiles)} swarm profile(s)")
        return profiles

    def get_available_profile(self) -> Optional[Dict[str, Any]]:
        """
        Returns the first active profile not deployed within the
        bootstrap_skip_if_deployed_within_hours window.
        """
        with open(PROFILES_FILE, "r") as f:
            data = json.load(f)

        skip_hours = data.get("bootstrap_skip_if_deployed_within_hours", 6)
        profiles = data.get("profiles", [])
        cutoff = datetime.utcnow() - timedelta(hours=skip_hours)

        for profile in profiles:
            if profile.get("status") != "active":
                continue

            last_deployed = profile.get("last_deployed")
            if last_deployed is None:
                self._log("✅", f"Available profile: {profile['mail_id']} (never deployed)")
                return profile

            try:
                deployed_dt = datetime.fromisoformat(last_deployed)
                if deployed_dt < cutoff:
                    self._log("✅", f"Available profile: {profile['mail_id']} (last deployed: {last_deployed})")
                    return profile
            except (ValueError, TypeError):
                # Invalid timestamp — treat as available
                self._log("⚠️", f"Profile {profile['mail_id']} has invalid last_deployed, treating as available")
                return profile

        self._log("❌", f"No available profiles (all deployed within {skip_hours}h)")
        return None

    def _update_profile_timestamp(self, mail_id: str):
        """Updates the last_deployed timestamp for a profile in swarm_profiles.json."""
        with open(PROFILES_FILE, "r") as f:
            data = json.load(f)

        for profile in data.get("profiles", []):
            if profile["mail_id"] == mail_id:
                profile["last_deployed"] = datetime.utcnow().isoformat()
                break

        with open(PROFILES_FILE, "w") as f:
            json.dump(data, f, indent=4)

        self._log("📝", f"Updated last_deployed for {mail_id}")

    # ─── Graph Seeding ──────────────────────────────────────────────────

    def seed_graph(self, graph: Dict[str, Any], memory: MemoryManager):
        """
        Walks the DAG recursively and calls memory.save_new_action for each node.
        Seeds the entire workflow into the agent's tiered memory system.
        """
        root_node = graph.get("root_node", graph)
        root_domain = graph.get("root_domain", "colab.research.google.com")
        self._seed_node_recursive(root_node, root_domain, memory, previous_node_id=None)
        self._log("🧠", "Graph seeded into agent memory")

    def _seed_node_recursive(self, node: Dict, domain: str, memory: MemoryManager, previous_node_id: Optional[str]):
        """Recursively seeds a single node and its children."""
        node_domain = node.get("domain", domain)
        url = f"https://{node_domain}"

        face_value = node.get("face_value", {
            "description": node.get("intent", ""),
            "label_words": []
        })
        place_value = node.get("place_value", {})
        action_type = node.get("action_type", "click")
        action_params = node.get("action_params", {})
        previous_intent = node.get("previous_intent")
        volatility_type = node.get("volatility_type", "static")
        output_var = node.get("output_var")
        execution_mode = node.get("execution_mode", "sequential")

        memory.save_new_action(
            url=url,
            intent=node["intent"],
            face_value=face_value.copy(),
            place_value=place_value.copy(),
            action_type=action_type,
            action_params=action_params.copy(),
            previous_intent=previous_intent,
            context_hash="default",
            visibility="public",
            volatility_type=volatility_type,
            output_var=output_var,
            previous_node_id=previous_node_id,
            execution_mode=execution_mode
        )

        current_node_id = node.get("id", node["intent"])

        # Recurse into next_nodes
        for next_node in node.get("next_nodes", []):
            self._seed_node_recursive(next_node, domain, memory, previous_node_id=current_node_id)

    # ─── Runtime Variable Injection ─────────────────────────────────────

    def inject_runtime_variables(self, graph: Dict[str, Any]):
        """
        Walks the DAG recursively and replaces template placeholders:
        - {{COLAB_WORKER_SCRIPT}} → actual content of data/scripts/colab_worker.py
        - {{SERVER_URL}} → configured server URL
        """
        # Load the worker script
        worker_script_path = SCRIPTS_DIR / "colab_worker.py"
        if not worker_script_path.exists():
            raise FileNotFoundError(f"Worker script not found: {worker_script_path}")

        with open(worker_script_path, "r") as f:
            worker_script = f.read()

        root_node = graph.get("root_node", graph)
        replacements = {
            "{{COLAB_WORKER_SCRIPT}}": worker_script,
            "{{SERVER_URL}}": self.server_url,
        }

        replaced_count = self._inject_recursive(root_node, replacements)
        self._log("💉", f"Injected {replaced_count} runtime variable(s) into graph")

    def _inject_recursive(self, node: Dict, replacements: Dict[str, str]) -> int:
        """Recursively walks the DAG and replaces placeholders in action_params."""
        count = 0
        action_params = node.get("action_params", {})

        for key, value in action_params.items():
            if isinstance(value, str):
                for placeholder, replacement in replacements.items():
                    if placeholder in value:
                        action_params[key] = value.replace(placeholder, replacement)
                        count += 1
                        value = action_params[key]  # Update for chained replacements

        for next_node in node.get("next_nodes", []):
            count += self._inject_recursive(next_node, replacements)

        return count

    # ─── DLQ Writer ─────────────────────────────────────────────────────

    def _write_to_dlq(self, graph: Dict, profile: Dict, reason: str):
        """Writes a failed deployment to the Dead-Letter Queue."""
        DLQ_DIR.mkdir(parents=True, exist_ok=True)
        dlq_file = DLQ_DIR / f"dlq_deploy_{int(time.time())}.json"

        dlq_data = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.utcnow().isoformat(),
            "graph_name": self.graph_name,
            "profile_mail_id": profile.get("mail_id", "unknown"),
            "server_url": self.server_url,
            "reason": reason,
            "deploy_logs": self.deploy_logs,
            "graph_snapshot": {
                "id": graph.get("id"),
                "name": graph.get("name"),
                "version": graph.get("version")
            }
        }

        with open(dlq_file, "w") as f:
            json.dump(dlq_data, f, indent=4)

        self._log("📥", f"Failed deployment written to DLQ: {dlq_file.name}")

    # ─── Main Deploy Method ─────────────────────────────────────────────

    async def deploy(self) -> Dict[str, Any]:
        """
        Main deployment method. Orchestrates the full deployment lifecycle:
        1. Load graph
        2. Resolve available profile
        3. Inject runtime variables
        4. Seed graph into memory
        5. Create and drive AgentLoop through the workflow
        6. Update profile timestamp on success / write DLQ on failure
        """
        self.start_time = time.time()
        self._print_banner()

        try:
            # ── Step 1: Load Graph ──────────────────────────────────────
            graph = self.load_graph()

            # ── Step 2: Resolve Profile ─────────────────────────────────
            if self.profile_mail_id:
                profiles = self.load_swarm_profiles()
                profile = next(
                    (p for p in profiles if p["mail_id"] == self.profile_mail_id),
                    None
                )
                if not profile:
                    raise ValueError(f"Profile not found: {self.profile_mail_id}")
                self._log("🎯", f"Using specified profile: {self.profile_mail_id}")
            else:
                profile = self.get_available_profile()
                if not profile:
                    return self._result(False, "No available profiles for deployment")

            session_id = f"deploy_{profile['mail_id'].split('@')[0]}_{int(time.time())}"

            # ── Step 3: Inject Runtime Variables ────────────────────────
            self.inject_runtime_variables(graph)

            # ── Step 4: Seed Graph into Memory ──────────────────────────
            memory = MemoryManager(session_id=session_id)
            self.seed_graph(graph, memory)

            # ── Step 5: Create LLM and Agent ────────────────────────────
            from core.smart_llm import SmartGeminiLLM
            llm = SmartGeminiLLM()

            agent = AgentLoop(
                session_id=session_id,
                llm=GeminiEngine(),
                enable_screenshots=True,
                record_video=True
            )
            self._log("🤖", f"Agent created with session: {session_id}")

            # ── Step 6: Start Agent and Navigate ────────────────────────
            await agent.start()
            await agent.browser.page.goto("about:blank")
            self._log("🌐", "Browser launched and ready")

            # ── Step 7: Execute Workflow Graph ──────────────────────────
            root_node = graph.get("root_node", graph)
            self._log("🚀", "Executing deployment workflow...")

            success = await agent._execute_workflow_graph(root_node)

            # ── Step 8: Handle Result ───────────────────────────────────
            if success:
                self._update_profile_timestamp(profile["mail_id"])
                self._log("🎉", f"Deployment SUCCESSFUL for {profile['mail_id']}")
            else:
                self._write_to_dlq(graph, profile, "Workflow graph execution returned False")
                self._log("💀", f"Deployment FAILED for {profile['mail_id']}")

            # ── Step 9: Cleanup ─────────────────────────────────────────
            await agent.stop()
            self._log("🧹", "Agent stopped and cleaned up")

            return self._result(success, 
                "Deployment completed successfully" if success else "Workflow execution failed",
                profile=profile
            )

        except Exception as e:
            error_msg = f"Deployment error: {str(e)}"
            self._log("💥", error_msg)

            # Attempt DLQ write
            try:
                self._write_to_dlq(
                    graph if 'graph' in dir() else {"name": self.graph_name},
                    profile if 'profile' in dir() else {"mail_id": self.profile_mail_id or "unknown"},
                    error_msg
                )
            except Exception:
                pass

            return self._result(False, error_msg)

    # ─── Helpers ────────────────────────────────────────────────────────

    def _log(self, emoji: str, message: str):
        """Log with Rich console and append to deploy_logs."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {emoji} {message}"
        self.deploy_logs.append(log_entry)
        console.print(f"  {emoji}  [dim]{timestamp}[/dim]  {message}")

    def _result(self, success: bool, message: str, profile: Dict = None) -> Dict[str, Any]:
        """Build a structured result dict."""
        elapsed = round(time.time() - self.start_time, 2) if self.start_time else 0
        result = {
            "success": success,
            "message": message,
            "graph_name": self.graph_name,
            "profile_mail_id": profile.get("mail_id") if profile else self.profile_mail_id,
            "server_url": self.server_url,
            "elapsed_seconds": elapsed,
            "logs": self.deploy_logs,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Print summary panel
        status_color = "green" if success else "red"
        status_text = "✅ SUCCESS" if success else "❌ FAILED"

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Status", f"[{status_color}]{status_text}[/{status_color}]")
        table.add_row("Graph", self.graph_name)
        table.add_row("Profile", result["profile_mail_id"] or "auto")
        table.add_row("Duration", f"{elapsed}s")
        table.add_row("Message", message)

        console.print(Panel(table, title="🚀 Deployment Result", border_style=status_color))
        return result

    def _print_banner(self):
        """Print a startup banner."""
        console.print(Panel(
            f"[bold cyan]XIOPATH Deployment Orchestrator[/bold cyan]\n"
            f"[dim]Graph:[/dim] {self.graph_name}  |  "
            f"[dim]Profile:[/dim] {self.profile_mail_id or 'auto'}  |  "
            f"[dim]Server:[/dim] {self.server_url}",
            title="🛸 Phase 21",
            border_style="cyan"
        ))


# ─── CLI Entrypoint ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🛸 XIOPATH Deployment Orchestrator — Deploy swarm workers to Google Colab"
    )
    parser.add_argument(
        "--graph",
        type=str,
        required=True,
        help="Name of the deployment graph (e.g. colab_deploy_graph)"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Specific mail_id to deploy with (default: auto-select first available)"
    )
    parser.add_argument(
        "--server-url",
        type=str,
        default="ws://localhost:8000/api/v1/agent/worker-stream",
        help="WebSocket URL of the XIOPATH Central Server"
    )
    args = parser.parse_args()

    orchestrator = DeploymentOrchestrator(
        graph_name=args.graph,
        profile_mail_id=args.profile,
        server_url=args.server_url
    )

    result = asyncio.run(orchestrator.deploy())

    # Exit with appropriate code
    exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
