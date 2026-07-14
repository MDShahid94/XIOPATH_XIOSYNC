import threading
import time
import logging
from collections import deque
from typing import Dict, Any

import requests

logger = logging.getLogger(__name__)


class SyncWorker:
    """
    Background worker that asynchronously pushes locally promoted nodes to the global server
    and pulls global nodes down to the local database.

    Uses a thread-safe deque instead of a plain list to prevent race conditions
    between the main thread (append) and the background thread (popleft).
    """
    def __init__(self, memory_manager, server_url: str = "http://localhost:8000/api/v1"):
        self.memory_manager = memory_manager
        self.server_url = server_url
        self.client_id = memory_manager.session_id
        self.running = False
        self.thread = None
        self._push_queue: deque = deque(maxlen=1000)
        self._last_pull_ts: float = 0  # Tracks last successful pull timestamp
        
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._sync_loop, daemon=True)
            self.thread.start()
            logger.info("Started federated memory sync thread.")
            
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            logger.info("Stopped federated memory sync thread.")
            
    def queue_push(self, node: Dict[str, Any]):
        """Queue a node for promotion to the global server. Thread-safe."""
        if len(self._push_queue) >= 800:
            logger.warning(
                "Sync push queue at %.0f%% capacity (%d/%d items)",
                len(self._push_queue) / 1000 * 100,
                len(self._push_queue),
                1000,
            )
        self._push_queue.append(node)
        
    def _sync_loop(self):
        while self.running:
            try:
                # 1. Process Pushes
                while self._push_queue:
                    node = self._push_queue.popleft()
                    try:
                        res = requests.post(
                            f"{self.server_url}/sync/push?client_id={self.client_id}", 
                            json=node,
                            timeout=5
                        )
                        if res.status_code == 200:
                            logger.info(f"Pushed '{node['intent']}' to global sync.")
                        else:
                            # If failed, re-queue at front
                            self._push_queue.appendleft(node)
                            break  # Wait until next cycle
                    except requests.RequestException as e:
                        logger.warning(f"Sync push failed for '{node.get('intent', '?')}': {e}")
                        self._push_queue.appendleft(node)
                        break
                
                # 2. Process Pulls — fetch global updates since last pull
                try:
                    res = requests.get(
                        f"{self.server_url}/sync/pull",
                        params={
                            "client_id": self.client_id,
                            "since": self._last_pull_ts,
                        },
                        timeout=5,
                    )
                    if res.status_code == 200:
                        nodes = res.json().get("nodes", [])
                        for node_data in nodes:
                            try:
                                self.memory_manager.ingest_global_node(node_data)
                            except Exception as ingest_err:
                                logger.warning(f"Failed to ingest global node: {ingest_err}")
                        if nodes:
                            self._last_pull_ts = time.time()
                            logger.info(f"Pulled and ingested {len(nodes)} global node(s).")
                except requests.RequestException as e:
                    logger.debug(f"Sync pull skipped (server may be unreachable): {e}")
                        
                # 3. Sleep between cycles
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                time.sleep(5)
                continue

