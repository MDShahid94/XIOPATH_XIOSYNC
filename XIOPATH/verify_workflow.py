import asyncio
from core.agent_loop import AgentLoop

async def verify_workflow_system():
    print("Testing Semantic Workflow System...")
    agent = AgentLoop(headless='true', session_id='test_workflow')
    await agent.start()
    
    try:
        print("\n--- STEP 1: Creating Workflow (Isaac Newton) ---")
        await agent.browser.page.goto("https://www.wikipedia.org")
        
        # Trigger an intent to track footprints
        intent = "Search for Isaac Newton"
        await agent.chat_step(intent)
        
        await asyncio.sleep(2)
        
        # Force a done footprint to trigger workflow save
        print("\n--- STEP 2: Finishing Workflow ---")
        await agent.chat_step(intent)
        
        print("\n--- STEP 3: Semantic Match Testing (Albert Einstein) ---")
        await agent.browser.page.goto("https://www.wikipedia.org")
        
        # This should trigger confidence > 0.85 and run the graph parametrically
        await agent.chat_step("Search for Albert Einstein")
        
        await asyncio.sleep(5)
        
    finally:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(verify_workflow_system())
