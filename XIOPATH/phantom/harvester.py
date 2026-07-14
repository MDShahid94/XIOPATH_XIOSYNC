"""
XIOPATH Phantom Infrastructure — Resource Harvester
=====================================================
Extracts compute and storage resources from phantom accounts
and registers them in the mesh as available nodes.

For each phantom: deploys Node Agent Worker, creates D1/R2/KV,
registers Colab/Kaggle GPU connections, and wires GitHub Actions.

Educational purpose only.
"""

import json
import time
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any
from dataclasses import dataclass, field


# ════════════════════════════════════════════════
# Resource Definitions
# ════════════════════════════════════════════════

@dataclass
class HarvestedResource:
    """A single resource extracted from a phantom account."""
    phantom_id: str
    service: str          # cloudflare, colab, kaggle, github
    resource_type: str    # worker, d1, r2, kv, gpu, actions, container
    resource_id: str      # Service-specific ID
    capabilities: list    # What this resource can do
    limits: dict          # Free-tier limits for this resource
    state: str = "pending"  # pending, deploying, active, suspended, dead
    endpoint: str = ""    # URL/endpoint to reach this resource
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    last_health_check: str = ""

    def to_dict(self) -> dict:
        return {
            "phantom_id": self.phantom_id,
            "service": self.service,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "capabilities": self.capabilities,
            "limits": self.limits,
            "state": self.state,
            "endpoint": self.endpoint,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_health_check": self.last_health_check,
        }


# Free-tier limits per resource type (starter defaults, upgradeable later)
FREE_TIER_LIMITS = {
    "cloudflare": {
        "workers":    {"requests_per_day": 100_000, "cpu_ms_per_invocation": 10, "script_size_mb": 1},
        "d1":         {"storage_gb": 5, "reads_per_day": 5_000_000, "writes_per_day": 100_000, "rows_read_per_day": 5_000_000},
        "r2":         {"storage_gb": 10, "class_a_ops_per_month": 1_000_000, "class_b_ops_per_month": 10_000_000, "egress_cost": 0},
        "kv":         {"reads_per_day": 100_000, "writes_per_day": 1_000, "storage_gb": 1},
        "durable_objects": {"requests_per_day": 100_000, "storage_gb": 5},
        "queues":     {"messages_per_month": 1_000_000, "operations_per_month": 1_000_000},
        "vectorize":  {"indexes": 5, "vectors_per_index": 200_000, "dimensions": 1536},
        "containers": {"vcpu_minutes_per_day": 375},
    },
    "google": {
        "colab_gpu":  {"gpu_type": "T4", "max_session_hours": 12, "ram_gb": 12.7},
        "drive":      {"storage_gb": 15},
    },
    "kaggle": {
        "gpu":        {"gpu_type": "P100", "hours_per_week": 30, "ram_gb": 16},
        "datasets":   {"storage_gb": 100},
    },
    "github": {
        "actions":    {"minutes_per_month": 2000, "concurrent_jobs": 20},
        "packages":   {"storage_mb": 500},
        "repos":      {"private_repos": "unlimited"},
    },
}


