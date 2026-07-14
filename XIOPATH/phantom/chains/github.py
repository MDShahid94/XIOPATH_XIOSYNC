"""
XIOPATH Phantom Infrastructure — GitHub / Colab / Kaggle Chains
=================================================================
OAuth cascade registrations from authenticated Google session.

Educational purpose only.
"""

import json
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("phantom.chains.github")


class GitHubChain:
    """Registers GitHub via Google OAuth and creates full-permission PAT."""

    def __init__(self, google_session_cookies: dict, browser_profile_options: dict,
                 fingerprint_script: str):
        self.google_cookies = google_session_cookies
        self.browser_options = browser_profile_options
        self.fingerprint_script = fingerprint_script

    async def register(self) -> dict:
        """Sign up to GitHub via 'Sign in with Google' OAuth."""
        from playwright.async_api import async_playwright

        result = {"success": False, "username": None, "email": None, "error": None}

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                opts = {**self.browser_options}
                if self.google_cookies.get("storage_state"):
                    opts["storage_state"] = self.google_cookies["storage_state"]

                context = await browser.new_context(**opts)
                await context.add_init_script(self.fingerprint_script)
                if self.google_cookies.get("cookies"):
                    await context.add_cookies(self.google_cookies["cookies"])

                page = await context.new_page()
                await page.goto("https://github.com/login", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # Click 'Sign in with Google'
                google_btn = await page.query_selector(
                    'button:has-text("Sign in with Google"), a[href*="google"], '
                    'button.js-google-login'
                )
                if google_btn:
                    await google_btn.click()
                    await asyncio.sleep(3)

                # Handle Google OAuth consent
                if "accounts.google.com" in page.url:
                    allow_btn = await page.query_selector(
                        'button:has-text("Allow"), button:has-text("Continue")'
                    )
                    if allow_btn:
                        await allow_btn.click()
                        await asyncio.sleep(5)

                # Handle GitHub username selection (new accounts)
                username_input = await page.query_selector('input[name="user[login]"], input#login_field')
                if username_input and "join" in page.url.lower():
                    import random
                    username = f"xp-{random.randint(1000, 9999)}"
                    await username_input.fill(username)
                    await asyncio.sleep(1)

                    submit_btn = await page.query_selector('button[type="submit"]')
                    if submit_btn:
                        await submit_btn.click()
                        await asyncio.sleep(3)

                # Extract username from profile
                if "github.com" in page.url:
                    try:
                        username = await page.evaluate("""
                            () => {
                                const meta = document.querySelector('meta[name="user-login"]');
                                return meta ? meta.content : null;
                            }
                        """)
                        result["username"] = username
                        result["success"] = True
                    except Exception:
                        result["success"] = "github.com" in page.url

                await browser.close()

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"GitHub registration failed: {e}")

        return result

    async def create_personal_access_token(self, page) -> dict:
        """
        Create a classic PAT with maximum scopes, no expiration.
        Scopes: repo, workflow, admin:org, gist, delete_repo, write:packages, admin:repo_hook
        """
        result = {"token": None, "scopes": [], "error": None}

        try:
            await page.goto("https://github.com/settings/tokens/new", timeout=15000)
            await asyncio.sleep(2)

            # Token note/description
            note_input = await page.query_selector('input[name="note"], input#description')
            if note_input:
                await note_input.fill(f"XIOPATH-Mesh-Full-Access")

            # Set no expiration
            expiry_select = await page.query_selector('select[name="expiration"]')
            if expiry_select:
                await expiry_select.select_option(label="No expiration")
                await asyncio.sleep(0.5)

            # Select all maximum scopes
            max_scopes = ["repo", "workflow", "admin:org", "gist", "delete_repo",
                          "write:packages", "admin:repo_hook"]

            for scope in max_scopes:
                try:
                    checkbox = await page.query_selector(f'input[value="{scope}"], input[name="scopes[]"][value="{scope}"]')
                    if checkbox:
                        is_checked = await checkbox.is_checked()
                        if not is_checked:
                            await checkbox.click()
                            result["scopes"].append(scope)
                            await asyncio.sleep(0.2)
                except Exception:
                    pass

            # Generate token
            submit_btn = await page.query_selector('button:has-text("Generate token"), button[type="submit"]')
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(3)

            # Extract the token (shown once)
            token_el = await page.query_selector('code, div.flash-full code, span[id*="token"]')
            if token_el:
                result["token"] = (await token_el.text_content()).strip()

        except Exception as e:
            result["error"] = str(e)

        return result

    async def setup_initial_repo(self, page, repo_name: str = "xiopath-node") -> dict:
        """Create an initial private repository."""
        result = {"success": False, "repo_url": None, "error": None}

        try:
            await page.goto("https://github.com/new", timeout=15000)
            await asyncio.sleep(2)

            name_input = await page.query_selector('input[name="repository[name]"], input#repository_name')
            if name_input:
                await name_input.fill(repo_name)
                await asyncio.sleep(1)

            # Select private
            private_radio = await page.query_selector('input[value="private"], input#repository_visibility_private')
            if private_radio:
                await private_radio.click()

            # Initialize with README
            readme_check = await page.query_selector('input[name="repository[auto_init]"]')
            if readme_check and not await readme_check.is_checked():
                await readme_check.click()

            submit = await page.query_selector('button:has-text("Create repository"), button[type="submit"]')
            if submit:
                await submit.click()
                await asyncio.sleep(3)

            if "github.com" in page.url and repo_name in page.url:
                result["success"] = True
                result["repo_url"] = page.url

        except Exception as e:
            result["error"] = str(e)

        return result
