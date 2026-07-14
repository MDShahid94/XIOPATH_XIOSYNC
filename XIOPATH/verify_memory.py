import asyncio
from core.agent_loop import AgentLoop

async def verify_memory_system():
    print("Testing 2-Tier Memory System...")
    agent = AgentLoop(headless='true', session_id='test_memory')
    await agent.start()
    
    try:
        # Step 1: Navigate to Wikipedia
        print("\n--- STEP 1: Setup ---")
        await agent.chat_step("Go to wikipedia.org")
        
        intent = "search for isaac newton"
        
        # Step 2: First Time (LLM Generation -> Saves to Secondary)
        print("\n--- STEP 2: First Execution (Generative) ---")
        await agent.chat_step(intent)
        
        # Manually reset to wikipedia homepage to test memory properly
        await agent.browser.page.goto("https://www.wikipedia.org")
        await agent.browser.page.wait_for_load_state('networkidle')
        
        # Step 3: Second Time (Secondary Memory Validation -> Promote to 1)
        print("\n--- STEP 3: Second Execution (Secondary Validation) ---")
        await agent.chat_step(intent)
        
        await agent.browser.page.goto("https://www.wikipedia.org")
        await agent.browser.page.wait_for_load_state('networkidle')
        
        # Step 4: Third Time (Secondary Validation -> Promote to 2)
        print("\n--- STEP 4: Third Execution (Secondary Validation) ---")
        await agent.chat_step(intent)
        
        await agent.browser.page.goto("https://www.wikipedia.org")
        await agent.browser.page.wait_for_load_state('networkidle')
        
        # Step 5: Fourth Time (Secondary Validation -> Promote to 3 -> Graduates to Primary)
        print("\n--- STEP 5: Fourth Execution (Secondary Validation -> Graduation) ---")
        await agent.chat_step(intent)
        
        await agent.browser.page.goto("https://www.wikipedia.org")
        await agent.browser.page.wait_for_load_state('networkidle')
        
        # Step 6: Fifth Time (Primary Execution -> Bypass LLM)
        print("\n--- STEP 6: Fifth Execution (Primary Instant Execute) ---")
        await agent.chat_step(intent)
        
    finally:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(verify_memory_system())
