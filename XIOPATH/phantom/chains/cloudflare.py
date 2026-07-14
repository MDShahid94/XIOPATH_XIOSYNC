"""
XIOPATH Phantom Infrastructure — Cloudflare Chain
===================================================
Registers phantom Cloudflare accounts via Google OAuth
and creates maximum-permission API tokens.

Educational purpose only.
"""

import json
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("phantom.chains.cloudflare")

# Maximum permission token specification (per A.4 in the plan)
CF_TOKEN_PERMISSIONS = {
    "Workers Scripts":     {"permission_group": "workers_scripts", "access": "edit"},
    "Workers KV Storage":  {"permission_group": "workers_kv_storage", "access": "edit"},
    "Workers R2 Storage":  {"permission_group": "workers_r2_storage", "access": "edit"},
    "D1":                  {"permission_group": "d1", "access": "edit"},
    "Durable Objects":     {"permission_group": "durable_objects", "access": "edit"},
    "Queues":              {"permission_group": "queues", "access": "edit"},
    "Vectorize":           {"permission_group": "vectorize", "access": "edit"},
    "Cloudflare Pages":    {"permission_group": "pages", "access": "edit"},
    "DNS":                 {"permission_group": "dns", "access": "edit"},
    "SSL Certificates":    {"permission_group": "ssl_certs", "access": "edit"},
    "Zone Settings":       {"permission_group": "zone_settings", "access": "edit"},
}


