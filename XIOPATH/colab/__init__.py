"""
Colab Virtual Worker Bot Package
================================
Transforms a Google Colab instance into an autonomous stealth worker node
that connects back to the central XIOPATH server.

Modules:
    stealth_browser  — Undetected Chrome + 5-vector anti-bot stealth
    profile_manager  — Encrypted .xio Chrome profile persistence
    drive_sync       — Google Drive upload/download for profile blobs
    worker_loop      — WebSocket task dispatch + heartbeat
    gpu_embedder     — Optional GPU-accelerated embeddings (FAISS/Qwen3)
    notebook_template — Bootstrap code template for Colab cells
    oauth_handler    — Auto-click through OAuth consent popups
    google_signin    — Full Google sign-in automation (email/pass/TOTP)
    auth_bootstrap   — agy CLI authentication orchestrator
    colab_automator  — Colab UI automation (sessions/runtime/cells)
    swarm_deployer   — Autonomous multi-worker swarm deployment
"""

from .stealth_browser import StealthBrowser
from .profile_manager import ColabProfileManager
from .drive_sync import DriveSync
from .worker_loop import ColabWorkerLoop

__all__ = [
    "StealthBrowser",
    "ColabProfileManager",
    "DriveSync",
    "ColabWorkerLoop",
]
"""

The following imports are deferred to avoid heavy dependencies
on Colab instances that don't need the full swarm stack:

    from .notebook_template import generate_bootstrap, COLAB_NOTEBOOK_URL
    from .oauth_handler import handle_oauth_popups, handle_drive_auth_modal
    from .google_signin import google_signin, check_existing_session
    from .auth_bootstrap import bootstrap_agy_auth
    from .colab_automator import run_colab_notebook
    from .swarm_deployer import SwarmDeployer
"""
