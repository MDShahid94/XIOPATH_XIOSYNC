"""
XIOPATH Phantom Infrastructure — Profile Aging Pipeline
=========================================================
30-day warm-up schedule that transforms a fresh phantom account
into a believable, "aged" identity before mesh deployment.

Educational purpose only.
"""

import random
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("phantom.aging")


# ════════════════════════════════════════════════
# Aging Content Databases
# ════════════════════════════════════════════════

AGING_SITES = [
    "https://www.youtube.com", "https://www.wikipedia.org", "https://www.reddit.com",
    "https://www.amazon.com", "https://stackoverflow.com", "https://www.quora.com",
    "https://medium.com", "https://www.bbc.com", "https://edition.cnn.com",
    "https://www.nytimes.com", "https://www.github.com", "https://www.linkedin.com",
    "https://www.imdb.com", "https://www.spotify.com", "https://www.twitch.tv",
    "https://www.pinterest.com", "https://www.ebay.com", "https://news.ycombinator.com",
    "https://www.producthunt.com", "https://dev.to",
    "https://www.weather.com", "https://www.yelp.com", "https://www.tripadvisor.com",
    "https://www.craigslist.org", "https://www.bestbuy.com", "https://www.walmart.com",
    "https://www.target.com", "https://www.nike.com", "https://www.apple.com",
    "https://www.microsoft.com", "https://www.adobe.com", "https://www.canva.com",
]

AGING_SEARCH_QUERIES = [
    "best programming language 2025", "python tutorial for beginners",
    "how to cook pasta", "weather forecast today", "latest tech news",
    "best laptops under 500", "healthy breakfast recipes", "javascript vs python",
    "how to learn machine learning", "best movies to watch",
    "home workout routine", "how to invest in stocks", "python data science",
    "best coffee shops near me", "linux vs windows comparison",
    "react tutorial 2025", "best budget smartphones", "travel tips Europe",
    "how to meditate", "best books for productivity",
    "docker tutorial beginners", "kubernetes explained", "cloud computing basics",
    "AI news today", "GPT vs Claude comparison", "web development roadmap",
    "freelancing tips for developers", "remote work best practices",
    "how to set up a VPN", "cybersecurity fundamentals",
    "best free online courses", "data structures and algorithms",
    "REST API design patterns", "PostgreSQL vs MySQL",
    "how to contribute to open source", "personal finance tips 2025",
    "smartphone photography tips", "best coding bootcamps",
    "electric vehicles comparison", "renewable energy facts",
    "space exploration news", "climate change latest research",
    "world news today", "cooking for one person", "meal prep ideas",
    "best hiking trails", "yoga for beginners", "mindfulness exercises",
    "how to write a resume", "job interview preparation",
    "best podcasts technology", "machine learning projects ideas",
]

YOUTUBE_QUERIES = [
    "python tutorial 2025", "how to cook ramen", "10 minute workout",
    "tech news today", "learn javascript", "best budget laptop review",
    "travel vlog europe", "productivity tips", "coding interview prep",
    "machine learning explained", "react vs angular", "how things are made",
    "space documentary", "guitar lesson beginners", "photography tips",
]


# ════════════════════════════════════════════════
# Aging Schedule Definition
# ════════════════════════════════════════════════

