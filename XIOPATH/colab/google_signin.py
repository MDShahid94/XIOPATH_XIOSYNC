"""
Google Sign-In Automation — Ported from XIO_VERSE google_signin.py.

Full Google sign-in automation with support for:
  - Email + password entry
  - reCAPTCHA detection (pauses for human)
  - TOTP (Google Authenticator) 2FA — selects "Google Authenticator" method
  - Recovery email challenge
  - Post-login interstitial dismissal (passkey, recovery prompts)
  - Session verification at myaccount.google.com
  - HITL fallback: screenshots sent to operator when automation can't proceed

Credentials source (priority order):
  1. Direct function arguments
  2. Central API SecretManager (vault://google_email)
  3. Environment variables (GOOGLE_EMAIL, GOOGLE_PASSWORD, GOOGLE_TOTP)
"""

import os
import time
import logging
import base64
import io

logger = logging.getLogger("google_signin")

# Optional TOTP import
try:
    import pyotp
except ImportError:
    pyotp = None


def check_existing_session(driver) -> bool:
    """
    Navigate to myaccount.google.com and check if already signed in.

    Returns:
        True if a valid Google session exists, False otherwise.
    """
    try:
        driver.get("https://myaccount.google.com")
        time.sleep(4)
        page = driver.page_source.lower()

        # If we see personal info or security links, we're signed in
        if "personal info" in page or "security" in page:
            current_url = driver.current_url
            if "myaccount.google.com" in current_url:
                logger.info("✅ Existing Google session detected.")
                return True

        # If redirected to sign-in page, not signed in
        if "accounts.google.com" in driver.current_url:
            logger.info("ℹ️ No existing session — sign-in required.")
            return False

    except Exception as e:
        logger.warning(f"Session check failed: {e}")

    return False


def _take_screenshot(driver, label: str = "state") -> str:
    """Take a screenshot and return as base64 PNG string."""
    try:
        return driver.get_screenshot_as_base64()
    except Exception:
        return ""


def _save_screenshot(driver, path: str, label: str = ""):
    """Save a screenshot to disk."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        driver.save_screenshot(path)
        logger.info(f"📸 Screenshot saved: {path} ({label})")
    except Exception as e:
        logger.warning(f"Screenshot failed: {e}")


def _wait_for_element(driver, js_check: str, timeout: int = 10) -> bool:
    """Wait until a JS expression returns truthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = driver.execute_script(f"return !!({js_check})")
            if result:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _type_slowly(driver, selector_js: str, text: str, delay: float = 0.08):
    """Type text character by character into an element found by JS."""
    for char in text:
        driver.execute_script(f"""
            let el = {selector_js};
            if (el) {{
                el.focus();
                el.value += '{char}';
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
        """)
        time.sleep(delay)


