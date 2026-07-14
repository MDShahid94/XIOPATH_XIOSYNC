"""
XIOPATH Colab Virtual Worker Bot
=====================================
Single-cell paste-and-run script for Google Colab.

Transforms a free Colab instance into an autonomous stealth worker node:
    1. Install system + Python dependencies
    2. Authenticate Tailscale (residential IP routing)
    3. Download + decrypt Chrome profile from Drive
    4. Launch 5-Vector Stealth Browser (UC + Xvfb + JS injection)
    5. Connect to central XIOPATH server via WebSocket
    6. Process tasks (LLM inference + browser automation)
    7. Periodic profile backup to Drive (every 10 min)
    8. Heartbeat keepalive (every 30s)

Usage in Colab:
    1. Paste this entire file into a single code cell
    2. Set the configuration parameters below
    3. Run the cell
    4. Click the Tailscale auth link when prompted
    5. The worker will connect to your central server automatically
"""

import os
import sys
import time
import asyncio
import logging
import subprocess
import threading

# ================================================================
# CONFIGURATION (Set these before running)
# ================================================================

# Central server WebSocket URL (your Mac's Tailscale IP)
CENTRAL_SERVER_URL = "ws://100.x.x.x:8000/api/ws/worker"  # @param {type:"string"}

# Tailscale exit node IP (the device whose residential IP you want to use)
EXIT_NODE_IP = "100.98.229.77"  # @param {type:"string"}

# Google Drive folder ID for encrypted profile storage
DRIVE_FOLDER_ID = "1c_bkeGvhTkyaIMpnZiXz7xhspAqaJqns"  # @param {type:"string"}

# Worker identity
WORKER_ID = "colab_worker_1"  # @param {type:"string"}
PROFILE_ID = "colab_worker_1"  # @param {type:"string"}

# Profile backup interval (seconds)
PROFILE_BACKUP_INTERVAL = 600  # @param {type:"integer"}

# Optional: Enable GPU-accelerated embeddings
ENABLE_GPU_EMBEDDINGS = False  # @param {type:"boolean"}
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"  # @param {type:"string"}

# Gemini API key (for direct LLM inference without agy CLI)
GEMINI_API_KEY = ""  # @param {type:"string"}

# Central server HTTP base URL (for ontology v2 API)
CENTRAL_API_URL = "http://100.x.x.x:8000"  # @param {type:"string"}

# Worker auth secret (must match XIOPATH_JWT_SECRET or WORKER_SECRET on server)
WORKER_AUTH_SECRET = ""  # @param {type:"string"}

# Dynamic capabilities matching the v5 Type Registry action_types
# e.g., ["web_browse", "llm_inference", "python_execute"]
WORKER_CAPABILITIES = ["web_browse", "llm_inference"]  # @param {type:"string"}

# ================================================================
# LOGGING
# ================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ColabWorker")


# ================================================================
# STEP 1: INSTALL DEPENDENCIES
# ================================================================

