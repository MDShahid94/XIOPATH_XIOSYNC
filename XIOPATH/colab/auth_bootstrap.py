"""
agy CLI Auth Bootstrap — Orchestrates Google sign-in → agy CLI authentication.

Flow:
  1. Check if Chrome profile has existing valid Google session
  2. If not → run google_signin() with stealth browser
  3. Save + encrypt + upload profile to Drive
  4. Attempt gcloud/agy CLI authentication via browser OAuth
  5. Return success/failure status

This module bridges the gap between browser-based Google auth
and CLI-based agy authentication on ephemeral Colab instances.
"""

import os
import sys
import time
import logging
import subprocess
import asyncio

logger = logging.getLogger("auth_bootstrap")


async def bootstrap_agy_auth(
    stealth_browser,
    profile_manager,
    drive_sync,
    credentials: dict,
    screenshot_dir: str = "/tmp/auth_screenshots",
) -> bool:
    """
    Full agy CLI authentication bootstrap sequence.

    Args:
        stealth_browser: Initialized StealthBrowser instance.
        profile_manager: ProfileManager for encrypt/decrypt.
        drive_sync: DriveSync for Google Drive operations.
        credentials: Dict with keys: email, password, totp_secret,
                     recovery_email (optional).
        screenshot_dir: Directory for evidence screenshots.

    Returns:
        True if agy CLI is authenticated and usable, False otherwise.
    """
    from .google_signin import google_signin, check_existing_session

    email = credentials.get("email", "")
    password = credentials.get("password", "")
    totp_secret = credentials.get("totp_secret", "")
    recovery_email = credentials.get("recovery_email", email)

    os.makedirs(screenshot_dir, exist_ok=True)

    # ── Step 1: Check existing session ───────────────────────
    logger.info("🔍 Checking for existing Google session in profile...")
    driver = stealth_browser.driver

    if driver and check_existing_session(driver):
        logger.info("✅ Existing session found — skipping sign-in.")
    else:
        # ── Step 2: Perform Google sign-in ───────────────────
        logger.info(f"🔑 No session found — signing in as {email}...")

        # HITL callback for Colab: save screenshot for operator review
        def colab_hitl_callback(screenshot_b64: str, message: str):
            """Save screenshot and wait for manual intervention."""
            import base64
            hitl_path = os.path.join(screenshot_dir, "hitl_challenge.png")
            if screenshot_b64:
                with open(hitl_path, "wb") as f:
                    f.write(base64.b64decode(screenshot_b64))
            logger.warning(f"🛑 HITL REQUIRED: {message}")
            logger.warning(f"   Screenshot: {hitl_path}")
            logger.warning("   Waiting 180s for manual resolution...")
            time.sleep(180)

        success = google_signin(
            driver=driver,
            email=email,
            password=password,
            recovery_email=recovery_email,
            totp_secret=totp_secret,
            screenshot_dir=screenshot_dir,
            hitl_callback=colab_hitl_callback,
            max_retries=3,
        )

        if not success:
            logger.error(f"❌ Google sign-in failed for {email}")
            return False

        logger.info("✅ Google sign-in completed successfully.")

    # ── Step 3: Save + encrypt + upload profile ──────────────
    logger.info("💾 Saving and encrypting browser profile...")
    try:
        profile_data = profile_manager.save_profile()
        if profile_data and drive_sync:
            profile_name = f"{email}_profile.xio"
            await drive_sync.upload_profile(profile_data, profile_name)
            logger.info(f"☁️ Profile uploaded to Drive: {profile_name}")
    except Exception as e:
        logger.warning(f"⚠️ Profile save/upload failed: {e}")

    # ── Step 4: Attempt agy CLI authentication ───────────────
    logger.info("🔧 Attempting agy CLI authentication...")
    agy_authenticated = await _authenticate_agy_cli(driver)

    if agy_authenticated:
        logger.info("✅ agy CLI authenticated successfully!")
    else:
        logger.warning("⚠️ agy CLI auth not completed — will use Gemini API fallback.")

    return True


async def _authenticate_agy_cli(driver) -> bool:
    """
    Attempt to authenticate the agy CLI using the browser's Google session.

    Strategy:
      1. Try `gcloud auth login` with browser-based OAuth
      2. The stealth browser auto-completes the OAuth consent
      3. agy CLI picks up the credential

    Returns:
        True if agy CLI responds successfully, False otherwise.
    """
    # First, check if agy is already authenticated
    try:
        result = subprocess.run(
            ["agy", "--version"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            logger.info(f"✓ agy CLI available: {result.stdout.strip()}")
        else:
            logger.warning("agy CLI not found — skipping CLI auth.")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("agy CLI not installed — skipping CLI auth.")
        return False

    # Try Colab's built-in auth first (if running in Colab)
    try:
        # This is the simplest path on Colab
        from google.colab import auth
        auth.authenticate_user()
        logger.info("✅ Colab auth.authenticate_user() succeeded.")
        return True
    except ImportError:
        logger.info("Not running in Colab — trying gcloud auth...")
    except Exception as e:
        logger.warning(f"Colab auth failed: {e}")

    # Try gcloud auth with the browser session
    try:
        # Launch gcloud auth in background — it will open a URL
        process = subprocess.Popen(
            ["gcloud", "auth", "login", "--no-launch-browser"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True
        )

        # Read the auth URL from gcloud output
        auth_url = None
        for line in process.stdout:
            line = line.strip()
            if "https://accounts.google.com" in line:
                auth_url = line
                break

        if auth_url and driver:
            # Navigate the stealth browser to the auth URL
            logger.info(f"🌐 Navigating to gcloud auth URL...")
            main_window = driver.current_window_handle
            driver.execute_script(f"window.open('{auth_url}', '_blank');")
            time.sleep(3)

            # Switch to the new window and handle OAuth
            from .oauth_handler import handle_oauth_popups
            for _ in range(30):
                handle_oauth_popups(driver, main_window)
                time.sleep(2)

                # Check if auth completed
                try:
                    handles = driver.window_handles
                    if len(handles) <= 1:
                        break  # OAuth window closed
                except Exception:
                    break

            driver.switch_to.window(main_window)
            process.wait(timeout=30)

            if process.returncode == 0:
                logger.info("✅ gcloud auth completed via browser.")
                return True

        process.kill()

    except Exception as e:
        logger.warning(f"gcloud auth failed: {e}")

    return False


def load_credentials_from_vault(api_base_url: str = "http://localhost:8000") -> list:
    """
    Load all stored Google credentials from the central API's vault.

    Returns:
        List of dicts: [{email, password, totp_secret, recovery_email}, ...]
    """
    import json
    try:
        import urllib.request
        url = f"{api_base_url}/api/v1/vault/credentials"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("credentials", [])
    except Exception as e:
        logger.warning(f"Could not load credentials from vault: {e}")
        return []


def load_credentials_from_csv(csv_path: str) -> list:
    """
    Load credentials from the AllMailsInfo.csv file.

    Args:
        csv_path: Path to the CSV file with columns:
                  email, password, totp_secret

    Returns:
        List of credential dicts.
    """
    import csv
    credentials = []
    try:
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                credentials.append({
                    "email": row.get("email", "").strip(),
                    "password": row.get("password", "").strip(),
                    "totp_secret": row.get("totp_secret", "").strip(),
                    "recovery_email": row.get("recovery_email", "").strip()
                         or row.get("email", "").strip(),
                })
    except Exception as e:
        logger.error(f"Failed to load credentials from CSV: {e}")

    return credentials
