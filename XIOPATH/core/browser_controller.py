import os
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional, Dict, Any

class PlaywrightController:
    """
    A modular, native Playwright controller that completely replaces browser-use's manager.
    Handles dynamic headless toggling, proxy injection, persistent sessions, and smart recordings.
    """
    def __init__(self, headless: str = 'auto', proxy_config: dict = None, profile_name: str = None):
        self.headless = self._determine_headless(headless)
        self.proxy_config = proxy_config
        self.profile_name = profile_name
        self.playwright = None
        self.browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        
    def _determine_headless(self, mode: str) -> bool:
        if mode.lower() == 'true': return True
        if mode.lower() == 'false': return False
        
        # Auto mode: Headless on CI/Linux servers, Headed on Mac/Windows/Local Desktop
        if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
            return True
        if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
            return True
        return False

    async def start(self, enable_traces: bool = True, enable_video: bool = True, video_mode: str = 'action'):
        """
        Initializes the browser and context with smart tracing and recording options.
        video_mode: 'continuous' (default playwright webm) or 'action' (screenshots before/after).
        """
        self.playwright = await async_playwright().start()
        
        launch_args = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled", 
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        }
        
        # We use chromium by default
        if self.profile_name:
            profile_path = Path("data/profiles") / self.profile_name
            profile_path.mkdir(parents=True, exist_ok=True)
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path.absolute()),
                headless=self.headless,
                proxy=self.proxy_config,
                viewport={"width": 1280, "height": 800},
                record_video_dir="data/recordings" if enable_video and video_mode == 'continuous' else None
            )
        else:
            self.browser = await self.playwright.chromium.launch(**launch_args)
            context_args = {
                "viewport": {"width": 1280, "height": 800},
                "proxy": self.proxy_config
            }
            if enable_video and video_mode == 'continuous':
                context_args["record_video_dir"] = "data/recordings"
                
            self.context = await self.browser.new_context(**context_args)
            
        # Start Tracing
        if enable_traces:
            await self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            
        # Initialize default page
        pages = self.context.pages
        if len(pages) > 0:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()

    async def stop(self, save_trace: bool = True):
        if self.context:
            if save_trace:
                Path("data/traces").mkdir(parents=True, exist_ok=True)
                await self.context.tracing.stop(path="data/traces/session_trace.zip")
            await self.context.close()
            
        if self.browser:
            await self.browser.close()
            
        if self.playwright:
            await self.playwright.stop()

    async def take_action_screenshot(self, name: str):
        """Action-based video/recording alternative: takes named screenshots at key moments."""
        Path("data/action_screenshots").mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=f"data/action_screenshots/{name}.png", full_page=True)
        
    async def get_fingerprint(self) -> Dict[str, str]:
        """Dynamically extracts the browser footprint."""
        if not self.page:
            return {"device_type": "unknown", "os_name": "unknown", "browser": "unknown", "viewport": "unknown"}
            
        user_agent = await self.page.evaluate("navigator.userAgent")
        platform = await self.page.evaluate("navigator.platform")
        
        device_type = "mobile" if "Mobi" in user_agent else "desktop"
        
        browser_name = self.browser.browser_type.name if self.browser else "chromium" # fallback if using persistent context
        
        viewport = self.page.viewport_size
        viewport_str = f"{viewport['width']}x{viewport['height']}" if viewport else "unknown"
        
        return {
            "device_type": device_type,
            "os_name": platform.lower(),
            "browser": browser_name,
            "viewport": viewport_str
        }