def install_dependencies():
    """Install all system and Python dependencies."""

    def run(cmd, desc, silent=True):
        """F-22: Uses subprocess.run instead of os.system for security."""
        logger.info(f"📦 {desc}...")
        subprocess.run(
            cmd, shell=True,
            stdout=subprocess.DEVNULL if silent else None,
            stderr=subprocess.DEVNULL if silent else None
        )

    # System packages
    run("sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/apt/lists/lock",
        "Clearing package locks")
    run("sudo apt-get update -y", "Updating apt")

    # Xvfb + fonts (for canvas stealth)
    run(
        'echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula '
        'select true" | sudo debconf-set-selections',
        "Accepting font EULA"
    )
    run(
        "sudo apt-get install -y xvfb xdotool ca-certificates curl gnupg "
        "libgl1-mesa-dri mesa-utils libegl1-mesa ttf-mscorefonts-installer "
        "fonts-liberation fonts-noto-color-emoji fonts-roboto",
        "Installing Xvfb + fonts + Mesa"
    )

    # Google Chrome (official)
    run(
        "wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | "
        "sudo gpg --yes --dearmor -o /usr/share/keyrings/googlechrome-keyring.gpg",
        "Adding Chrome signing key"
    )
    run(
        'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-keyring.gpg] '
        'http://dl.google.com/linux/chrome/deb/ stable main" | '
        "sudo tee /etc/apt/sources.list.d/google-chrome.list",
        "Adding Chrome repo"
    )
    run("sudo apt-get update -y && sudo apt-get install -y google-chrome-stable",
        "Installing Google Chrome")

    # Tailscale
    run("sudo mkdir -p /usr/share/keyrings", "Preparing Tailscale keyring")
    run(
        "curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg | "
        "sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg",
        "Adding Tailscale key"
    )
    run(
        "curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list | "
        "sudo tee /etc/apt/sources.list.d/tailscale.list",
        "Adding Tailscale repo"
    )
    run("sudo apt-get update -y && sudo apt-get install -y tailscale",
        "Installing Tailscale")

    # Python packages
    run(
        "pip install undetected-chromedriver pyautogui PySocks beautifulsoup4 "
        "requests websockets cryptography psutil google-api-python-client "
        "google-auth",
        "Installing Python packages"
    )

    # Optional: GPU embedding packages
    if ENABLE_GPU_EMBEDDINGS:
        run(
            "pip install torch transformers faiss-gpu",
            "Installing GPU embedding packages (torch + FAISS)"
        )

    logger.info("✅ All dependencies installed.")


# ================================================================
# STEP 2: AUTHENTICATE TAILSCALE
# ================================================================

def setup_tailscale():
    """Boot Tailscale daemon and authenticate."""
    logger.info("🔒 Setting up Tailscale...")

    subprocess.run(["sudo", "pkill", "-9", "tailscaled"], capture_output=True)
    subprocess.run(["sudo", "rm", "-f", "/var/run/tailscale/tailscaled.sock"], capture_output=True)
    subprocess.Popen(
        ["sudo", "tailscaled", "--tun=userspace-networking",
         "--socks5-server=localhost:1055"],
        stdout=open("tailscaled.log", "w"),
        stderr=subprocess.STDOUT
    )
    time.sleep(3)

    logger.info("🔗 Generating Tailscale auth link...")
    logger.info("⚠️  Click the link below to authenticate this Colab instance:")
    subprocess.run(["sudo", "tailscale", "up"])

    logger.info("✅ Tailscale authenticated.")


# ================================================================
# STEP 3: PERIODIC PROFILE BACKUP (Background Thread)
# ================================================================

def start_profile_backup_thread(profile_mgr, drive_sync, profile_path):
    """Background thread that periodically saves and uploads the profile."""

    def backup_loop():
        while True:
            time.sleep(PROFILE_BACKUP_INTERVAL)
            try:
                logger.info("⏰ Periodic profile backup...")
                xio_bytes = profile_mgr.save_profile(
                    extract_path=profile_path,
                    profile_id=PROFILE_ID,
                    essential_only=True,
                    encrypt=True,
                )
                if xio_bytes:
                    drive_sync.upload_profile(f"{PROFILE_ID}.xio", xio_bytes)
                    logger.info("✅ Profile backed up to Drive.")
                else:
                    logger.warning("⚠️ Profile backup returned empty bytes.")
            except Exception as e:
                logger.error(f"Profile backup failed: {e}")

    thread = threading.Thread(target=backup_loop, daemon=True)
    thread.start()
    return thread


# ================================================================
# MAIN ORCHESTRATOR
# ================================================================