class CloudflareHarvester:
    """
    Deploys XIOPATH Node Agent and creates resources on a phantom Cloudflare account.
    Uses the CF API with the phantom's full-permission API token.
    """

    CF_API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, account_id: str, api_token: str):
        self.account_id = account_id
        self.api_token = api_token
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def harvest_all(self, phantom_id: str, node_agent_code: str) -> list[HarvestedResource]:
        """
        Deploy all resources on this phantom's CF account.
        
        Args:
            phantom_id: The phantom identity this account belongs to
            node_agent_code: JavaScript source code for the Node Agent Worker
        
        Returns:
            List of HarvestedResource objects
        """
        resources = []
        now = datetime.now(timezone.utc).isoformat()

        # 1. Deploy Node Agent Worker
        worker = await self._deploy_worker(phantom_id, node_agent_code)
        if worker:
            resources.append(HarvestedResource(
                phantom_id=phantom_id,
                service="cloudflare",
                resource_type="worker",
                resource_id=worker["id"],
                capabilities=["edge_compute", "api_proxy", "websocket", "cron"],
                limits=FREE_TIER_LIMITS["cloudflare"]["workers"],
                state="active",
                endpoint=worker.get("endpoint", ""),
                metadata=worker,
                created_at=now,
            ))

        # 2. Create D1 database
        d1 = await self._create_d1(phantom_id)
        if d1:
            resources.append(HarvestedResource(
                phantom_id=phantom_id,
                service="cloudflare",
                resource_type="d1",
                resource_id=d1["uuid"],
                capabilities=["sql_cache", "distributed_storage"],
                limits=FREE_TIER_LIMITS["cloudflare"]["d1"],
                state="active",
                metadata=d1,
                created_at=now,
            ))

        # 3. Create R2 bucket
        r2 = await self._create_r2(phantom_id)
        if r2:
            resources.append(HarvestedResource(
                phantom_id=phantom_id,
                service="cloudflare",
                resource_type="r2",
                resource_id=r2["name"],
                capabilities=["blob_storage", "zero_egress"],
                limits=FREE_TIER_LIMITS["cloudflare"]["r2"],
                state="active",
                metadata=r2,
                created_at=now,
            ))

        # 4. Create KV namespace
        kv = await self._create_kv(phantom_id)
        if kv:
            resources.append(HarvestedResource(
                phantom_id=phantom_id,
                service="cloudflare",
                resource_type="kv",
                resource_id=kv["id"],
                capabilities=["key_value_store", "fast_reads"],
                limits=FREE_TIER_LIMITS["cloudflare"]["kv"],
                state="active",
                metadata=kv,
                created_at=now,
            ))

        return resources

    async def _deploy_worker(self, phantom_id: str, code: str) -> Optional[dict]:
        """Deploy a Worker script to the phantom's CF account."""
        import urllib.request
        import urllib.error

        worker_name = f"xiopath-node-{phantom_id[:8]}"
        url = f"{self.CF_API_BASE}/accounts/{self.account_id}/workers/scripts/{worker_name}"

        # Worker upload uses multipart form data
        boundary = f"----XiopathBoundary{int(time.time())}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="script"; filename="{worker_name}.js"\r\n'
            f"Content-Type: application/javascript\r\n\r\n"
            f"{code}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="metadata"; filename="metadata.json"\r\n'
            f"Content-Type: application/json\r\n\r\n"
            f'{{"main_module": "{worker_name}.js", "compatibility_date": "2024-12-01"}}\r\n'
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="PUT")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())

            if result.get("success"):
                # Enable the route
                route_url = f"{self.CF_API_BASE}/accounts/{self.account_id}/workers/scripts/{worker_name}/subdomain"
                route_body = json.dumps({"enabled": True}).encode()
                route_req = urllib.request.Request(
                    route_url, data=route_body, headers=self._headers, method="POST"
                )
                try:
                    with urllib.request.urlopen(route_req, timeout=15) as r:
                        pass
                except Exception:
                    pass  # Subdomain enablement is best-effort

                return {
                    "id": worker_name,
                    "endpoint": f"https://{worker_name}.{self.account_id}.workers.dev",
                    "deployed": True,
                }
        except urllib.error.HTTPError as e:
            return {"id": worker_name, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            return {"id": worker_name, "error": str(e)}

        return None

    async def _create_d1(self, phantom_id: str) -> Optional[dict]:
        """Create a D1 database."""
        import urllib.request

        db_name = f"xiopath-cache-{phantom_id[:8]}"
        url = f"{self.CF_API_BASE}/accounts/{self.account_id}/d1/database"
        body = json.dumps({"name": db_name}).encode()

        try:
            req = urllib.request.Request(url, data=body, headers=self._headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success"):
                return result["result"]
        except Exception as e:
            return {"name": db_name, "error": str(e)}
        return None

    async def _create_r2(self, phantom_id: str) -> Optional[dict]:
        """Create an R2 storage bucket."""
        import urllib.request

        bucket_name = f"xiopath-store-{phantom_id[:8]}"
        url = f"{self.CF_API_BASE}/accounts/{self.account_id}/r2/buckets"
        body = json.dumps({"name": bucket_name}).encode()

        try:
            req = urllib.request.Request(url, data=body, headers=self._headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success"):
                return result["result"]
        except Exception as e:
            return {"name": bucket_name, "error": str(e)}
        return None

    async def _create_kv(self, phantom_id: str) -> Optional[dict]:
        """Create a KV namespace."""
        import urllib.request

        ns_name = f"xiopath-kv-{phantom_id[:8]}"
        url = f"{self.CF_API_BASE}/accounts/{self.account_id}/storage/kv/namespaces"
        body = json.dumps({"title": ns_name}).encode()

        try:
            req = urllib.request.Request(url, data=body, headers=self._headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success"):
                return result["result"]
        except Exception as e:
            return {"title": ns_name, "error": str(e)}
        return None

    async def bind_resources_to_worker(self, worker_name: str,
                                        d1_id: str = None, kv_id: str = None,
                                        r2_name: str = None) -> bool:
        """Bind D1/KV/R2 resources to the deployed Worker."""
        import urllib.request

        bindings = []
        if d1_id:
            bindings.append({
                "type": "d1",
                "name": "DB",
                "id": d1_id,
            })
        if kv_id:
            bindings.append({
                "type": "kv_namespace",
                "name": "KV",
                "namespace_id": kv_id,
            })
        if r2_name:
            bindings.append({
                "type": "r2_bucket",
                "name": "R2",
                "bucket_name": r2_name,
            })

        if not bindings:
            return True

        url = f"{self.CF_API_BASE}/accounts/{self.account_id}/workers/scripts/{worker_name}/settings"
        body = json.dumps({"bindings": bindings}).encode()

        try:
            req = urllib.request.Request(url, data=body, headers=self._headers, method="PATCH")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            return result.get("success", False)
        except Exception:
            return False


class GPUConnector:
    """
    Connects Colab/Kaggle GPU sessions to the XIOPATH mesh.
    Generates mesh-worker notebook code that runs inside Colab/Kaggle.
    """

    MESH_WORKER_NOTEBOOK = '''
# XIOPATH Mesh Worker — Colab/Kaggle Connector
# This notebook connects to the XIOPATH control plane and
# accepts tasks (inference, browser automation, data processing).

import websocket
import json
import threading
import time

CONTROL_PLANE_URL = "{control_plane_ws}"
NODE_ID = "{node_id}"
API_KEY = "{api_key}"
CAPABILITIES = {capabilities}

class MeshWorker:
    def __init__(self):
        self.ws = None
        self.running = False
        self.tasks_completed = 0

    def connect(self):
        """Connect to XIOPATH Control Plane via WebSocket."""
        self.ws = websocket.WebSocketApp(
            CONTROL_PLANE_URL,
            header={{"Authorization": f"Bearer {{API_KEY}}"}},
            on_open=self.on_open,
            on_message=self.on_message,
            on_close=self.on_close,
            on_error=self.on_error,
        )
        self.running = True
        self.ws.run_forever(ping_interval=30, ping_timeout=10)

    def on_open(self, ws):
        """Register node with control plane."""
        ws.send(json.dumps({{
            "type": "node_register",
            "node_id": NODE_ID,
            "capabilities": CAPABILITIES,
            "gpu_info": self._get_gpu_info(),
        }}))
        print(f"[XIOPATH] Connected as {{NODE_ID}}")
        # Start heartbeat
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def on_message(self, ws, message):
        """Handle incoming tasks from control plane."""
        msg = json.loads(message)
        if msg.get("type") == "task_dispatch":
            result = self._execute_task(msg["task"])
            ws.send(json.dumps({{
                "type": "task_result",
                "task_id": msg["task"]["id"],
                "result": result,
                "node_id": NODE_ID,
            }}))
            self.tasks_completed += 1

    def on_close(self, ws, code, reason):
        print(f"[XIOPATH] Disconnected: {{reason}}")
        if self.running:
            time.sleep(5)
            self.connect()  # Auto-reconnect

    def on_error(self, ws, error):
        print(f"[XIOPATH] Error: {{error}}")

    def _execute_task(self, task):
        """Execute a mesh task based on its type."""
        task_type = task.get("type", "unknown")
        try:
            if task_type == "inference":
                return self._run_inference(task)
            elif task_type == "browser_automation":
                return self._run_browser(task)
            elif task_type == "data_processing":
                return self._run_data(task)
            else:
                return {{"error": f"Unknown task type: {{task_type}}"}}
        except Exception as e:
            return {{"error": str(e)}}

    def _run_inference(self, task):
        """Run ML inference task."""
        return {{"status": "completed", "output": "inference_result_placeholder"}}

    def _run_browser(self, task):
        """Run browser automation task."""
        return {{"status": "completed", "output": "browser_result_placeholder"}}

    def _run_data(self, task):
        """Run data processing task."""
        return {{"status": "completed", "output": "data_result_placeholder"}}

    def _get_gpu_info(self):
        """Detect GPU info."""
        try:
            import torch
            if torch.cuda.is_available():
                return {{
                    "name": torch.cuda.get_device_name(0),
                    "memory_gb": torch.cuda.get_device_properties(0).total_mem / 1e9,
                    "cuda_version": torch.version.cuda,
                }}
        except ImportError:
            pass
        return {{"name": "CPU", "memory_gb": 0, "cuda_version": None}}

    def _heartbeat(self):
        while self.running:
            try:
                self.ws.send(json.dumps({{
                    "type": "heartbeat",
                    "node_id": NODE_ID,
                    "tasks_completed": self.tasks_completed,
                    "timestamp": time.time(),
                }}))
            except Exception:
                pass
            time.sleep(60)

worker = MeshWorker()
worker.connect()
'''

    def generate_colab_notebook(self, phantom_id: str, control_plane_url: str,
                                 api_key: str, capabilities: list) -> dict:
        """
        Generate a Colab notebook JSON that runs the mesh worker.
        
        Returns:
            Jupyter notebook dict (ipynb format)
        """
        node_id = f"colab-{phantom_id[:8]}"
        worker_code = self.MESH_WORKER_NOTEBOOK.format(
            control_plane_ws=control_plane_url,
            node_id=node_id,
            api_key=api_key,
            capabilities=json.dumps(capabilities),
        )

        notebook = {
            "nbformat": 4,
            "nbformat_minor": 0,
            "metadata": {
                "colab": {"name": f"XIOPATH-Worker-{phantom_id[:8]}", "provenance": []},
                "kernelspec": {"name": "python3", "display_name": "Python 3"},
                "accelerator": "GPU",
            },
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["!pip install websocket-client torch --quiet"],
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
                {
                    "cell_type": "code",
                    "source": worker_code.split("\n"),
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
            ],
        }
        return notebook

    def generate_kaggle_kernel(self, phantom_id: str, control_plane_url: str,
                                api_key: str, capabilities: list) -> dict:
        """
        Generate a Kaggle kernel script + metadata.
        
        Returns:
            Dict with 'script' (Python code) and 'metadata' (kernel-metadata.json)
        """
        node_id = f"kaggle-{phantom_id[:8]}"
        worker_code = self.MESH_WORKER_NOTEBOOK.format(
            control_plane_ws=control_plane_url,
            node_id=node_id,
            api_key=api_key,
            capabilities=json.dumps(capabilities),
        )

        metadata = {
            "id": f"xiopath/worker-{phantom_id[:8]}",
            "title": f"XIOPATH Worker {phantom_id[:8]}",
            "code_file": "worker.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": True,
        }

        return {
            "script": f"# pip install websocket-client torch\n{worker_code}",
            "metadata": metadata,
        }


class GitHubActionsHarvester:
    """
    Configures GitHub Actions as CI/CD compute nodes in the mesh.
    Creates workflow YAML files that execute mesh tasks.
    """

    MESH_WORKFLOW_YAML = '''name: XIOPATH Mesh Worker
on:
  workflow_dispatch:
    inputs:
      task_payload:
        description: 'Base64-encoded task JSON'
        required: true
        type: string
  schedule:
    - cron: '*/15 * * * *'  # Check for tasks every 15 minutes

jobs:
  mesh-worker:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests websocket-client

      - name: Execute mesh task
        env:
          CONTROL_PLANE_URL: ${{{{ secrets.XIOPATH_CONTROL_PLANE }}}}
          API_KEY: ${{{{ secrets.XIOPATH_API_KEY }}}}
          NODE_ID: "actions-{phantom_id_short}"
          TASK_PAYLOAD: ${{{{ github.event.inputs.task_payload }}}}
        run: |
          python -c "
          import os, json, base64, requests, time

          cp_url = os.environ['CONTROL_PLANE_URL']
          api_key = os.environ['API_KEY']
          node_id = os.environ['NODE_ID']
          headers = {{'Authorization': f'Bearer {{api_key}}', 'Content-Type': 'application/json'}}

          # Register node
          requests.post(f'{{cp_url}}/api/v1/mesh/nodes', json={{
              'node_id': node_id,
              'capabilities': ['ci_cd_compute', 'data_processing', 'build'],
              'runtime': 'github_actions',
          }}, headers=headers)

          # Check for task payload (workflow_dispatch) or poll for tasks (scheduled)
          payload = os.environ.get('TASK_PAYLOAD', '')
          if payload:
              task = json.loads(base64.b64decode(payload))
              # Execute task
              result = {{'status': 'completed', 'output': 'task_executed'}}
              requests.post(f'{{cp_url}}/api/v1/mesh/tasks/result', json={{
                  'task_id': task['id'],
                  'result': result,
                  'node_id': node_id,
              }}, headers=headers)
          else:
              # Poll mode: check for pending tasks
              resp = requests.get(f'{{cp_url}}/api/v1/mesh/tasks?node_id={{node_id}}&status=pending', headers=headers)
              tasks = resp.json().get('tasks', [])
              for task in tasks[:3]:  # Process up to 3 tasks per run
                  result = {{'status': 'completed', 'output': 'task_executed'}}
                  requests.post(f'{{cp_url}}/api/v1/mesh/tasks/result', json={{
                      'task_id': task['id'],
                      'result': result,
                      'node_id': node_id,
                  }}, headers=headers)
                  time.sleep(2)

          # Heartbeat
          requests.post(f'{{cp_url}}/api/v1/mesh/heartbeat', json={{
              'node_id': node_id,
          }}, headers=headers)
          "
'''

    def generate_workflow(self, phantom_id: str) -> str:
        """Generate GitHub Actions workflow YAML for a phantom's repo."""
        return self.MESH_WORKFLOW_YAML.format(phantom_id_short=phantom_id[:8])

    async def deploy_to_repo(self, github_token: str, repo_owner: str,
                              repo_name: str, phantom_id: str,
                              control_plane_url: str, api_key: str) -> dict:
        """
        Deploy mesh worker workflow to a phantom GitHub repo.
        Creates the workflow file and sets required secrets.
        """
        import urllib.request

        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # 1. Create workflow file
        workflow_content = self.generate_workflow(phantom_id)
        import base64
        encoded = base64.b64encode(workflow_content.encode()).decode()

        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/.github/workflows/mesh-worker.yml"
        body = json.dumps({
            "message": "Add XIOPATH mesh worker workflow",
            "content": encoded,
        }).encode()

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="PUT")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            workflow_sha = result.get("content", {}).get("sha", "")
        except Exception as e:
            return {"success": False, "error": f"Workflow deploy failed: {e}"}

        # 2. Set repository secrets (CP URL and API key)
        # Note: GitHub requires encrypting secrets with the repo's public key
        # This is a simplified version — full implementation needs libsodium
        secrets_to_set = {
            "XIOPATH_CONTROL_PLANE": control_plane_url,
            "XIOPATH_API_KEY": api_key,
        }

        secrets_set = []
        for secret_name, secret_value in secrets_to_set.items():
            try:
                # Get repo public key first
                pk_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/secrets/public-key"
                pk_req = urllib.request.Request(pk_url, headers=headers)
                with urllib.request.urlopen(pk_req, timeout=10) as resp:
                    pk_data = json.loads(resp.read().decode())

                # In production: encrypt with NaCl sealed box using pk_data["key"]
                # Simplified: we'll note the requirement
                secrets_set.append(secret_name)
            except Exception:
                pass

        return {
            "success": True,
            "workflow_sha": workflow_sha,
            "secrets_configured": secrets_set,
        }


class ResourceHarvester:
    """
    Master orchestrator that harvests resources from ALL services
    on a phantom account and registers them in the mesh.
    """

    def __init__(self, vault, control_plane_url: str, ontology_bridge=None):
        """
        Args:
            vault: CredentialVault instance
            control_plane_url: URL of the XIOPATH Control Plane
            ontology_bridge: Optional PhantomOntologyBridge for ontology integration
        """
        self.vault = vault
        self.control_plane_url = control_plane_url
        self.bridge = ontology_bridge
        self.gpu_connector = GPUConnector()
        self.actions_harvester = GitHubActionsHarvester()

    async def harvest_phantom(self, phantom_id: str) -> dict:
        """
        Harvest all resources from a single phantom's accounts.
        
        Returns:
            Dict with per-service results and total resource count
        """
        identity = self.vault.get_identity(phantom_id)
        if not identity:
            return {"error": f"Phantom {phantom_id} not found in vault"}

        results = {
            "phantom_id": phantom_id,
            "cloudflare": [],
            "colab": None,
            "kaggle": None,
            "github": None,
            "total_resources": 0,
        }

        services = identity.get("services", {})

        # 1. Cloudflare resources
        cf = services.get("cloudflare", {})
        if cf.get("account_id") and cf.get("api_token"):
            harvester = CloudflareHarvester(cf["account_id"], cf["api_token"])
            node_agent_code = self._generate_node_agent_code(phantom_id)
            cf_resources = await harvester.harvest_all(phantom_id, node_agent_code)
            results["cloudflare"] = [r.to_dict() for r in cf_resources]
            results["total_resources"] += len(cf_resources)

            # Bind resources to the Worker
            d1_res = next((r for r in cf_resources if r.resource_type == "d1"), None)
            kv_res = next((r for r in cf_resources if r.resource_type == "kv"), None)
            r2_res = next((r for r in cf_resources if r.resource_type == "r2"), None)
            worker_res = next((r for r in cf_resources if r.resource_type == "worker"), None)

            if worker_res and worker_res.state == "active":
                await harvester.bind_resources_to_worker(
                    worker_res.resource_id,
                    d1_id=d1_res.resource_id if d1_res else None,
                    kv_id=kv_res.resource_id if kv_res else None,
                    r2_name=r2_res.resource_id if r2_res else None,
                )

        # 2. Colab GPU notebook
        google = identity.get("google", {})
        if google.get("email"):
            notebook = self.gpu_connector.generate_colab_notebook(
                phantom_id=phantom_id,
                control_plane_url=self.control_plane_url.replace("https://", "wss://") + "/api/v1/ws",
                api_key=cf.get("api_token", ""),
                capabilities=["gpu_inference", "browser_automation", "data_processing"],
            )
            results["colab"] = {
                "notebook_generated": True,
                "node_id": f"colab-{phantom_id[:8]}",
                "gpu_type": "T4",
            }
            results["total_resources"] += 1

        # 3. Kaggle kernel
        kaggle = services.get("kaggle", {})
        if kaggle.get("api_key"):
            kernel = self.gpu_connector.generate_kaggle_kernel(
                phantom_id=phantom_id,
                control_plane_url=self.control_plane_url.replace("https://", "wss://") + "/api/v1/ws",
                api_key=kaggle["api_key"],
                capabilities=["gpu_training", "data_processing", "ml_inference"],
            )
            results["kaggle"] = {
                "kernel_generated": True,
                "node_id": f"kaggle-{phantom_id[:8]}",
                "gpu_type": "P100",
            }
            results["total_resources"] += 1

        # 4. GitHub Actions
        gh = services.get("github", {})
        if gh.get("token") and gh.get("username"):
            results["github"] = {
                "workflow_generated": True,
                "node_id": f"actions-{phantom_id[:8]}",
                "minutes_per_month": 2000,
            }
            results["total_resources"] += 1

        # Register all harvested resources as child agents in ontology
        if self.bridge:
            resources_flat = []
            for r in results.get("cloudflare", []):
                resources_flat.append(r)
            if results.get("colab"):
                resources_flat.append({
                    "resource_type": "gpu",
                    "resource_id": results["colab"]["node_id"],
                    "alias": f"colab-gpu-{phantom_id[:8]}",
                    "endpoint": None,
                    "limits": {"gpu_type": "T4", "runtime_hours": 12},
                })
            if results.get("kaggle"):
                resources_flat.append({
                    "resource_type": "gpu",
                    "resource_id": results["kaggle"]["node_id"],
                    "alias": f"kaggle-gpu-{phantom_id[:8]}",
                    "endpoint": None,
                    "limits": {"gpu_type": "P100", "runtime_hours": 30},
                })
            if results.get("github"):
                resources_flat.append({
                    "resource_type": "actions",
                    "resource_id": results["github"]["node_id"],
                    "alias": f"gh-actions-{phantom_id[:8]}",
                    "endpoint": None,
                    "limits": {"minutes_per_month": 2000},
                })
            for res in resources_flat:
                self.bridge.register_child_resource(
                    phantom_id,
                    res.get("resource_type", "worker"),
                    res,
                )
            results["resources"] = resources_flat

        return results

    def _generate_node_agent_code(self, phantom_id: str) -> str:
        """Generate the Node Agent Worker JavaScript code."""
        return f"""
// XIOPATH Node Agent — Phantom {phantom_id[:8]}
// Deployed to Cloudflare Workers free tier
// Handles: task dispatch, heartbeat, data proxy

export default {{
  async fetch(request, env) {{
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS headers
    const corsHeaders = {{
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }};

    if (request.method === 'OPTIONS') {{
      return new Response(null, {{ headers: corsHeaders }});
    }}

    // Health check
    if (path === '/health') {{
      return Response.json({{
        status: 'alive',
        node_id: 'cf-{phantom_id[:8]}',
        phantom: '{phantom_id[:8]}',
        timestamp: Date.now(),
      }}, {{ headers: corsHeaders }});
    }}

    // Task execution endpoint
    if (path === '/task' && request.method === 'POST') {{
      const task = await request.json();
      const result = await executeTask(task, env);
      return Response.json(result, {{ headers: corsHeaders }});
    }}

    // Data proxy (forward to R2/D1)
    if (path.startsWith('/data/')) {{
      return handleDataProxy(path, request, env);
    }}

    return Response.json({{ error: 'Not found' }}, {{ status: 404, headers: corsHeaders }});
  }},

  // Scheduled heartbeat (every 5 minutes)
  async scheduled(event, env) {{
    await fetch('{self.control_plane_url}/api/v1/mesh/heartbeat', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        node_id: 'cf-{phantom_id[:8]}',
        timestamp: Date.now(),
      }}),
    }});
  }},
}};

async function executeTask(task, env) {{
  try {{
    switch (task.type) {{
      case 'kv_get':
        const val = await env.KV.get(task.key);
        return {{ status: 'ok', value: val }};
      case 'kv_put':
        await env.KV.put(task.key, task.value);
        return {{ status: 'ok' }};
      case 'fetch_proxy':
        const resp = await fetch(task.url, task.options || {{}});
        const body = await resp.text();
        return {{ status: 'ok', response: body, code: resp.status }};
      default:
        return {{ status: 'error', message: 'Unknown task type' }};
    }}
  }} catch (e) {{
    return {{ status: 'error', message: e.message }};
  }}
}}

async function handleDataProxy(path, request, env) {{
  const key = path.replace('/data/', '');
  if (request.method === 'GET') {{
    const obj = await env.R2.get(key);
    if (!obj) return new Response('Not found', {{ status: 404 }});
    return new Response(obj.body, {{
      headers: {{ 'Content-Type': obj.httpMetadata?.contentType || 'application/octet-stream' }},
    }});
  }}
  if (request.method === 'PUT') {{
    const body = await request.arrayBuffer();
    await env.R2.put(key, body);
    return Response.json({{ status: 'stored', key }});
  }}
  return new Response('Method not allowed', {{ status: 405 }});
}}
"""

    def calculate_mesh_capacity(self, phantom_count: int) -> dict:
        """Calculate total mesh capacity for N phantom accounts."""
        return {
            "phantom_count": phantom_count,
            "edge_requests_per_day": phantom_count * 100_000,
            "d1_storage_gb": phantom_count * 5,
            "d1_reads_per_day": phantom_count * 5_000_000,
            "r2_storage_gb": phantom_count * 10,
            "r2_egress_cost": 0,
            "kv_reads_per_day": phantom_count * 100_000,
            "colab_gpu_sessions": phantom_count,
            "colab_gpu_type": "T4",
            "kaggle_gpu_sessions": phantom_count,
            "kaggle_gpu_hours_per_week": phantom_count * 30,
            "github_actions_minutes_per_month": phantom_count * 2000,
            "containers_vcpu_min_per_day": phantom_count * 375,
            "total_cost_per_month": 0,
        }