def _get_aging_schedule() -> dict:
    """
    30-day warm-up schedule organized into 4 phases.
    Each day maps to a list of tasks to perform.
    """
    schedule = {}

    # ── PHASE 1: BIRTH (Days 1-3) ──
    # Light touch: prove the account is "alive"
    for day in range(1, 4):
        schedule[day] = [
            {"type": "check_gmail", "duration_s": 15, "description": "Open Gmail briefly"},
            {"type": "watch_youtube", "query": random.choice(YOUTUBE_QUERIES),
             "duration_s": 120, "description": "Watch a YouTube video"},
            {"type": "google_search", "query": random.choice(AGING_SEARCH_QUERIES),
             "duration_s": 30, "description": "Perform a Google search"},
        ]

    # ── PHASE 2: INFANCY (Days 4-10) ──
    # Regular usage patterns, build cookie footprint
    for day in range(4, 11):
        tasks = [
            {"type": "check_gmail", "duration_s": 20, "description": "Check Gmail inbox"},
            {"type": "google_search", "query": random.choice(AGING_SEARCH_QUERIES),
             "duration_s": 40, "description": "Search and browse results"},
            {"type": "browse_sites", "count": 3, "duration_s": 90,
             "description": "Browse 3 random popular websites"},
        ]
        if day % 2 == 0:
            tasks.append({"type": "watch_youtube", "query": random.choice(YOUTUBE_QUERIES),
                         "duration_s": 180, "description": "Watch YouTube content"})
        if day == 7:
            tasks.append({"type": "send_test_email", "duration_s": 30,
                         "description": "Send a test email to self"})
        schedule[day] = tasks

    # ── PHASE 3: ADOLESCENCE (Days 11-20) ──
    # Service signups, developer activity begins
    for day in range(11, 21):
        tasks = [
            {"type": "check_gmail", "duration_s": 15, "description": "Check Gmail"},
            {"type": "browse_sites", "count": 4, "duration_s": 120,
             "description": "Browse popular websites"},
            {"type": "google_search", "query": random.choice(AGING_SEARCH_QUERIES),
             "duration_s": 45, "description": "Search and browse"},
        ]
        if day == 12:
            tasks.append({"type": "signup_cloudflare", "duration_s": 120,
                         "description": "Sign up for Cloudflare"})
        if day == 15:
            tasks.append({"type": "signup_github", "duration_s": 120,
                         "description": "Sign up for GitHub"})
        if day == 17:
            tasks.append({"type": "create_colab_notebook", "duration_s": 90,
                         "description": "Create a Colab notebook"})
        if day == 19:
            tasks.append({"type": "signup_kaggle", "duration_s": 120,
                         "description": "Sign up for Kaggle"})
        schedule[day] = tasks

    # ── PHASE 4: MATURATION (Days 21-30) ──
    # Active developer usage, prepare for mesh deployment
    for day in range(21, 31):
        tasks = [
            {"type": "check_gmail", "duration_s": 15, "description": "Check Gmail"},
            {"type": "browse_sites", "count": 5, "duration_s": 150,
             "description": "Heavy browsing session"},
            {"type": "google_search", "query": random.choice(AGING_SEARCH_QUERIES),
             "duration_s": 45, "description": "Search"},
        ]
        if day == 22:
            tasks.append({"type": "create_github_repo", "duration_s": 60,
                         "description": "Create a GitHub repository"})
        if day == 24:
            tasks.append({"type": "deploy_test_worker", "duration_s": 60,
                         "description": "Deploy a test Cloudflare Worker"})
        if day == 26:
            tasks.append({"type": "star_github_repos", "count": 5, "duration_s": 45,
                         "description": "Star popular GitHub repos"})
        if day == 28:
            tasks.append({"type": "run_colab_notebook", "duration_s": 120,
                         "description": "Run a Colab notebook"})
        if day == 30:
            tasks.append({"type": "final_health_check", "duration_s": 30,
                         "description": "Final account health verification"})
        schedule[day] = tasks

    return schedule


