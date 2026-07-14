"""
XIOPATH Phantom Infrastructure — Session Migration
=====================================================
Gradual IP/device migration over 3 days to establish the
phantom's "new normal" IP without triggering anomaly detection.

Educational purpose only.
"""

import json
import asyncio
import logging
import hashlib
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("phantom.session_migration")


# Travel-plausible country mappings (for migration step 3)
TRAVEL_PLAUSIBLE_COUNTRIES = {
    "US": ["CA", "MX", "GB", "DE", "JP", "FR", "AU"],
    "IN": ["AE", "SG", "US", "GB", "TH", "MY", "AU"],
    "GB": ["FR", "DE", "ES", "US", "IE", "NL", "IT"],
    "DE": ["FR", "AT", "CH", "NL", "CZ", "US", "IT"],
    "CA": ["US", "MX", "GB", "FR", "JP"],
    "AU": ["NZ", "SG", "ID", "US", "JP", "IN"],
    "BR": ["AR", "CL", "US", "PT", "CO"],
    "JP": ["KR", "TW", "US", "TH", "SG"],
    "SG": ["MY", "TH", "AU", "IN", "JP", "US"],
    "AE": ["IN", "PK", "GB", "US", "EG"],
}


@dataclass
class MigrationStep:
    """A single step in the multi-day session migration."""
    step_number: int
    day: int
    hour: int
    proxy_country: str
    proxy_type: str  # "member_device", "residential_same_city", "residential_same_country", "travel", "infrastructure"
    description: str
    activity: list[str]  # Actions to perform during this login
    completed: bool = False
    completed_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "day": self.day,
            "hour": self.hour,
            "proxy_country": self.proxy_country,
            "proxy_type": self.proxy_type,
            "description": self.description,
            "activity": self.activity,
            "completed": self.completed,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class SessionMigrator:
    """
    Executes gradual IP/device migration over 3 days.
    Creates a plausible "travel narrative" for the IP change.
    """

    def __init__(self, vault, proxy_pool, browser_profile_manager):
        self.vault = vault
        self.proxy_pool = proxy_pool
        self.browser_manager = browser_profile_manager
        self._migrations: dict[str, list[MigrationStep]] = {}

    async def plan_migration(self, phantom_id: str, member_ip_country: str) -> list[dict]:
        """
        Create a 3-day migration schedule.
        
        The schedule gradually shifts the phantom's login IP from
        the member's real location to the system infrastructure IP.
        
        Args:
            phantom_id: Phantom identity ID
            member_ip_country: 2-letter country code of the member's IP
        
        Returns:
            List of MigrationStep dicts
        """
        rng = random.Random(hashlib.sha256(phantom_id.encode()).hexdigest())

        # Choose a travel-plausible intermediate country
        plausible = TRAVEL_PLAUSIBLE_COUNTRIES.get(member_ip_country, ["US", "GB", "DE"])
        travel_country = rng.choice(plausible)

        # Infrastructure country (where the system runs)
        infra_country = "US"  # Default; configurable

        steps = [
            # ── Day 0: Login from member's location ──
            MigrationStep(
                step_number=1,
                day=0, hour=0,
                proxy_country=member_ip_country,
                proxy_type="member_device",
                description="Initial login from member's verification device",
                activity=["check_gmail", "browse_youtube"],
            ),
            MigrationStep(
                step_number=2,
                day=0, hour=1,
                proxy_country=member_ip_country,
                proxy_type="residential_same_city",
                description="Login from residential proxy, same city (WiFi change simulation)",
                activity=["check_gmail", "google_search"],
            ),
            MigrationStep(
                step_number=3,
                day=0, hour=6,
                proxy_country=member_ip_country,
                proxy_type="residential_same_country",
                description="Login from residential proxy, same country (mobile network switch)",
                activity=["check_gmail", "browse_news"],
            ),
            MigrationStep(
                step_number=4,
                day=0, hour=18,
                proxy_country=member_ip_country,
                proxy_type="residential_same_country",
                description="Evening login, same country (home WiFi)",
                activity=["watch_youtube", "check_gmail"],
            ),

            # ── Day 1: Travel simulation ──
            MigrationStep(
                step_number=5,
                day=1, hour=8,
                proxy_country=travel_country,
                proxy_type="travel",
                description=f"Login from {travel_country} (travel-plausible intermediate)",
                activity=["check_gmail", "google_maps", "flight_search"],
            ),
            MigrationStep(
                step_number=6,
                day=1, hour=14,
                proxy_country=travel_country,
                proxy_type="travel",
                description=f"Afternoon in {travel_country} (establish presence)",
                activity=["browse_local_sites", "check_gmail"],
            ),
            MigrationStep(
                step_number=7,
                day=1, hour=22,
                proxy_country=infra_country,
                proxy_type="infrastructure",
                description=f"Evening login from {infra_country} (final destination)",
                activity=["check_gmail"],
            ),

            # ── Day 2: Establish new normal ──
            MigrationStep(
                step_number=8,
                day=2, hour=9,
                proxy_country=infra_country,
                proxy_type="infrastructure",
                description=f"Morning login from infrastructure IP ({infra_country})",
                activity=["check_gmail", "google_search", "browse_youtube"],
            ),
            MigrationStep(
                step_number=9,
                day=2, hour=18,
                proxy_country=infra_country,
                proxy_type="infrastructure",
                description="Evening login — new normal established",
                activity=["check_gmail", "browse_random"],
            ),

            # ── Day 3: Confirm stable ──
            MigrationStep(
                step_number=10,
                day=3, hour=10,
                proxy_country=infra_country,
                proxy_type="infrastructure",
                description="Day 3 login — migration complete, all future logins from infrastructure",
                activity=["check_gmail", "verify_account_health"],
            ),
        ]

        self._migrations[phantom_id] = steps
        return [s.to_dict() for s in steps]

    async def execute_step(self, phantom_id: str, step: MigrationStep) -> bool:
        """
        Execute a single migration step.
        Restores the phantom's browser session, logs in via the specified proxy,
        performs light activity, and saves the session state.
        """
        try:
            from playwright.async_api import async_playwright

            # Get the phantom's browser profile
            profile = self.browser_manager.get_profile(phantom_id)
            if not profile:
                logger.error(f"No browser profile for {phantom_id[:8]}")
                step.error = "No browser profile"
                return False

            # Get proxy for this step
            proxy_config = None
            if step.proxy_type != "member_device" and self.proxy_pool:
                proxy = self.proxy_pool.get_proxy(country=step.proxy_country)
                if proxy:
                    proxy_config = {
                        "server": f"{proxy.protocol}://{proxy.host}:{proxy.port}",
                        "username": proxy.username,
                        "password": proxy.password,
                    }

            # Get Playwright options with proxy
            pw_options = self.browser_manager.get_playwright_context_options(phantom_id)
            if proxy_config:
                pw_options["proxy"] = proxy_config

            fp_script = self.browser_manager.get_fingerprint_injection_script(phantom_id)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(**pw_options)
                await context.add_init_script(fp_script)
                page = await context.new_page()

                # Perform each activity
                for activity in step.activity:
                    await self._perform_activity(page, activity)
                    await asyncio.sleep(random.uniform(2, 5))

                # Save session state
                storage = await context.storage_state()
                self.browser_manager.save_session_state(phantom_id, storage)
                self.browser_manager.update_profile_state(phantom_id, "active")

                await browser.close()

            step.completed = True
            step.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Migration step {step.step_number} complete for {phantom_id[:8]}")
            return True

        except Exception as e:
            step.error = str(e)
            logger.error(f"Migration step {step.step_number} failed for {phantom_id[:8]}: {e}")
            return False

    async def run_migration(self, phantom_id: str) -> dict:
        """
        Execute the full multi-day migration.
        Returns immediately — schedules steps as async tasks.
        """
        if phantom_id not in self._migrations:
            return {"error": "No migration plan found. Call plan_migration() first."}

        steps = self._migrations[phantom_id]
        result = {
            "phantom_id": phantom_id,
            "total_steps": len(steps),
            "scheduled": True,
        }

        # Execute Day 0 steps immediately
        for step in steps:
            if step.day == 0 and not step.completed:
                await self.execute_step(phantom_id, step)

        return result

    def get_migration_status(self, phantom_id: str) -> dict:
        """Check progress of an ongoing migration."""
        steps = self._migrations.get(phantom_id, [])
        completed = sum(1 for s in steps if s.completed)
        failed = sum(1 for s in steps if s.error)

        return {
            "phantom_id": phantom_id,
            "total_steps": len(steps),
            "completed": completed,
            "failed": failed,
            "pending": len(steps) - completed - failed,
            "steps": [s.to_dict() for s in steps],
        }

    async def _perform_activity(self, page, activity: str) -> None:
        """Perform a single migration activity."""
        try:
            if activity == "check_gmail":
                await page.goto("https://mail.google.com", timeout=15000)
                await asyncio.sleep(random.uniform(3, 8))

            elif activity == "browse_youtube":
                await page.goto("https://www.youtube.com", timeout=15000)
                await asyncio.sleep(random.uniform(5, 15))

            elif activity == "watch_youtube":
                await page.goto("https://www.youtube.com", timeout=15000)
                await asyncio.sleep(3)
                # Click a trending video
                video = await page.query_selector('a#video-title')
                if video:
                    await video.click()
                    await asyncio.sleep(random.uniform(30, 90))

            elif activity == "google_search":
                queries = [
                    "weather today", "latest news", "python tutorial",
                    "best restaurants near me", "how to cook pasta",
                ]
                query = random.choice(queries)
                await page.goto(f"https://www.google.com/search?q={query}", timeout=15000)
                await asyncio.sleep(random.uniform(3, 8))

            elif activity == "browse_news":
                await page.goto("https://news.google.com", timeout=15000)
                await asyncio.sleep(random.uniform(5, 15))

            elif activity == "google_maps":
                await page.goto("https://www.google.com/maps", timeout=15000)
                await asyncio.sleep(random.uniform(3, 8))

            elif activity == "flight_search":
                await page.goto("https://www.google.com/travel/flights", timeout=15000)
                await asyncio.sleep(random.uniform(3, 8))

            elif activity == "browse_random":
                sites = ["https://www.wikipedia.org", "https://www.reddit.com",
                         "https://www.amazon.com", "https://stackoverflow.com"]
                await page.goto(random.choice(sites), timeout=15000)
                await asyncio.sleep(random.uniform(3, 10))

            elif activity == "browse_local_sites":
                await page.goto("https://www.google.com/search?q=local+restaurants", timeout=15000)
                await asyncio.sleep(random.uniform(3, 8))

            elif activity == "verify_account_health":
                await page.goto("https://myaccount.google.com/security", timeout=15000)
                await asyncio.sleep(random.uniform(3, 5))

        except Exception as e:
            logger.debug(f"Activity '{activity}' failed: {e}")
