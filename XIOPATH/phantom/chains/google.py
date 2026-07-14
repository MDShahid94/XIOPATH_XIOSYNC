"""
XIOPATH Phantom Infrastructure — Google Account Chain
======================================================
Automated Google account creation using anti-detect browser profiles
with human behavioral simulation.

Educational purpose only.
"""

import json
import time
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("phantom.chains.google")


class GoogleAccountCreator:
    """
    Automates Google account creation using Playwright with
    anti-detect fingerprinting and human-like interaction patterns.
    """

    SIGNUP_URL = "https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp"
    SECURITY_URL = "https://myaccount.google.com/security"

    def __init__(self, identity: dict, browser_profile_options: dict,
                 fingerprint_script: str, proxy_config: dict = None):
        """
        Args:
            identity: Synthetic identity dict from IdentityForge
            browser_profile_options: Playwright context options from BrowserProfileManager
            fingerprint_script: JS fingerprint injection script
            proxy_config: Optional proxy config {server, username, password}
        """
        self.identity = identity
        self.browser_options = browser_profile_options
        self.fingerprint_script = fingerprint_script
        self.proxy_config = proxy_config

    async def create_account(self) -> dict:
        """
        Execute the full Google account creation flow.
        
        Returns:
            {success, email, password, session_cookies, verification_needed, error}
        """
        from playwright.async_api import async_playwright
        from phantom.human_sim import HumanInteraction

        human = HumanInteraction(self.identity.get("username", "default"))
        result = {
            "success": False,
            "email": None,
            "password": None,
            "session_cookies": None,
            "verification_needed": None,
            "error": None,
        }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context(**self.browser_options)
                await context.add_init_script(self.fingerprint_script)
                page = await context.new_page()

                # ── Step 1: Navigate to signup ──
                await page.goto(self.SIGNUP_URL, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # ── Step 2: Fill name fields ──
                first_name_sel = 'input[name="firstName"]'
                last_name_sel = 'input[name="lastName"]'

                await page.wait_for_selector(first_name_sel, timeout=10000)
                await self._human_type(page, first_name_sel, self.identity["first_name"], human)
                await asyncio.sleep(0.3)
                await self._human_type(page, last_name_sel, self.identity["last_name"], human)

                # Click Next
                await self._human_click(page, 'button:has-text("Next"), div[id="identifierNext"] button', human)
                await asyncio.sleep(2)

                # ── Step 3: Fill birthday and gender ──
                await page.wait_for_selector('select[id="month"]', timeout=10000)

                # Month dropdown
                dob_parts = self.identity["dob"].split("-")
                month_num = str(int(dob_parts[1]))
                await page.select_option('select[id="month"]', month_num)
                await asyncio.sleep(0.5)

                # Day
                await self._human_type(page, 'input[name="day"]', dob_parts[2], human)
                # Year
                await self._human_type(page, 'input[name="year"]', dob_parts[0], human)

                # Gender dropdown
                gender_map = {"male": "1", "female": "2", "unspecified": "4"}
                gender_val = gender_map.get(self.identity["gender"], "4")
                await page.select_option('select[id="gender"]', gender_val)

                await self._human_click(page, 'button:has-text("Next")', human)
                await asyncio.sleep(2)

                # ── Step 4: Choose username ──
                # Google may offer suggested usernames or a custom field
                custom_option = await page.query_selector('div[data-value="custom"]')
                if custom_option:
                    await custom_option.click()
                    await asyncio.sleep(1)

                username_sel = 'input[name="Username"]'
                if await page.query_selector(username_sel):
                    await self._human_type(page, username_sel, self.identity["username"], human)

                await self._human_click(page, 'button:has-text("Next")', human)
                await asyncio.sleep(2)

                # ── Step 5: Set password ──
                password_sel = 'input[name="Passwd"]'
                confirm_sel = 'input[name="PasswdAgain"], input[name="ConfirmPasswd"]'

                await page.wait_for_selector(password_sel, timeout=10000)
                await self._human_type(page, password_sel, self.identity["password"], human)
                await asyncio.sleep(0.3)

                confirm = await page.query_selector(confirm_sel)
                if confirm:
                    await self._human_type(page, confirm_sel, self.identity["password"], human)

                await self._human_click(page, 'button:has-text("Next")', human)
                await asyncio.sleep(3)

                # ── Step 6: Handle verification challenges ──
                challenge = await self._detect_challenge_type(page)
                if challenge != "none":
                    result["verification_needed"] = {
                        "type": challenge,
                        "data": await self._extract_challenge_data(page, challenge),
                    }
                    logger.info(f"Verification required: {challenge}")
                    # Return here — caller must handle verification
                    result["email"] = f"{self.identity['username']}@gmail.com"
                    result["password"] = self.identity["password"]
                    # Keep browser alive for verification
                    return result

                # ── Step 7: Skip phone/recovery (if optional) ──
                skip_btn = await page.query_selector('button:has-text("Skip"), a:has-text("Skip")')
                if skip_btn:
                    await skip_btn.click()
                    await asyncio.sleep(2)

                # ── Step 8: Accept Terms ──
                agree_btn = await page.query_selector(
                    'button:has-text("I agree"), button:has-text("Accept"), '
                    'button[jsname="LgbsSe"]'
                )
                if agree_btn:
                    await agree_btn.click()
                    await asyncio.sleep(3)

                # ── Step 9: Export session ──
                cookies = await context.cookies()
                storage = await context.storage_state()

                result["success"] = True
                result["email"] = f"{self.identity['username']}@gmail.com"
                result["password"] = self.identity["password"]
                result["session_cookies"] = {
                    "cookies": cookies,
                    "storage_state": storage,
                }

                await browser.close()

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Account creation failed: {e}")

        return result

    async def handle_verification(self, page, verification_response: dict) -> bool:
        """
        Process verification response from the member.
        
        Args:
            page: Active Playwright page
            verification_response: {type: 'otp'|'link', value: '123456' or URL}
        """
        resp_type = verification_response.get("type")
        value = verification_response.get("value")

        try:
            if resp_type == "otp":
                otp_input = await page.query_selector(
                    'input[name="code"], input[type="tel"][aria-label*="code"]'
                )
                if otp_input:
                    await otp_input.fill(value)
                    await asyncio.sleep(0.5)
                    next_btn = await page.query_selector('button:has-text("Next"), button:has-text("Verify")')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(3)
                        return True

            elif resp_type == "link":
                # Member clicked the verification link on their device
                # Wait for the page to auto-advance
                await asyncio.sleep(5)
                return True

        except Exception as e:
            logger.error(f"Verification handling failed: {e}")

        return False

    async def _detect_challenge_type(self, page) -> str:
        """Detect what verification Google is requesting."""
        try:
            content = await page.content()
            url = page.url

            if "challenge/dp" in url or "phone" in url.lower():
                return "phone_otp"
            if "challenge/az" in url:
                return "captcha"
            if "challenge/ipp" in url:
                return "identity_verification"

            # Check for QR code image
            qr_img = await page.query_selector('img[src*="chart.googleapis"], img[alt*="QR"]')
            if qr_img:
                return "qr_code"

            # Check for OTP input
            otp_input = await page.query_selector('input[name="code"]')
            if otp_input:
                return "sms_otp"

            # Check for email verification
            if "recovery" in content.lower() or "verify" in content.lower():
                return "email_verify"

        except Exception:
            pass

        return "none"

    async def _extract_challenge_data(self, page, challenge_type: str) -> dict:
        """Extract data needed for the member to complete verification."""
        data = {"type": challenge_type}

        try:
            if challenge_type == "qr_code":
                from phantom.qr_tools import qr_to_verify_link
                qr_img = await page.query_selector('img[src*="chart.googleapis"], img[alt*="QR"]')
                if qr_img:
                    src = await qr_img.get_attribute("src")
                    if src:
                        data["qr_src"] = src
                        # Try to convert QR to link
                        link_info = qr_to_verify_link(src)
                        data["verify_link"] = link_info

            elif challenge_type in ("phone_otp", "sms_otp"):
                data["instruction"] = "Enter the OTP sent to the verification device"

            elif challenge_type == "email_verify":
                data["instruction"] = "Check email for verification link"

        except Exception as e:
            data["extraction_error"] = str(e)

        return data

    async def _human_type(self, page, selector: str, text: str, human) -> None:
        """Type text with human-like timing."""
        keystrokes = human.typer.generate_keystrokes(text)
        element = await page.query_selector(selector)
        if not element:
            await page.wait_for_selector(selector, timeout=5000)

        for ks in keystrokes:
            if ks["action"] == "press":
                await page.type(selector, ks["char"], delay=0)
                await asyncio.sleep(ks["delay_ms"] / 1000)
            elif ks["action"] == "backspace":
                await page.keyboard.press("Backspace")
                await asyncio.sleep(ks["delay_ms"] / 1000)
            elif ks["action"] == "pause":
                await asyncio.sleep(ks["delay_ms"] / 1000)

    async def _human_click(self, page, selector: str, human) -> None:
        """Click with human-like delay."""
        import random
        delay = random.uniform(0.3, 1.0)
        await asyncio.sleep(delay)
        try:
            await page.click(selector, timeout=5000)
        except Exception:
            # Try clicking first matching element
            elements = await page.query_selector_all(selector.split(",")[0].strip())
            if elements:
                await elements[0].click()

    async def export_session(self, page) -> dict:
        """Export cookies and storage state from the current page context."""
        context = page.context
        return {
            "cookies": await context.cookies(),
            "storage_state": await context.storage_state(),
        }


class GoogleSessionManager:
    """Manages Google session persistence and restoration."""

    async def restore_session(self, session_data: dict, browser_profile_options: dict,
                               fingerprint_script: str):
        """
        Restore a Google session from saved cookies/storage state.
        
        Returns:
            (browser, context, page) tuple
        """
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=False)

        # Inject saved storage state into context options
        opts = {**browser_profile_options}
        if session_data.get("storage_state"):
            opts["storage_state"] = session_data["storage_state"]

        context = await browser.new_context(**opts)
        await context.add_init_script(fingerprint_script)

        # Add cookies if not in storage state
        if session_data.get("cookies"):
            await context.add_cookies(session_data["cookies"])

        page = await context.new_page()
        return browser, context, page

    async def verify_session_alive(self, page) -> bool:
        """Check if the Google session is still authenticated."""
        try:
            await page.goto("https://myaccount.google.com", timeout=15000)
            await asyncio.sleep(2)
            # If redirected to login, session is dead
            if "accounts.google.com/signin" in page.url.lower():
                return False
            # Check for profile indicator
            profile = await page.query_selector('a[aria-label*="Account"], img[data-profile-identifier]')
            return profile is not None
        except Exception:
            return False

    async def navigate_to_security(self, page) -> None:
        """Navigate to the Google Account security settings."""
        await page.goto("https://myaccount.google.com/security", timeout=15000)
        await asyncio.sleep(2)
