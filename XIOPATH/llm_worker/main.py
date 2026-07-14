import asyncio
import websockets
import json
import logging
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AGY-Worker")

CENTRAL_SERVER_WS = "ws://localhost:8000/api/v1/agent/worker-stream"

prompt_template = """
You are an autonomous web automation agent. 
Given the following DOM snapshot and an Intent, you must infer the next single logical action to take to progress toward the intent.
You must return your response as a raw JSON object with the following schema:
{{
    "action": "click" | "fill",
    "selector": "<css_selector_or_xpath>",
    "text": "<text_to_fill_if_action_is_fill>"
}}

Intent: {intent}
DOM:
{dom}
"""

async def process_inference_task(task_data: dict) -> dict:
    try:
        intent = task_data.get("intent")
        dom = task_data.get("dom")
        task_id = task_data.get("task_id")
        
        logger.info(f"Received inference task {task_id} for intent: {intent}")
        
        prompt = prompt_template.format(intent=intent, dom=dom)
        
        # Take over XIOPATH Console!
        # Runs the agy CLI in headless/print mode, but streams output LIVE for "headed" visibility
        logger.info("Spawning XIOPATH Agent (agy)... (Streaming output live!)")
        process = await asyncio.create_subprocess_exec(
            "agy", "--dangerously-skip-permissions", "--print", prompt,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        
        output_lines = []
        async for line in process.stdout:
            decoded = line.decode('utf-8')
            print(f"[AGY] {decoded}", end="")
            output_lines.append(decoded)
            
        await process.wait()
        
        if process.returncode != 0:
            logger.error(f"agy execution failed!")
            raise Exception("agy process returned non-zero exit code")
            
        text_res = "".join(output_lines).strip()
        
        # Clean up Markdown formatting if any
        if "```json" in text_res:
            text_res = text_res.split("```json")[1].split("```")[0]
        elif text_res.startswith("```"):
            text_res = text_res[3:-3]
            
        action_json = json.loads(text_res.strip())
        
        logger.info(f"Inference complete for task {task_id}: {action_json}")
        
        return {
            "status": "success",
            "task_id": task_id,
            "action": action_json
        }
        
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        return {
            "status": "error",
            "task_id": task_data.get("task_id"),
            "message": str(e)
        }

async def worker_loop():
    while True:
        try:
            logger.info(f"Connecting to Central Server at {CENTRAL_SERVER_WS}...")
            async with websockets.connect(CENTRAL_SERVER_WS) as websocket:
                logger.info("Connected successfully! Waiting for tasks...")
                
                # Registration/Hello message
                await websocket.send(json.dumps({"type": "register_worker", "worker_id": "admin_worker_1"}))
                
                async for message in websocket:
                    data = json.loads(message)
                    if data.get("type") == "inference_task":
                        result = await process_inference_task(data)
                        result["type"] = "inference_result"
                        await websocket.send(json.dumps(result))
                        
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    logger.info("Starting XIOPATH Headless CLI Worker...")
    asyncio.run(worker_loop())
