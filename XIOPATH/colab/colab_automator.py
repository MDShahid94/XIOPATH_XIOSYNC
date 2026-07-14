"""
Colab Automator — Drives Google Colab UI programmatically.

Ported from XIO_VERSE colab_automator.py (656 lines → ~450 lines).
OAuth popup handling extracted to oauth_handler.py.

Capabilities:
  - Open Colab notebooks by URL
  - Manage sessions (terminate stale ones)
  - Connect to hosted runtime
  - Inject + run code cells (clipboard paste method)
  - Monitor cell output with live streaming
  - Auto-diagnose and fix common errors
  - Handle Drive API auth modals
  - Handle OAuth popups in secondary windows
  - Wait for [COLAB_EXECUTION_COMPLETE] end marker
  - Disconnect + delete runtime on completion
"""

import os
import sys
import time
import json
import logging

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from .oauth_handler import handle_oauth_popups, handle_drive_auth_modal

logger = logging.getLogger("colab_automator")


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def execute_colab_command(driver, command_name: str) -> bool:
    """
    Open the Command Palette and execute a command by name.

    Args:
        driver: Selenium WebDriver instance.
        command_name: The command to search for and execute.

    Returns:
        True if the command was executed, False on error.
    """
    logger.info(f"🎹 Executing command: '{command_name}'")
    try:
        # Open Command Palette (Ctrl/Cmd + Shift + P)
        driver.execute_script("""
            document.body.focus();
            let event = new KeyboardEvent('keydown', {
                key: 'p', code: 'KeyP', keyCode: 80, which: 80,
                shiftKey: true,
                ctrlKey: !navigator.platform.toUpperCase().includes('MAC'),
                metaKey: navigator.platform.toUpperCase().includes('MAC'),
                bubbles: true, cancelable: true
            });
            document.body.dispatchEvent(event);
        """)
        time.sleep(1.5)

        # Fallback shortcut
        driver.execute_script("""
            if (!document.querySelector('colab-command-palette')) {
                let event2 = new KeyboardEvent('keydown', {
                    key: 'P', code: 'KeyP', keyCode: 80, which: 80,
                    shiftKey: true, ctrlKey: true,
                    bubbles: true, cancelable: true
                });
                document.body.dispatchEvent(event2);
            }
        """)
        time.sleep(1.0)

        # Type the command name and press Enter
        ActionChains(driver).send_keys(command_name).perform()
        time.sleep(1.0)
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(1.0)

        logger.info(f"  ✅ Done: '{command_name}'")
        return True

    except Exception as e:
        logger.error(f"  ❌ Failed '{command_name}': {e}")
        return False


def inject_code(driver, code_str: str) -> bool:
    """
    Inject multiline code into the focused Colab cell using
    clipboard write + Ctrl/Cmd+V paste.

    Args:
        driver: Selenium WebDriver instance.
        code_str: The Python code to inject.

    Returns:
        True if injection succeeded, False otherwise.
    """
    try:
        time.sleep(1)
        ctrl = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL

        # Clear existing cell content
        ActionChains(driver).key_down(ctrl).send_keys("a") \
            .key_up(ctrl).send_keys(Keys.BACKSPACE).perform()
        time.sleep(0.5)

        # Write to clipboard via JS (escape backticks/backslashes/dollars)
        escaped = code_str.replace('\\', '\\\\') \
                          .replace('`', '\\`') \
                          .replace('${', '\\${')
        driver.execute_script(f"navigator.clipboard.writeText(`{escaped}`);")
        time.sleep(0.8)

        # Paste
        ActionChains(driver).key_down(ctrl).send_keys("v") \
            .key_up(ctrl).perform()
        time.sleep(0.5)

        logger.info("  ✅ Code injected into cell.")
        return True

    except Exception as e:
        logger.error(f"  ❌ Code injection failed: {e}")
        return False