class CloudflareChain:
    """
    Registers a Cloudflare account via 'Sign in with Google' OAuth
    and creates full-permission API tokens.
    """

    SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
    DASHBOARD_URL = "https://dash.cloudflare.com"
    TOKEN_URL_TEMPLATE = "https://dash.cloudflare.com/{account_id}/profile/api-tokens"

    def __init__(self, google_session_cookies: dict, browser_profile_options: dict,
                 fingerprint_script: str):
        self.google_cookies = google_session_cookies
        self.browser_options = browser_profile_options
        self.fingerprint_script = fingerprint_script

    async def register(self) -> dict:
        """
        Register a Cloudflare account using 'Sign in with Google'.
        
        Returns:
            {success, account_id, email, session_cookies, error}
        """
        from playwright.async_api import async_playwright

        result = {"success": False, "account_id": None, "email": None,
                  "session_cookies": None, "error": None}

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

                # Navigate to CF signup
                await page.goto(self.SIGNUP_URL, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # Click 'Sign in with Google'
                google_btn = await page.query_selector(
                    'button[data-provider="google"], a[href*="google"], '
                    'button:has-text("Sign in with Google"), '
                    'button:has-text("Continue with Google")'
                )
                if google_btn:
                    await google_btn.click()
                    await asyncio.sleep(3)

                    # Handle Google OAuth consent screen (should auto-consent)
                    # Check if we're on a Google consent page
                    if "accounts.google.com" in page.url:
                        allow_btn = await page.query_selector(
                            'button:has-text("Allow"), button:has-text("Continue"), '
                            'button[id="submit_approve_access"]'
                        )
                        if allow_btn:
                            await allow_btn.click()
                            await asyncio.sleep(5)

                # Wait for dashboard to load
                await page.wait_for_url("**/dash.cloudflare.com/**", timeout=30000)
                await asyncio.sleep(3)

                # Extract account ID from URL
                current_url = page.url
                # CF dashboard URL format: dash.cloudflare.com/<account_id>/...
                parts = current_url.split("dash.cloudflare.com/")
                if len(parts) > 1:
                    account_id = parts[1].split("/")[0].split("?")[0]
                    if len(account_id) == 32:  # CF account IDs are 32 hex chars
                        result["account_id"] = account_id

                # If no account ID from URL, try to extract from page
                if not result["account_id"]:
                    try:
                        account_id = await page.evaluate("""
                            () => {
                                const url = window.location.href;
                                const match = url.match(/dash\\.cloudflare\\.com\\/([a-f0-9]{32})/);
                                return match ? match[1] : null;
                            }
                        """)
                        result["account_id"] = account_id
                    except Exception:
                        pass

                # Export session
                result["session_cookies"] = {
                    "cookies": await context.cookies(),
                    "storage_state": await context.storage_state(),
                }
                result["success"] = True
                result["email"] = self.google_cookies.get("email", "")

                await browser.close()

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"CF registration failed: {e}")

        return result

    async def create_api_token(self, page) -> dict:
        """
        Create a custom API token with maximum permissions via the CF dashboard.
        All permissions set to EDIT, all accounts scope, NO expiration.
        
        Returns:
            {token, permissions, error}
        """
        result = {"token": None, "permissions": [], "error": None}

        try:
            # Navigate to API tokens page
            await page.goto("https://dash.cloudflare.com/profile/api-tokens", timeout=20000)
            await asyncio.sleep(3)

            # Click 'Create Token'
            create_btn = await page.query_selector(
                'button:has-text("Create Token"), a:has-text("Create Token")'
            )
            if create_btn:
                await create_btn.click()
                await asyncio.sleep(2)

            # Select 'Create Custom Token'
            custom_btn = await page.query_selector(
                'button:has-text("Custom token"), button:has-text("Get started"), '
                'a:has-text("Create Custom Token")'
            )
            if custom_btn:
                await custom_btn.click()
                await asyncio.sleep(2)

            # Fill token name
            name_input = await page.query_selector('input[name="name"], input[placeholder*="name"]')
            if name_input:
                await name_input.fill(f"XIOPATH-Full-Access-{int(asyncio.get_event_loop().time())}")
                await asyncio.sleep(0.5)

            # Add permissions (click 'Add permission' for each)
            permissions_added = []
            for perm_name, perm_config in CF_TOKEN_PERMISSIONS.items():
                try:
                    add_btn = await page.query_selector('button:has-text("Add more")')
                    if add_btn and len(permissions_added) > 0:
                        await add_btn.click()
                        await asyncio.sleep(1)

                    # Select permission group from dropdowns
                    # CF uses multiple cascading dropdowns
                    selects = await page.query_selector_all('select')
                    for select in selects:
                        options = await select.query_selector_all('option')
                        for option in options:
                            text = await option.text_content()
                            if perm_name.lower() in text.lower():
                                await select.select_option(value=await option.get_attribute("value"))
                                break

                    permissions_added.append(perm_name)
                except Exception as e:
                    logger.debug(f"Could not add permission {perm_name}: {e}")

            # Set scope to 'All accounts'
            scope_selects = await page.query_selector_all('select[name*="scope"], select[name*="account"]')
            for sel in scope_selects:
                try:
                    options = await sel.query_selector_all('option')
                    for opt in options:
                        text = await opt.text_content()
                        if "all" in text.lower() and "account" in text.lower():
                            await sel.select_option(value=await opt.get_attribute("value"))
                            break
                except Exception:
                    pass

            # Ensure no expiration (leave TTL/expiry fields blank)
            expiry_inputs = await page.query_selector_all('input[name*="expir"], input[type="date"]')
            for inp in expiry_inputs:
                await inp.fill("")

            # Click 'Continue to summary' then 'Create Token'
            continue_btn = await page.query_selector(
                'button:has-text("Continue"), button:has-text("Summary")'
            )
            if continue_btn:
                await continue_btn.click()
                await asyncio.sleep(2)

            create_final = await page.query_selector(
                'button:has-text("Create Token"), button[type="submit"]'
            )
            if create_final:
                await create_final.click()
                await asyncio.sleep(3)

            # Extract the token (shown once on the confirmation page)
            token_element = await page.query_selector(
                'code, input[readonly][value], div[data-testid="token-value"], '
                'span.token-value, pre'
            )
            if token_element:
                token_text = await token_element.text_content()
                if not token_text:
                    token_text = await token_element.get_attribute("value")
                if token_text:
                    result["token"] = token_text.strip()

            result["permissions"] = permissions_added

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"API token creation failed: {e}")

        return result

    async def create_api_token_via_api(self, email: str, session_cookies: dict) -> dict:
        """
        Alternative: Create API token using CF's internal dashboard API.
        This avoids complex UI automation.
        """
        import urllib.request

        result = {"token": None, "error": None}

        # Extract CF auth tokens from cookies
        cf_cookies = {}
        for cookie in session_cookies.get("cookies", []):
            if cookie.get("domain", "").endswith("cloudflare.com"):
                cf_cookies[cookie["name"]] = cookie["value"]

        cookie_header = "; ".join(f"{k}={v}" for k, v in cf_cookies.items())

        # CF dashboard API for token creation
        # This endpoint is used internally by the CF dashboard
        api_url = "https://api.cloudflare.com/client/v4/user/tokens"

        policies = []
        for perm_name, perm_config in CF_TOKEN_PERMISSIONS.items():
            policies.append({
                "effect": "allow",
                "resources": {"com.cloudflare.api.account.*": "*"},
                "permission_groups": [{"id": perm_config["permission_group"]}],
            })

        token_payload = {
            "name": f"XIOPATH-Full-{int(time.time())}",
            "policies": policies,
            "not_before": "",
            "expires_on": "",  # No expiration
        }

        try:
            body = json.dumps(token_payload).encode()
            req = urllib.request.Request(
                api_url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Cookie": cookie_header,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            if data.get("success") and data.get("result", {}).get("value"):
                result["token"] = data["result"]["value"]

        except Exception as e:
            result["error"] = str(e)

        return result

    async def enable_all_services(self, page) -> dict:
        """
        Navigate through CF dashboard to enable all free-tier services.
        Workers, D1, R2, KV, Queues, Vectorize are enabled by visiting their pages.
        """
        services_enabled = []

        service_paths = [
            ("/workers-and-pages", "Workers & Pages"),
            ("/r2", "R2 Storage"),
            ("/d1", "D1 Database"),
            ("/queues", "Queues"),
            ("/vectorize", "Vectorize"),
        ]

        for path, name in service_paths:
            try:
                await page.goto(f"https://dash.cloudflare.com{path}", timeout=15000)
                await asyncio.sleep(2)

                # Click any 'Get Started', 'Enable', or 'Subscribe' buttons
                enable_btn = await page.query_selector(
                    'button:has-text("Get started"), button:has-text("Enable"), '
                    'button:has-text("Subscribe to"), a:has-text("Get started")'
                )
                if enable_btn:
                    await enable_btn.click()
                    await asyncio.sleep(2)

                services_enabled.append(name)
            except Exception as e:
                logger.debug(f"Could not enable {name}: {e}")

        return {"services_enabled": services_enabled}
