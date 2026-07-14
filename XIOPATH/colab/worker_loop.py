"""
Colab Worker Loop — WebSocket Task Dispatch + Heartbeat
=======================================================
Connects to the central XIOPATH server via WebSocket,
receives tasks, executes them, and returns results.

Upgraded from llm_worker/main.py with:
    - Browser task support (not just LLM inference)
    - Heartbeat keepalive (prevents Colab idle timeout)
    - Exponential backoff reconnect
    - Memory node sync after task completion
    - Graceful shutdown with profile save
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("ColabWorkerLoop")


class ColabWorkerLoop:
    """
    WebSocket worker loop that connects to the central XIOPATH server
    and processes inference + browser tasks.

    Task Types:
        inference_task  — LLM reasoning (text in → action JSON out)
        browser_task    — Navigate + interact via stealth browser
        embed_task      — Generate embeddings on GPU (optional)
    """

    def __init__(
        self,
        server_url: str,
        worker_id: str = "colab_worker_1",
        heartbeat_interval: int = 30,
        max_reconnect_delay: int = 60,
    ):
        """
        Args:
            server_url: WebSocket URL of the central server
                       (e.g., "ws://100.x.x.x:8000/api/v1/agent/worker-stream")
            worker_id: Unique identifier for this worker
            heartbeat_interval: Seconds between keepalive pings
            max_reconnect_delay: Maximum seconds between reconnect attempts
        """
        self.server_url = server_url
        self.worker_id = worker_id
        self.heartbeat_interval = heartbeat_interval
        self.max_reconnect_delay = max_reconnect_delay

        self._running = False
        self._websocket = None
        self._task_handlers: Dict[str, Callable] = {}

        # Callbacks for lifecycle events
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_task_complete: Optional[Callable] = None

    def register_handler(self, task_type: str, handler: Callable):
        """
        Register a handler function for a specific task type.

        The handler receives a dict (task data) and must return a dict (result).
        """
        self._task_handlers[task_type] = handler
        logger.info(f"Registered handler for task type: '{task_type}'")

    async def _heartbeat(self):
        """Send periodic keepalive pings to prevent Colab idle disconnect."""
        while self._running and self._websocket:
            try:
                await self._websocket.send(json.dumps({
                    "type": "heartbeat",
                    "worker_id": self.worker_id,
                    "timestamp": time.time(),
                }))
                await asyncio.sleep(self.heartbeat_interval)
            except Exception:
                break

    async def _process_task(self, data: dict) -> dict:
        """Route a task to its registered handler."""
        task_type = data.get("type", "unknown")
        task_id = data.get("task_id", "?")

        handler = self._task_handlers.get(task_type)
        if not handler:
            logger.warning(f"No handler for task type '{task_type}'")
            return {
                "status": "error",
                "task_id": task_id,
                "message": f"Unknown task type: {task_type}",
            }

        try:
            logger.info(f"Processing {task_type} (task_id={task_id})...")
            start_time = time.time()

            if asyncio.iscoroutinefunction(handler):
                result = await handler(data)
            else:
                result = handler(data)

            elapsed = time.time() - start_time
            logger.info(f"Task {task_id} completed in {elapsed:.2f}s")

            if self.on_task_complete:
                self.on_task_complete(data, result)

            return result

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            return {
                "status": "error",
                "task_id": task_id,
                "message": str(e),
            }

    async def _worker_session(self):
        """Single WebSocket session: connect → register → process tasks."""
        import websockets

        logger.info(f"Connecting to {self.server_url}...")
        async with websockets.connect(self.server_url) as websocket:
            self._websocket = websocket
            logger.info("Connected! Registering as worker...")

            import os
            token = os.environ.get("WORKER_AUTH_TOKEN", "")

            # Register
            await websocket.send(json.dumps({
                "type": "register_worker",
                "worker_id": self.worker_id,
                "token": token,
            }))

            if self.on_connected:
                self.on_connected()

            # Start heartbeat
            heartbeat_task = asyncio.create_task(self._heartbeat())

            try:
                async for message in websocket:
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "register_worker":
                        continue

                    # Process and respond
                    result = await self._process_task(data)
                    result["type"] = "inference_result"
                    await websocket.send(json.dumps(result))

            finally:
                heartbeat_task.cancel()
                self._websocket = None

    async def run(self):
        """
        Main loop with exponential backoff reconnection.

        Runs indefinitely until stop() is called.
        """
        self._running = True
        backoff = 5

        while self._running:
            try:
                await self._worker_session()
            except Exception as e:
                if not self._running:
                    break

                logger.warning(f"Connection lost: {e}. Reconnecting in {backoff}s...")

                if self.on_disconnected:
                    self.on_disconnected()

                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.max_reconnect_delay)
            else:
                backoff = 5  # Reset on clean disconnect

        logger.info("Worker loop stopped.")

    def stop(self):
        """Signal the worker loop to stop."""
        self._running = False
        if self._websocket:
            asyncio.ensure_future(self._websocket.close())

    # ================================================================
    # BUILT-IN INFERENCE HANDLER (compatible with existing llm_worker)
    # ================================================================

    @staticmethod
    def make_inference_handler(llm_engine=None):
        """
        Create an inference task handler using the Gemini engine or agy CLI.

        If llm_engine is provided, uses it directly.
        Otherwise, falls back to agy CLI subprocess.
        """

        async def handle_inference(task_data: dict) -> dict:
            intent = task_data.get("intent", "")
            dom = task_data.get("dom", "")
            task_id = task_data.get("task_id", "?")

            prompt = (
                "You are an autonomous web automation agent.\n"
                "Given the following DOM snapshot and an Intent, infer the next "
                "single logical action.\n"
                "Return raw JSON: {\"action\": \"click\"|\"fill\", "
                "\"selector\": \"<css>\", \"text\": \"<if fill>\"}\n\n"
                f"Intent: {intent}\nDOM:\n{dom}"
            )

            if llm_engine:
                # Direct API call (Gemini/local model)
                try:
                    response = llm_engine.ask_raw(prompt)
                    action_json = _parse_llm_response(response)
                    return {
                        "status": "success",
                        "task_id": task_id,
                        "action": action_json,
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "task_id": task_id,
                        "message": str(e),
                    }
            else:
                # Fallback: agy CLI subprocess
                import subprocess

                try:
                    process = await asyncio.create_subprocess_exec(
                        "agy", "--dangerously-skip-permissions", "--print", prompt,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                    )
                    stdout, _ = await process.communicate()
                    text_res = stdout.decode("utf-8").strip()
                    action_json = _parse_llm_response(text_res)
                    return {
                        "status": "success",
                        "task_id": task_id,
                        "action": action_json,
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "task_id": task_id,
                        "message": str(e),
                    }

        return handle_inference


def _parse_llm_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif text.startswith("```"):
        text = text[3:-3]

    return json.loads(text.strip())