def wait_for_cell_idle(driver, timeout: int = 3600) -> bool:
    """
    Wait until cell execution completes by polling visible output
    for end markers or crash indicators.

    Args:
        driver: Selenium WebDriver instance.
        timeout: Max seconds to wait.

    Returns:
        True if cell completed (success or crash), False on timeout.
    """
    logger.info("⏳ Waiting for cell execution to finish...")
    start = time.time()
    last_output_len = 0

    while time.time() - start < timeout:
        try:
            # Handle Drive Auth modal
            handle_drive_auth_modal(driver)

            # Read visible output from DOM (traversing Shadow DOMs)
            visible_output = driver.execute_script("""
                function getOutputDeep(root) {
                    let t = "";
                    for (let el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) t += getOutputDeep(el.shadowRoot);
                        if (el.tagName === 'IFRAME') {
                            try {
                                if (el.contentDocument && el.contentDocument.body)
                                    t += el.contentDocument.body.innerText + '\\n';
                            } catch(e) {}
                        }
                        if (el.className && typeof el.className === 'string' &&
                            el.className.includes('output_area')) {
                            t += el.innerText + '\\n';
                        }
                        if (el.tagName && el.tagName.toLowerCase() ===
                            'colab-cell-output') {
                            t += el.innerText + '\\n';
                        }
                    }
                    return t;
                }

                let out = getOutputDeep(document);
                if (!out.trim()) {
                    // Fallback: entire page text
                    function getTextDeep(root) {
                        let t = "";
                        for (let el of root.querySelectorAll('*')) {
                            if (el.shadowRoot) t += getTextDeep(el.shadowRoot);
                            if (el.tagName === 'IFRAME') {
                                try {
                                    if (el.contentDocument && el.contentDocument.body)
                                        t += el.contentDocument.body.innerText + '\\n';
                                } catch(e) {}
                            }
                        }
                        return t + root.textContent;
                    }
                    out = getTextDeep(document);
                }
                return out;
            """)

            if visible_output:
                visible_output = visible_output.strip()

                # Print new output
                if len(visible_output) > last_output_len:
                    new_text = visible_output[last_output_len:]
                    print(f"\n[LIVE COLAB OUTPUT]:\n{new_text}\n", flush=True)
                    last_output_len = len(visible_output)

                out_lower = visible_output.lower()

                # Check for completion marker
                if "[colab_execution_complete]" in out_lower:
                    logger.info("  ✅ End marker found in output.")
                    return True

                # Check for crashes
                crash_markers = [
                    "syntaxerror:", "traceback (most recent",
                    "nameerror:", "failed to execute cell",
                    "an error occurred while executing"
                ]
                for marker in crash_markers:
                    if marker in out_lower:
                        logger.warning(f"  ❌ Crash detected: {marker}")
                        return True

        except Exception:
            pass

        time.sleep(5)

    logger.warning("  ⚠️ Timed out waiting for cell to finish.")
    return False


def copy_cell_output(driver) -> str:
    """
    Copy the last cell's output via Command Palette or DOM scraping.

    Returns:
        The cell output text.
    """
    execute_colab_command(driver, "Copy cell output")
    time.sleep(1.5)

    output = driver.execute_script("""
        return new Promise(resolve => {
            navigator.clipboard.readText()
                .then(t => resolve(t))
                .catch(() => {
                    // Fallback: read visible output from DOM
                    let outputs = document.querySelectorAll('.output_area');
                    let text = '';
                    outputs.forEach(o => { text += o.innerText + '\\n'; });
                    resolve(text || 'OUTPUT_NOT_FOUND');
                });
        });
    """)
    return (output or "").strip()


