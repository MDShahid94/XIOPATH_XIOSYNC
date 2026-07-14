"""
Colab Notebook Template — Bootstrap code for worker deployment.

This module provides the template code that gets injected into a Google Colab
notebook cell to bootstrap a worker instance. The template is parameterized
with worker-specific configuration (worker_id, exit_node, credentials, etc.)
and is designed to be used by the swarm_deployer via colab_automator.
"""

# Hardcoded URLs per user specification
COLAB_NOTEBOOK_URL = "https://colab.research.google.com/drive/1PQurRe48EZvzoSqLdL0zrFpkhhwDsIBa?usp=sharing"
DRIVE_PROFILES_FOLDER_URL = "https://drive.google.com/drive/folders/1oxZx_Lcoh1Wae8JVgDUV3GN3Og6cThji?usp=sharing"
DRIVE_PROFILES_FOLDER_ID = "1oxZx_Lcoh1Wae8JVgDUV3GN3Og6cThji"

# The bootstrap code template injected into a Colab cell.
# Placeholders: __WORKER_ID__, __EXIT_NODE__, __CENTRAL_WS__, __REPO_URL__,
#               __DRIVE_FOLDER_ID__
BOOTSTRAP_TEMPLATE = r'''
import os, sys, subprocess, time

def run(cmd, silent=False):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    lines = []
    for line in p.stdout:
        line = line.rstrip()
        lines.append(line)
        if not silent:
            print(line, flush=True)
    p.wait()
    return "\n".join(lines), p.returncode

print("=" * 60)
print("🚀 XIOPATH Colab Worker Bootstrap")
print("   Worker ID: __WORKER_ID__")
print("=" * 60)

# ── 1. Clone project ────────────────────────────────────────
REPO = "__REPO_URL__"
PROJECT_DIR = "/content/antigravity"
if not os.path.exists(PROJECT_DIR):
    print("📦 Cloning project...", flush=True)
    run(f"git clone {REPO} {PROJECT_DIR}")
else:
    print("📦 Project already cloned, pulling latest...", flush=True)
    run(f"cd {PROJECT_DIR} && git pull")

os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

# ── 2. Install dependencies ─────────────────────────────────
print("\n📦 Installing dependencies...", flush=True)
run("pip install -q -r requirements.txt 2>/dev/null || true", silent=True)
run("pip install -q undetected-chromedriver cryptography psutil pyotp "
    "websockets faiss-cpu sentence-transformers 2>/dev/null", silent=True)

# System deps (Chrome + Xvfb)
run("apt-get update > /dev/null 2>&1 && "
    "apt-get install -y xvfb > /dev/null 2>&1", silent=True)
_, rc = run("which google-chrome-stable", silent=True)
if rc != 0:
    run("wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | "
        "apt-key add - > /dev/null 2>&1", silent=True)
    run('echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" '
        '>> /etc/apt/sources.list.d/google-chrome.list', silent=True)
    run("apt-get update > /dev/null 2>&1 && "
        "apt-get install -y google-chrome-stable > /dev/null 2>&1", silent=True)
print("✅ Chrome ready.", flush=True)

# Start Xvfb
subprocess.Popen("Xvfb :99 -screen 0 1920x1080x24 &", shell=True)
os.environ['DISPLAY'] = ':99'
time.sleep(2)
print("✅ Virtual display :99 started.", flush=True)

# ── 3. Set worker environment ───────────────────────────────
os.environ['WORKER_ID'] = '__WORKER_ID__'
os.environ['EXIT_NODE_IP'] = '__EXIT_NODE__'
os.environ['CENTRAL_WS_URL'] = '__CENTRAL_WS__'
os.environ['DRIVE_FOLDER_ID'] = '__DRIVE_FOLDER_ID__'

# ── 4. Run the worker ───────────────────────────────────────
print("\n🤖 Starting Colab Worker Loop...", flush=True)
run("python colab_worker.py")

print("\n[COLAB_EXECUTION_COMPLETE]")
'''


def generate_bootstrap(
    worker_id: str,
    exit_node: str = "",
    central_ws: str = "ws://localhost:8000/api/v1/agent/worker-stream",
    repo_url: str = "https://github.com/MDShahid94/Browser-Automation-Test.git",
    drive_folder_id: str = DRIVE_PROFILES_FOLDER_ID,
) -> str:
    """
    Fill the bootstrap template with worker-specific parameters.

    Args:
        worker_id: Unique identifier for this worker instance.
        exit_node: Tailscale exit node IP for residential proxy.
        central_ws: WebSocket URL of the central server.
        repo_url: Git repository URL to clone.
        drive_folder_id: Google Drive folder ID for profile storage.

    Returns:
        Ready-to-inject Python code string.
    """
    code = BOOTSTRAP_TEMPLATE
    code = code.replace("__WORKER_ID__", worker_id)
    code = code.replace("__EXIT_NODE__", exit_node)
    code = code.replace("__CENTRAL_WS__", central_ws)
    code = code.replace("__REPO_URL__", repo_url)
    code = code.replace("__DRIVE_FOLDER_ID__", drive_folder_id)
    return code
