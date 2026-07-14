"""
OAuth Popup Handler — Auto-clicks through OAuth consent flows.

Extracted from XIO_VERSE colab_automator.py (L443-L476) to be reusable
across google_signin.py and colab_automator.py.

Handles:
  - Checkbox selection (input[type=checkbox], role=checkbox)
  - "Select All" / "Continue" / "Allow" button clicks
  - Account selector (div[data-identifier])
  - Fix for infinite "Select All" loop (from fix_automator.py)
"""

import time
import logging

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger("oauth_handler")


def handle_oauth_popups(driver, main_window: str, timeout: int = 5) -> bool:
    """
    Monitor all secondary browser windows for OAuth consent flows
    and auto-click through them.

    Args:
        driver: Selenium WebDriver instance.
        main_window: Handle of the main (Colab/primary) window.
        timeout: Max seconds to spend per iteration.

    Returns:
        True if any OAuth action was taken, False otherwise.
    """
    any_action = False

    try:
        handles = driver.window_handles
    except Exception:
        return False

    for handle in handles:
        if handle == main_window:
            continue

        try:
            driver.switch_to.window(handle)
            url = driver.current_url

            # Skip Colab's internal Gemini panel
            if "gemini.google.com" in url:
                continue

            clicked = driver.execute_script("""
                let actionTaken = false;

                // 1. Click explicit checkboxes
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    if (!cb.checked) { cb.click(); actionTaken = true; }
                });
                document.querySelectorAll('[role="checkbox"]').forEach(cb => {
                    if (cb.getAttribute('aria-checked') === 'false') {
                        cb.click(); actionTaken = true;
                    }
                });

                // 2. Click "Select all", "Continue", "Allow"
                let els = document.querySelectorAll(
                    'button, [role="button"], a, div, span'
                );
                for (let el of els) {
                    let text = (el.innerText || el.textContent ||
                               el.getAttribute('aria-label') || '')
                              .toLowerCase().trim();

                    if (text === 'continue' || text === 'allow' ||
                        text === 'select all') {
                        let isClickable = (
                            el.tagName === 'BUTTON' ||
                            el.tagName === 'A' ||
                            el.getAttribute('role') === 'button'
                        );

                        // Fix: prevent infinite "Select all" loop
                        if (text === 'select all' &&
                            el.getAttribute('aria-checked') === 'true') {
                            continue;
                        }

                        if (!isClickable && el.parentElement &&
                            (el.parentElement.tagName === 'BUTTON' ||
                             el.parentElement.getAttribute('role') === 'button')) {
                            el.parentElement.click();
                            actionTaken = true;
                            break;
                        } else if (isClickable || text === 'select all') {
                            el.click();
                            actionTaken = true;
                            break;
                        }
                    }
                }

                // 3. Account selection (if on chooser screen)
                let listItems = document.querySelectorAll(
                    'div[data-identifier]'
                );
                if (listItems.length > 0) {
                    listItems[0].click();
                    actionTaken = true;
                }

                return actionTaken;
            """)

            if clicked:
                logger.info("✅ Clicked OAuth element in popup window.")
                any_action = True
                time.sleep(2)

        except Exception as e:
            logger.debug(f"OAuth popup check failed for window: {e}")

    # Switch back to main window
    try:
        driver.switch_to.window(main_window)
    except Exception:
        pass

    return any_action


def handle_drive_auth_modal(driver) -> bool:
    """
    Handle the Google Drive API access modal that appears inside Colab
    when a cell tries to access Drive. Clicks "Allow" if found.

    Args:
        driver: Selenium WebDriver instance.

    Returns:
        True if the modal was found and clicked, False otherwise.
    """
    try:
        clicked = driver.execute_script("""
            function findAndClick(root) {
                for (let el of root.querySelectorAll('*')) {
                    if (el.shadowRoot && findAndClick(el.shadowRoot))
                        return true;
                    let text = (
                        (el.innerText || '') + ' ' +
                        (el.textContent || '') + ' ' +
                        (el.getAttribute('label') || '') + ' ' +
                        (el.getAttribute('aria-label') || '')
                    ).toLowerCase();
                    let clickable = (
                        el.tagName.includes('BUTTON') ||
                        el.getAttribute('role') === 'button'
                    );
                    if (clickable && text.includes('allow')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
            return findAndClick(document);
        """)

        if clicked:
            logger.info("⚠️ Detected and clicked 'Allow' for Drive API modal.")
            time.sleep(2)
            return True

    except Exception:
        pass

    return False