def google_signin(
    driver,
    email: str,
    password: str,
    recovery_email: str = "",
    totp_secret: str = "",
    screenshot_dir: str = "/tmp/signin_screenshots",
    hitl_callback=None,
    max_retries: int = 3,
) -> bool:
    """
    Automate Google sign-in through the full flow.

    Args:
        driver: Selenium WebDriver instance (already started).
        email: Google account email.
        password: Account password.
        recovery_email: Recovery email for verification challenges.
        totp_secret: Base32 TOTP secret for Google Authenticator.
        screenshot_dir: Directory to save evidence screenshots.
        hitl_callback: Optional callable(screenshot_b64, message) for HITL.
                       If None, the function pauses and waits.
        max_retries: Number of retry attempts for the full flow.

    Returns:
        True if sign-in was successful, False otherwise.
    """
    os.makedirs(screenshot_dir, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        logger.info(f"🔑 Sign-in attempt {attempt}/{max_retries} for {email}")

        try:
            success = _do_signin(
                driver, email, password, recovery_email,
                totp_secret, screenshot_dir, hitl_callback
            )
            if success:
                logger.info(f"✅ Sign-in SUCCESS for {email}")
                return True
            else:
                logger.warning(f"⚠️ Sign-in attempt {attempt} failed for {email}")

        except Exception as e:
            logger.error(f"❌ Sign-in attempt {attempt} error: {e}")
            _save_screenshot(
                driver,
                os.path.join(screenshot_dir, f"error_attempt_{attempt}.png"),
                f"Error: {e}"
            )

        if attempt < max_retries:
            time.sleep(3)

    logger.error(f"❌ All {max_retries} sign-in attempts failed for {email}")
    return False


def _do_signin(
    driver, email, password, recovery_email,
    totp_secret, screenshot_dir, hitl_callback
) -> bool:
    """Execute a single sign-in attempt."""

    # ── Step 1: Navigate to Google sign-in ───────────────────
    logger.info("📍 Navigating to accounts.google.com...")
    driver.get("https://accounts.google.com/signin")
    time.sleep(3)
    _save_screenshot(driver, os.path.join(screenshot_dir, "01_signin_page.png"),
                     "Sign-in page loaded")

    # ── Step 2: Enter email ──────────────────────────────────
    logger.info(f"📧 Entering email: {email}")
    email_entered = driver.execute_script(f"""
        let inputs = document.querySelectorAll(
            'input[type="email"], input[name="identifier"], input#identifierId'
        );
        for (let inp of inputs) {{
            if (inp.offsetParent !== null) {{
                inp.focus();
                inp.value = '{email}';
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                return true;
            }}
        }}
        return false;
    """)

    if not email_entered:
        logger.error("Could not find email input field")
        return False

    time.sleep(1)

    # Click Next
    driver.execute_script("""
        let buttons = document.querySelectorAll('button, div[role="button"]');
        for (let btn of buttons) {
            let text = (btn.innerText || btn.textContent || '').toLowerCase();
            if (text.includes('next') || text.includes('continue')) {
                btn.click(); return true;
            }
        }
        // Fallback: submit via Enter
        let emailInput = document.querySelector('input[type="email"]');
        if (emailInput) {
            emailInput.dispatchEvent(new KeyboardEvent('keydown',
                {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
        }
        return false;
    """)
    time.sleep(3)
    _save_screenshot(driver, os.path.join(screenshot_dir, "02_after_email.png"),
                     "After email entry")

    # ── Step 3: Check for CAPTCHA ────────────────────────────
    page_source = driver.page_source.lower()
    if "recaptcha" in page_source or "captcha" in page_source:
        logger.warning("🛡️ CAPTCHA detected! Requesting human intervention...")
        _request_hitl(driver, hitl_callback, screenshot_dir,
                      "CAPTCHA detected during sign-in. Please solve it.")
        time.sleep(5)

    # ── Step 4: Enter password ───────────────────────────────
    logger.info("🔒 Entering password...")
    _wait_for_element(driver,
        "document.querySelector(\"input[type='password']\")", timeout=10)

    password_entered = driver.execute_script(f"""
        let pwInputs = document.querySelectorAll(
            "input[type='password'], input[name='Passwd']"
        );
        for (let inp of pwInputs) {{
            if (inp.offsetParent !== null) {{
                inp.focus();
                inp.value = '';
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                // Type char by char for realistic input
                let pw = '{password}';
                for (let c of pw) {{
                    inp.value += c;
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
                return true;
            }}
        }}
        return false;
    """)

    if not password_entered:
        logger.error("Could not find password input field")
        return False

    time.sleep(1)

    # Click Next after password
    driver.execute_script("""
        let buttons = document.querySelectorAll('button, div[role="button"]');
        for (let btn of buttons) {
            let text = (btn.innerText || btn.textContent || '').toLowerCase();
            if (text.includes('next') || text.includes('sign in')) {
                btn.click(); return true;
            }
        }
        return false;
    """)
    time.sleep(5)
    _save_screenshot(driver, os.path.join(screenshot_dir, "03_after_password.png"),
                     "After password entry")

    # ── Step 5: Handle 2FA challenges ────────────────────────
    page_source = driver.page_source.lower()
    current_url = driver.current_url.lower()

    # 5a. Check if we need to select 2FA method
    if "challenge" in current_url or "selectchallenge" in current_url:
        logger.info("🔐 2FA challenge page detected — selecting Google Authenticator...")
        _select_authenticator_method(driver)
        time.sleep(3)
        page_source = driver.page_source.lower()

    # 5b. TOTP (Google Authenticator)
    if ("authenticator" in page_source or "totp" in page_source or
            "verification code" in page_source or "6-digit" in page_source or
            "totppin" in current_url):
        if totp_secret and pyotp:
            logger.info("🔢 Generating TOTP code...")
            totp = pyotp.TOTP(totp_secret)
            code = totp.now()
            logger.info(f"🔢 TOTP code: {code}")

            code_entered = driver.execute_script(f"""
                let inputs = document.querySelectorAll(
                    'input[type="tel"], input[type="text"], input[name="totpPin"]'
                );
                for (let inp of inputs) {{
                    if (inp.offsetParent !== null) {{
                        inp.focus();
                        inp.value = '{code}';
                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return true;
                    }}
                }}
                return false;
            """)

            if code_entered:
                time.sleep(1)
                driver.execute_script("""
                    let buttons = document.querySelectorAll(
                        'button, div[role="button"]'
                    );
                    for (let btn of buttons) {
                        let text = (btn.innerText || '').toLowerCase();
                        if (text.includes('next') || text.includes('verify')) {
                            btn.click(); return true;
                        }
                    }
                    return false;
                """)
                time.sleep(5)
                _save_screenshot(driver,
                    os.path.join(screenshot_dir, "04_after_totp.png"),
                    "After TOTP entry")
            else:
                logger.warning("Could not find TOTP input field")
                _request_hitl(driver, hitl_callback, screenshot_dir,
                              "Could not find TOTP input. Please enter the code manually.")
        else:
            # No TOTP secret available — need human
            logger.warning("🛑 TOTP challenge but no secret available!")
            _request_hitl(driver, hitl_callback, screenshot_dir,
                          "TOTP 2FA required but no secret configured. "
                          "Please complete verification manually.")

    # 5c. Recovery email challenge
    elif "recovery" in page_source and "email" in page_source:
        if recovery_email:
            logger.info(f"📧 Entering recovery email: {recovery_email}")
            driver.execute_script(f"""
                let inputs = document.querySelectorAll(
                    'input[type="email"], input[type="text"]'
                );
                for (let inp of inputs) {{
                    if (inp.offsetParent !== null) {{
                        inp.focus();
                        inp.value = '{recovery_email}';
                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        break;
                    }}
                }}
            """)
            time.sleep(1)
            driver.execute_script("""
                let buttons = document.querySelectorAll(
                    'button, div[role="button"]'
                );
                for (let btn of buttons) {
                    let text = (btn.innerText || '').toLowerCase();
                    if (text.includes('next')) { btn.click(); return; }
                }
            """)
            time.sleep(5)
        else:
            _request_hitl(driver, hitl_callback, screenshot_dir,
                          "Recovery email challenge appeared but no recovery email configured.")

    # 5d. Unknown challenge — HITL fallback
    elif ("challenge" in current_url and
          "myaccount" not in current_url):
        logger.warning("🛑 Unknown 2FA challenge — requesting human intervention...")
        _request_hitl(driver, hitl_callback, screenshot_dir,
                      "Unknown 2FA challenge. Please complete verification "
                      "(e.g., approve device prompt, scan QR code).")

    # ── Step 6: Dismiss post-login interstitials ─────────────
    time.sleep(3)
    _dismiss_interstitials(driver)

    # ── Step 7: Verify sign-in success ───────────────────────
    _save_screenshot(driver, os.path.join(screenshot_dir, "05_final_state.png"),
                     "Final state after sign-in")
    return check_existing_session(driver)


def _select_authenticator_method(driver):
    """On the 2FA method selection page, click 'Google Authenticator'."""
    driver.execute_script("""
        let items = document.querySelectorAll(
            'li, div[role="link"], div[data-challengetype], button, a'
        );
        for (let item of items) {
            let text = (item.innerText || item.textContent || '').toLowerCase();
            if (text.includes('authenticator') || text.includes('google auth') ||
                text.includes('verification code') || text.includes('6-digit')) {
                item.click();
                return true;
            }
        }
        // Also check data attributes for TOTP challenge type
        let totpOptions = document.querySelectorAll(
            '[data-challengetype="6"], [data-challengeid="6"]'
        );
        if (totpOptions.length > 0) {
            totpOptions[0].click();
            return true;
        }
        return false;
    """)


def _dismiss_interstitials(driver):
    """Dismiss common post-login popups (passkey, recovery, etc.)."""
    for _ in range(3):
        try:
            dismissed = driver.execute_script("""
                let buttons = document.querySelectorAll(
                    'button, div[role="button"], a'
                );
                for (let btn of buttons) {
                    let text = (btn.innerText || btn.textContent || '')
                              .toLowerCase().trim();
                    if (text === 'not now' || text === 'skip' ||
                        text === 'no thanks' || text === 'dismiss' ||
                        text === 'maybe later' || text === 'done' ||
                        text === 'i agree' || text === 'accept') {
                        btn.click();
                        return true;
                    }
                }
                return false;
            """)
            if dismissed:
                logger.info("🔄 Dismissed post-login interstitial.")
                time.sleep(2)
            else:
                break
        except Exception:
            break


def _request_hitl(driver, hitl_callback, screenshot_dir, message):
    """
    Request human-in-the-loop intervention.

    For native browser: pauses execution.
    For Colab browser: takes screenshot, sends to operator, waits.
    """
    screenshot_b64 = _take_screenshot(driver, "hitl_request")
    screenshot_path = os.path.join(screenshot_dir, "hitl_request.png")
    _save_screenshot(driver, screenshot_path, message)

    if hitl_callback:
        logger.info(f"🛑 HITL: {message}")
        hitl_callback(screenshot_b64, message)
    else:
        logger.warning(f"🛑 HITL REQUIRED: {message}")
        logger.warning("⏸️ Pausing for 120 seconds for manual intervention...")
        logger.warning(f"   Screenshot saved to: {screenshot_path}")
        time.sleep(120)
