#!/usr/bin/env python3
"""
XIOPATH — Antigravity Command Line Interface (agy)
===================================================
The primary CLI for joining the XIOPATH Swarm Mesh and 
managing local workspaces.
"""

import argparse
import sys
import asyncio
import logging
from typing import List

# Setup basic logging for CLI output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("agy")

def cmd_swarm_join(args):
    """Joins the XIOPATH Swarm as a worker node."""
    logger.info(f"🚀 Initializing Swarm Worker [{args.worker_id}]")
    logger.info(f"🔗 Connecting to Central Control Plane: {args.url}")
    logger.info(f"⚙️ Declaring Capabilities: {args.capabilities}")
    
    try:
        from colab.worker_loop import ColabWorkerLoop
        
        # Configure the event loop for the worker
        worker = ColabWorkerLoop(
            server_url=args.url,
            worker_id=args.worker_id,
            heartbeat_interval=30
        )
        
        # Simulate passing the auth token to the websocket (handled in worker_loop logic)
        import os
        os.environ["WORKER_AUTH_TOKEN"] = args.token
        
        logger.info("🟢 Starting local execution loop...")
        asyncio.run(worker.run())
        
    except ImportError as e:
        logger.error(f"Failed to load Swarm worker dependencies: {e}")
        logger.error("Please ensure you are running this from the XIOPATH root directory.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 Swarm worker shut down gracefully.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(
        prog="agy",
        description="XIOPATH Antigravity CLI — Autonomous Swarm Management"
    )
    
    subparsers = parser.add_subparsers(title="commands", dest="command", required=True)
    
    # --- SWARM COMMANDS ---
    swarm_parser = subparsers.add_parser("swarm", help="Manage swarm participation")
    swarm_subs = swarm_parser.add_subparsers(title="swarm commands", dest="swarm_cmd", required=True)
    
    # agy swarm join
    join_parser = swarm_subs.add_parser("join", help="Join the XIOPATH distributed compute mesh")
    join_parser.add_argument("--url", type=str, default="ws://localhost:8000/api/ws/worker", 
                             help="Central Control Plane WebSocket URL")
    join_parser.add_argument("--token", type=str, required=True, 
                             help="JWT Auth Token provided by your XIOPATH dashboard")
    join_parser.add_argument("--worker-id", type=str, default="native_worker_1", 
                             help="Unique identifier for this worker node")
    join_parser.add_argument("--capabilities", nargs="+", default=["web_browse", "llm_inference"],
                             help="List of action_types this node is willing to process")
    
    args = parser.parse_args()
    
    if args.command == "swarm":
        if args.swarm_cmd == "join":
            cmd_swarm_join(args)

if __name__ == "__main__":
    main()