def _auto_diagnose_error(cell_output: str) -> str | None:
    """
    Attempt to auto-diagnose common Colab errors and return fix code.

    Returns:
        Fix code string, or None if unable to diagnose.
    """
    out_lower = cell_output.lower()

    if "no module named" in out_lower:
        # Extract missing module name
        missing = ""
        for line in cell_output.split('\n'):
            if "no module named" in line.lower():
                parts = line.split("'")
                if len(parts) >= 2:
                    missing = parts[-2]
        if missing:
            logger.info(f"  🔧 Auto-fix: pip install {missing}")
            return (f"import subprocess; "
                    f"subprocess.run(['pip', 'install', '{missing}'], check=True)")

    elif "modulenotfounderror" in out_lower and "src" in out_lower:
        logger.info("  🔧 Auto-fix: adding project to sys.path")
        return (
            "import sys, os\n"
            "sys.path.insert(0, '/content/antigravity')\n"
            "print('✅ Fixed sys.path.', flush=True)\n"
        )

    elif ("cannot connect to chrome" in out_lower or
          "session not created" in out_lower):
        logger.info("  🔧 Auto-fix: Starting Xvfb + Chrome")
        return (
            "import subprocess, os\n"
            "subprocess.run('apt-get install -y xvfb google-chrome-stable "
            "> /dev/null 2>&1', shell=True)\n"
            "subprocess.run('Xvfb :99 -screen 0 1920x1080x24 &', shell=True)\n"
            "os.environ['DISPLAY'] = ':99'\n"
            "print('✅ Xvfb started. DISPLAY set to :99', flush=True)\n"
        )

    elif ("no such file or directory" in out_lower and
          "profile" in out_lower):
        logger.info("  🔧 Auto-fix: Creating missing profile directory")
        return (
            "import os\n"
            "os.makedirs('/content/antigravity/profiles', exist_ok=True)\n"
            "print('✅ Profile directory created.', flush=True)\n"
        )

    return None


# ═══════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════