class ProfileAger:
    """
    Executes the 30-day profile aging schedule for phantom accounts.
    Each day, the phantom performs human-like browsing activity to
    build up a natural usage history and cookie footprint.
    """

    def __init__(self, vault, browser_profile_manager, proxy_pool):
        self.vault = vault
        self.browser_manager = browser_profile_manager
        self.proxy_pool = proxy_pool
        self._schedule = _get_aging_schedule()

    async def get_aging_tasks(self, phantom_id: str, current_age_days: int) -> list[dict]:
        """
        Get today's aging tasks based on the phantom's age.
        
        Args:
            phantom_id: The phantom identity ID
            current_age_days: How many days old the profile is
        
        Returns:
            List of task dicts for today
        """
        day = min(current_age_days + 1, 30)  # Cap at day 30
        tasks = self._schedule.get(day, [])

        # Use phantom_id as seed for deterministic task selection
        rng = random.Random(hashlib.sha256(f"{phantom_id}:{day}".encode()).hexdigest())

        # Randomize task-specific parameters
        for task in tasks:
            if task["type"] == "browse_sites":
                count = task.get("count", 3)
                task["urls"] = rng.sample(AGING_SITES, min(count, len(AGING_SITES)))
            elif task["type"] == "google_search":
                task["query"] = rng.choice(AGING_SEARCH_QUERIES)
            elif task["type"] == "watch_youtube":
                task["query"] = rng.choice(YOUTUBE_QUERIES)

        return tasks

    async def execute_aging_task(self, phantom_id: str, task: dict) -> bool:
        """Execute a single aging task in the phantom's browser profile."""
        profile = self.browser_manager.get_profile(phantom_id)
        if not profile:
            logger.error(f"No profile for {phantom_id[:8]}")
            return False

        try:
            from playwright.async_api import async_playwright

            pw_options = self.browser_manager.get_playwright_context_options(phantom_id)
            fp_script = self.browser_manager.get_fingerprint_injection_script(phantom_id)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(**pw_options)
                await context.add_init_script(fp_script)
                page = await context.new_page()

                task_type = task["type"]
                duration = task.get("duration_s", 30)

                if task_type == "check_gmail":
                    await self._check_gmail(page)
                elif task_type == "watch_youtube":
                    await self._watch_youtube(page, task.get("query", "trending"), duration)
                elif task_type == "google_search":
                    await self._do_google_search(page, task.get("query", "weather"))
                elif task_type == "browse_sites":
                    await self._browse_random_sites(page, task.get("urls", AGING_SITES[:3]))
                elif task_type == "send_test_email":
                    await self._send_test_email(page)
                elif task_type == "star_github_repos":
                    await self._star_github_repos(page, task.get("count", 3))
                else:
                    # Generic: just visit a random site
                    await page.goto(random.choice(AGING_SITES), timeout=15000)
                    await asyncio.sleep(duration)

                # Save session state
                storage = await context.storage_state()
                self.browser_manager.save_session_state(phantom_id, storage)
                cookies = await context.cookies()
                self.browser_manager.update_profile_state(
                    phantom_id, "warming",
                    cookies_count=len(cookies),
                )

                await browser.close()

            return True

        except Exception as e:
            logger.error(f"Aging task '{task.get('type')}' failed for {phantom_id[:8]}: {e}")
            return False

    async def run_daily_aging(self, phantom_id: str) -> dict:
        """Run all today's aging tasks for a phantom."""
        profile = self.browser_manager.get_profile(phantom_id)
        if not profile:
            return {"error": "Profile not found"}

        tasks = await self.get_aging_tasks(phantom_id, profile.age_days)
        results = {"phantom_id": phantom_id, "day": profile.age_days + 1,
                    "tasks_total": len(tasks), "tasks_completed": 0, "tasks_failed": 0}

        for task in tasks:
            success = await self.execute_aging_task(phantom_id, task)
            if success:
                results["tasks_completed"] += 1
            else:
                results["tasks_failed"] += 1
            # Wait between tasks
            await asyncio.sleep(random.uniform(5, 30))

        # Check if aging is complete (30 days)
        if profile.age_days >= 30:
            self.browser_manager.update_profile_state(phantom_id, "aged")
            results["aging_complete"] = True

        return results

    async def _check_gmail(self, page) -> bool:
        """Open Gmail briefly."""
        try:
            await page.goto("https://mail.google.com", timeout=15000)
            await asyncio.sleep(random.uniform(5, 15))
            return True
        except Exception:
            return False

    async def _watch_youtube(self, page, query: str, duration: int = 120) -> bool:
        """Browse YouTube and watch a video."""
        try:
            await page.goto(f"https://www.youtube.com/results?search_query={query}", timeout=15000)
            await asyncio.sleep(3)

            # Click first video result
            video = await page.query_selector('a#video-title, ytd-video-renderer a')
            if video:
                await video.click()
                # Watch for specified duration
                await asyncio.sleep(min(duration, 180))
            else:
                await asyncio.sleep(30)

            return True
        except Exception:
            return False

    async def _do_google_search(self, page, query: str) -> bool:
        """Perform a Google search and browse results."""
        try:
            encoded_query = query.replace(" ", "+")
            await page.goto(f"https://www.google.com/search?q={encoded_query}", timeout=15000)
            await asyncio.sleep(random.uniform(3, 8))

            # Click a result
            results = await page.query_selector_all('a[href^="http"]:not([href*="google"])')
            if results and len(results) > 2:
                target = random.choice(results[1:4])
                await target.click()
                await asyncio.sleep(random.uniform(5, 15))

            return True
        except Exception:
            return False

    async def _browse_random_sites(self, page, urls: list[str]) -> int:
        """Visit random popular sites to accumulate cookies."""
        visited = 0
        for url in urls:
            try:
                await page.goto(url, timeout=15000)
                await asyncio.sleep(random.uniform(5, 20))

                # Scroll down to simulate reading
                await page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(random.uniform(2, 5))

                visited += 1
            except Exception:
                pass
        return visited

    async def _send_test_email(self, page) -> bool:
        """Send a test email to self via Gmail."""
        try:
            await page.goto("https://mail.google.com/mail/u/0/#inbox?compose=new", timeout=15000)
            await asyncio.sleep(3)

            # Gmail compose
            to_field = await page.query_selector('input[name="to"], div[aria-label="To"]')
            if to_field:
                identity = self.vault.get_identity("") if self.vault else None
                email = identity.get("google", {}).get("email", "test@gmail.com") if identity else "test@gmail.com"
                await to_field.fill(email)

            subject = await page.query_selector('input[name="subjectbox"]')
            if subject:
                await subject.fill("Test message")

            body = await page.query_selector('div[aria-label="Message Body"], div[role="textbox"]')
            if body:
                await body.fill("This is a test message.")

            send = await page.query_selector('div[aria-label="Send"]')
            if send:
                await send.click()
                await asyncio.sleep(3)

            return True
        except Exception:
            return False

    async def _star_github_repos(self, page, count: int = 3) -> int:
        """Star popular GitHub repositories."""
        popular_repos = [
            "https://github.com/tensorflow/tensorflow",
            "https://github.com/torvalds/linux",
            "https://github.com/microsoft/vscode",
            "https://github.com/facebook/react",
            "https://github.com/python/cpython",
            "https://github.com/rust-lang/rust",
            "https://github.com/golang/go",
        ]

        starred = 0
        repos = random.sample(popular_repos, min(count, len(popular_repos)))

        for repo_url in repos:
            try:
                await page.goto(repo_url, timeout=15000)
                await asyncio.sleep(2)

                star_btn = await page.query_selector(
                    'button:has-text("Star"), form[action*="star"] button'
                )
                if star_btn:
                    await star_btn.click()
                    await asyncio.sleep(2)
                    starred += 1
            except Exception:
                pass

        return starred