async def main():
    """Full Colab worker boot sequence."""

    logger.info("=" * 60)
    logger.info("🚀 ANTIGRAVITY COLAB VIRTUAL WORKER BOT")
    logger.info("=" * 60)

    # --- Step 1: Dependencies ---
    install_dependencies()

    # Add project to path (if cloned)
    project_dir = os.getcwd()
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    # --- Step 2: Tailscale ---
    setup_tailscale()

    # --- Step 2.5: Ontology Self-Registration ---
    # Register this worker in the agent ontology (Phase O.6)
    boot_integration = None
    try:
        from core.worker_boot_integration import WorkerBootIntegration
        boot_integration = WorkerBootIntegration(
            server_base_url=CENTRAL_API_URL,
            worker_id=WORKER_ID,
            worker_secret=WORKER_AUTH_SECRET,
            profile_id=PROFILE_ID,
        )
        agent_id = boot_integration.self_register(
            exit_node_ip=EXIT_NODE_IP,
            capabilities=WORKER_CAPABILITIES,
        )
        if agent_id:
            logger.info(f"✅ Ontology agent registered: {agent_id}")

            # Restore profiles from ontology (supplements Drive sync)
            ontology_profiles = boot_integration.restore_profiles()

            # Restore Tailscale config from ontology
            ts_config = boot_integration.restore_tailscale_config()
            if ts_config and ts_config.get("current_exit_node_ip"):
                # Override EXIT_NODE_IP with ontology value if different
                ontology_exit = ts_config["current_exit_node_ip"]
                if ontology_exit != EXIT_NODE_IP:
                    logger.info(f"🔄 Exit node overridden by ontology: {EXIT_NODE_IP} → {ontology_exit}")
                    EXIT_NODE_IP = ontology_exit
    except ImportError:
        logger.info("ℹ️ Ontology integration not available (core module missing). Continuing standalone.")
    except Exception as e:
        logger.warning(f"⚠️ Ontology registration failed: {e}. Continuing standalone.")
    from colab.stealth_browser import StealthBrowser
    from colab.profile_manager import ColabProfileManager
    from colab.drive_sync import DriveSync
    from colab.worker_loop import ColabWorkerLoop

    drive_sync = DriveSync(folder_id=DRIVE_FOLDER_ID)
    profile_mgr = ColabProfileManager(profiles_dir="/content/profiles")

    # --- Step 4: Sync vault key from Drive ---
    logger.info("🔑 Checking for shared vault key on Drive...")
    vault_key_bytes = drive_sync.download_vault_key()
    if vault_key_bytes:
        vault_key_path = os.path.join("/content/profiles", ".vault_key")
        with open(vault_key_path, "wb") as f:
            f.write(vault_key_bytes)
        profile_mgr = ColabProfileManager(
            profiles_dir="/content/profiles",
            vault_key_path=vault_key_path,
        )
        logger.info("✅ Shared vault key loaded from Drive.")
    else:
        logger.info("No shared vault key found. Using/generating local key.")
        # Upload the generated key to Drive for future workers
        with open(profile_mgr.vault_key_path, "rb") as f:
            drive_sync.upload_vault_key(f.read())

    # --- Step 5: Download + decrypt Chrome profile ---
    logger.info("📥 Downloading profile from Drive...")
    xio_bytes = drive_sync.download_profile(f"{PROFILE_ID}.xio")
    profile_path = profile_mgr.load_profile(PROFILE_ID, xio_bytes)
    logger.info(f"✅ Profile loaded at: {profile_path}")

    # --- Step 6: Launch stealth browser ---
    browser = StealthBrowser(
        exit_node_ip=EXIT_NODE_IP,
        profile_path=profile_path,
    )
    browser.set_exit_node()
    driver = browser.launch()
    logger.info("✅ Stealth browser launched!")

    # --- Step 7: Start periodic profile backup ---
    start_profile_backup_thread(profile_mgr, drive_sync, profile_path)

    # --- Step 7.5: Register profile in ontology ---
    if boot_integration and boot_integration.agent_id:
        boot_integration.register_profile(
            profile_type="browser_chrome",
            storage_path=f"/drive/MyDrive/profiles/{PROFILE_ID}.xio",
            persistence_mode="periodic",
            save_interval=PROFILE_BACKUP_INTERVAL,
        )

    # --- Step 7.6: Start ontology keepalive heartbeat ---
    if boot_integration and boot_integration.agent_id:
        boot_integration.start_keepalive(interval_seconds=30)

    # --- Step 8: Initialize LLM engine (optional) ---
    llm_engine = None
    if GEMINI_API_KEY:
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
        try:
            from core.gemini_engine import GeminiEngine
            llm_engine = GeminiEngine()
            logger.info("✅ Gemini engine initialized (direct API).")
        except Exception as e:
            logger.warning(f"Gemini engine failed: {e}. Using agy CLI fallback.")

    # --- Step 9: Optional GPU embedder ---
    gpu_embedder = None
    if ENABLE_GPU_EMBEDDINGS:
        try:
            from colab.gpu_embedder import GPUEmbedder
            gpu_embedder = GPUEmbedder(model_name=EMBEDDING_MODEL)
            logger.info(f"✅ GPU embedder loaded: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.warning(f"GPU embedder failed: {e}. Using default embeddings.")

    # --- Step 10: Connect to central server ---
    worker = ColabWorkerLoop(
        server_url=CENTRAL_SERVER_URL,
        worker_id=WORKER_ID,
    )

    # Register inference handler
    inference_handler = ColabWorkerLoop.make_inference_handler(llm_engine)
    worker.register_handler("inference_task", inference_handler)

    # Browser task handler
    async def handle_browser_task(task_data: dict) -> dict:
        """Execute a browser navigation/interaction task."""
        url = task_data.get("url", "")
        action = task_data.get("action", {})
        task_id = task_data.get("task_id", "?")

        try:
            if url:
                driver.get(url)
                time.sleep(2)

            action_type = action.get("action", "")
            selector = action.get("selector", "")

            if action_type == "click":
                element = driver.find_element("css selector", selector)
                element.click()
            elif action_type == "fill":
                element = driver.find_element("css selector", selector)
                element.clear()
                element.send_keys(action.get("text", ""))

            return {
                "status": "success",
                "task_id": task_id,
                "action": {"completed": True, "url": driver.current_url},
            }
        except Exception as e:
            return {
                "status": "error",
                "task_id": task_id,
                "message": str(e),
            }

    worker.register_handler("browser_task", handle_browser_task)

    # Lifecycle callbacks
    def on_shutdown():
        """Final profile save on shutdown."""
        logger.info("🛑 Shutting down. Final profile save...")
        try:
            xio_bytes = profile_mgr.save_profile(
                extract_path=profile_path,
                profile_id=PROFILE_ID,
                essential_only=False,
                encrypt=True,
            )
            if xio_bytes:
                drive_sync.upload_profile(f"{PROFILE_ID}.xio", xio_bytes)
                logger.info("✅ Final profile saved to Drive.")
        except Exception as e:
            logger.error(f"Final profile save failed: {e}")
        finally:
            browser.quit()

    worker.on_disconnected = lambda: (
        logger.warning("⚠️ Disconnected from central server."),
        boot_integration.record_disconnected("ws_connection_lost") if boot_integration else None,
    )
    worker.on_connected = lambda: (
        logger.info("✅ Connected to central server!"),
        boot_integration.record_connected() if boot_integration else None,
    )

    # --- Step 11: Run worker loop ---
    logger.info("=" * 60)
    logger.info("🤖 WORKER ONLINE — Waiting for tasks...")
    logger.info("=" * 60)

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        on_shutdown()
        # Record shutdown in ontology
        if boot_integration:
            boot_integration.record_shutdown()

    logger.info("[COLAB_EXECUTION_COMPLETE]")


# ================================================================
# ENTRYPOINT
# ================================================================

if __name__ == "__main__":
    asyncio.run(main())