def run_colab_notebook(
    driver,
    colab_url: str,
    bootstrap_code: str,
    max_rounds: int = 8,
    cell_timeout: int = 3600,
) -> bool:
    """
    Full Colab notebook lifecycle: open → manage sessions → connect runtime →
    inject code → run → monitor → handle errors → cleanup.

    Args:
        driver: Selenium WebDriver instance.
        colab_url: URL of the Colab notebook to open.
        bootstrap_code: Python code to inject and run.
        max_rounds: Max error-fix-retry rounds.
        cell_timeout: Max seconds to wait per cell execution.

    Returns:
        True if the notebook ran successfully, False otherwise.
    """
    logger.info(f"🚀 Opening Colab: {colab_url}")

    # ── Open notebook ────────────────────────────────────────
    try:
        driver.set_page_load_timeout(15)
        driver.get(colab_url)
    except Exception:
        pass  # Timeout is expected for Colab's heavy page
    finally:
        driver.set_page_load_timeout(60)

    logger.info("⏳ Waiting for UI to load (10s)...")
    time.sleep(10)

    # ── Manage Sessions ──────────────────────────────────────
    logger.info("🔍 Managing active sessions...")
    execute_colab_command(driver, "Manage sessions")
    time.sleep(3)

    sessions_text = driver.execute_script("""
        function getTextDeep(root) {
            let t = "";
            for (let el of root.querySelectorAll('*')) {
                if (el.shadowRoot) t += getTextDeep(el.shadowRoot);
            }
            return t + root.textContent;
        }
        return getTextDeep(document);
    """) or ""

    if "no active sessions" in sessions_text.lower():
        logger.info("  ✅ No active sessions.")
    else:
        logger.info("  ⚠️ Active sessions found — terminating...")
        driver.execute_script("""
            function findAndClick(root, match) {
                for (let el of root.querySelectorAll('*')) {
                    if (el.shadowRoot && findAndClick(el.shadowRoot, match))
                        return true;
                    let text = ((el.textContent || '') + ' ' +
                               (el.getAttribute('label') || '') + ' ' +
                               (el.title || '')).toLowerCase();
                    let clickable = el.tagName.includes('BUTTON') ||
                                    el.getAttribute('role') === 'button' ||
                                    el.tagName === 'A';
                    if (clickable && text.includes(match)) {
                        el.click(); return true;
                    }
                }
                return false;
            }
            if (!findAndClick(document, 'terminate other sessions')) {
                // Click individual delete icons
                function clickDeletes(root) {
                    for (let el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) clickDeletes(el.shadowRoot);
                        let t = ((el.title || '') + ' ' +
                                 (el.getAttribute('aria-label') || ''))
                                .toLowerCase();
                        if ((el.tagName.includes('BUTTON') ||
                             el.getAttribute('role') === 'button') &&
                            (t.includes('delete') || t.includes('terminate'))) {
                            try { el.click(); } catch(e) {}
                        }
                    }
                }
                clickDeletes(document);
            }
        """)
        time.sleep(3)

    # Close dialog
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    time.sleep(1)

    # ── Connect to Runtime ───────────────────────────────────
    logger.info("⚡ Connecting to a hosted runtime...")
    execute_colab_command(driver, "Connect to a hosted runtime")
    logger.info("⏳ Waiting 20s for runtime allocation...")
    time.sleep(20)

    # ── Interactive Loop ─────────────────────────────────────
    code_to_run = bootstrap_code
    main_window = driver.current_window_handle
    success = False

    for round_num in range(1, max_rounds + 1):
        logger.info(f"\n{'=' * 60}")
        logger.info(f"🔄 Round {round_num}/{max_rounds}")

        if not code_to_run:
            logger.info("  ℹ️ No more code to inject. Stopping loop.")
            break

        # Insert a new code cell below
        logger.info(f"  💉 Injecting code for round {round_num}...")
        execute_colab_command(driver, "Insert code cell below")
        time.sleep(1.5)
        inject_code(driver, code_to_run)
        time.sleep(0.5)

        # Run the cell
        logger.info("  ▶️ Running cell...")
        execute_colab_command(driver, "Run focused cell")
        time.sleep(3)

        # Wait for execution with OAuth popup monitoring
        logger.info("  ⏳ Waiting for execution...")
        start_wait = time.time()
        cell_finished = False

        while time.time() - start_wait < cell_timeout:
            # Handle OAuth popups in secondary windows
            handle_oauth_popups(driver, main_window)

            # Switch back to main and check cell status
            try:
                driver.switch_to.window(main_window)
            except Exception:
                pass

            try:
                if wait_for_cell_idle(driver, timeout=5):
                    cell_finished = True
                    break
            except Exception:
                break

        if not cell_finished:
            logger.warning("  ⚠️ Execution wait timed out.")

        # Read output
        logger.info("  📋 Reading cell output...")
        cell_output = copy_cell_output(driver)
        logger.info(f"\n  📄 Cell Output (Round {round_num}):\n{'-' * 40}")
        print(cell_output, flush=True)
        print('-' * 40, flush=True)

        # ── Analyze output ───────────────────────────────────
        output_lower = (cell_output or "").lower()

        # Success markers
        if ("drive upload complete" in output_lower or
                "test complete. profile saved." in output_lower or
                "[colab_execution_complete]" in output_lower):
            logger.info("\n  🎉 SUCCESS: Worker bootstrap complete!")
            success = True
            break

        if "session already active and authorized" in output_lower:
            logger.info("\n  🎉 SUCCESS: Session already active!")
            success = True
            break

        # Error handling
        if ("error" in output_lower or "traceback" in output_lower or
                "failed" in output_lower):
            logger.warning(f"\n  ❌ Error detected in round {round_num}.")
            fix_code = _auto_diagnose_error(cell_output)

            if fix_code:
                code_to_run = fix_code
                logger.info(f"  🔄 Will inject fix in round {round_num + 1}...")
                continue
            else:
                logger.warning("  ⚠️ Could not auto-diagnose error.")
                break

        # No errors, first round complete
        logger.info(f"  ✅ Round {round_num} complete. No critical errors.")
        success = True
        break

    # ── Cleanup ──────────────────────────────────────────────
    logger.info("\n🛑 Disconnecting and deleting runtime...")
    execute_colab_command(driver, "Disconnect and delete runtime")
    time.sleep(2)

    # Click Yes on confirmation modal
    driver.execute_script("""
        function findAndClick(root, match) {
            for (let el of root.querySelectorAll('*')) {
                if (el.shadowRoot && findAndClick(el.shadowRoot, match))
                    return true;
                let text = (el.innerText || el.textContent || '')
                          .toLowerCase().trim();
                let clickable = el.tagName.includes('BUTTON') ||
                                el.getAttribute('role') === 'button' ||
                                el.tagName.includes('PAPER-BUTTON');
                if (clickable && text === match) {
                    el.click(); return true;
                }
            }
            return false;
        }
        findAndClick(document, 'yes');
    """)
    logger.info("  ✅ Runtime deleted.")
    time.sleep(2)

    logger.info("\n✅ Colab automation loop complete.")
    return success
