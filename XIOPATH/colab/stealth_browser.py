"""
Stealth Browser Engine for Colab Worker Bots
=============================================
Merges the 5-Vector Antibot Stealth Stack with XIO_VERSE's BrowserEngine lifecycle.

Capabilities:
    - Undetected Chromedriver (bypasses webdriver detection)
    - Tailscale SOCKS5 proxy routing (residential IP)
    - Dynamic fingerprint morphing based on exit node OS/arch
    - Deep JS injection (WebGL, Workers, Battery, Camera, Memory spoofing)
    - Xvfb virtual display (avoids --headless flag detection)
    - Service Worker cache purging between sessions
    - CDP timezone + user-agent metadata overrides
    - pyautogui physical mouse events (Cloudflare Turnstile bypass)
"""

import sys
import json
import time
import shutil
import logging
import subprocess
from typing import Dict, Optional

logger = logging.getLogger("StealthBrowser")


class StealthBrowser:
    """
    A fully stealth-configured Chrome browser for Colab environments.

    Uses undetected_chromedriver + Tailscale SOCKS5 proxy + deep JS injection
    to appear as a genuine residential user browsing from the exit node device.
    """

    def __init__(
        self,
        exit_node_ip: str,
        socks_port: int = 1055,
        profile_path: Optional[str] = None,
        display_size: tuple = (1920, 1080),
    ):
        self.exit_node_ip = exit_node_ip
        self.socks_port = socks_port
        self.profile_path = profile_path
        self.display_size = display_size
        self.driver = None
        self.sys_info = None
        self._display_started = False

    # ================================================================
    # 1. TAILSCALE SOCKS5 MANAGEMENT
    # ================================================================

    @staticmethod
    def ensure_tailscale_running():
        """Self-healing Tailscale daemon check and restart."""
        try:
            subprocess.check_output(
                ["tailscale", "status"], stderr=subprocess.STDOUT
            )
            logger.info("Tailscale daemon is running.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Tailscale daemon offline. Rebooting...")
            subprocess.run(["sudo", "pkill", "-9", "tailscaled"], capture_output=True)
            subprocess.run(["sudo", "rm", "-f", "/var/run/tailscale/tailscaled.sock"], capture_output=True)
            subprocess.Popen(
                ["sudo", "tailscaled", "--tun=userspace-networking",
                 "--socks5-server=localhost:1055"],
                stdout=open("tailscaled.log", "w"),
                stderr=subprocess.STDOUT
            )
            time.sleep(4)

    def set_exit_node(self):
        """Lock Tailscale routing to the specified exit node."""
        self.ensure_tailscale_running()
        logger.info(f"Locking Tailscale to exit node: {self.exit_node_ip}")
        subprocess.run(
            ["sudo", "tailscale", "set", f"--exit-node={self.exit_node_ip}"],
            capture_output=True
        )
        time.sleep(3)

    def verify_socks5(self) -> Dict:
        """Verify SOCKS5 proxy connectivity and fetch geolocation."""
        import socks
        import requests as req

        max_retries = 5
        for attempt in range(max_retries):
            try:
                test_socket = socks.socksocket()
                test_socket.set_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
                test_socket.settimeout(6)
                test_socket.connect(("1.1.1.1", 80))
                test_socket.close()

                proxies = {
                    "http": f"socks5h://127.0.0.1:{self.socks_port}",
                    "https": f"socks5h://127.0.0.1:{self.socks_port}",
                }
                geo_data = req.get(
                    "http://ip-api.com/json/", proxies=proxies, timeout=10
                ).json()

                logger.info(
                    f"SOCKS5 healthy! Exit: {geo_data.get('city')}, "
                    f"{geo_data.get('country')} (TZ: {geo_data.get('timezone')})"
                )
                return geo_data

            except Exception as e:
                logger.warning(
                    f"SOCKS5 unreachable (attempt {attempt + 1}/{max_retries}). "
                    f"Wake up exit node ({self.exit_node_ip}). Retrying in 10s..."
                )
                time.sleep(10)

        raise ConnectionError(
            f"SOCKS5 proxy at 127.0.0.1:{self.socks_port} unreachable after {max_retries} retries."
        )

    # ================================================================
    # 2. DYNAMIC FINGERPRINT PROFILING
    # ================================================================

    def get_dynamic_profile(self) -> Dict:
        """
        Query Tailscale API to detect exit node OS/arch,
        then morph the entire browser fingerprint to match.
        """
        # Get Chrome version
        try:
            cv_str = (
                subprocess.check_output(["google-chrome", "--version"])
                .decode("utf-8")
                .strip()
                .split()[2]
            )
        except Exception:
            cv_str = "137.0.0.0"
        major_v = cv_str.split(".")[0]

        # Query Tailscale for exit node info
        os_type, arch_type = "linux", "amd64"
        try:
            status_json = subprocess.check_output(
                ["tailscale", "status", "--json"]
            ).decode("utf-8")
            status_data = json.loads(status_json)
            peers = status_data.get("Peer", {})
            target_peer = next(
                (p for p in peers.values() if self.exit_node_ip in p.get("TailscaleIPs", [])),
                None,
            )
            if target_peer:
                os_type = (target_peer.get("OS", "") or "").lower()
                arch_type = (target_peer.get("GoArch", "") or "").lower()
                if not os_type and "Hostinfo" in target_peer:
                    os_type = target_peer["Hostinfo"].get("OS", "").lower()
                if not arch_type and "Hostinfo" in target_peer:
                    arch_type = target_peer["Hostinfo"].get("GoArch", "").lower()

            logger.info(f"Exit Node detected: OS='{os_type.upper()}' ARCH='{arch_type.upper()}'")
        except Exception as e:
            logger.warning(f"Tailscale query failed ({e}). Defaulting to Linux x86_64.")

        # Base profile (Linux Desktop)
        profile = {
            "width": self.display_size[0],
            "height": self.display_size[1],
            "is_mobile": False,
            "cv_full": cv_str,
            "cv_major": major_v,
            "cores": 8,
            "ram": 16,
            "battery_charging": "true",
            "battery_level": "1.0",
            "cam_name": "HD Web Camera",
            "platform": "Linux x86_64",
            "ch_platform": "Linux",
            "ch_arch": "x86",
            "ch_version": "5.15.0",
            "user_agent": f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv_str} Safari/537.36",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "timezone": "UTC",
        }

        # Mac Silicon
        if "mac" in os_type and "arm" in arch_type:
            profile.update({
                "platform": "MacIntel",
                "ch_platform": "macOS",
                "ch_arch": "arm",
                "ch_version": "10.15.7",
                "cores": 8,
                "ram": 8,
                "cam_name": "FaceTime HD Camera",
                "user_agent": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv_str} Safari/537.36",
                "webgl_vendor": "Apple Inc.",
                "webgl_renderer": "Apple M1",
            })
        # Mac Intel
        elif "mac" in os_type:
            profile.update({
                "platform": "MacIntel",
                "ch_platform": "macOS",
                "ch_arch": "x86",
                "ch_version": "10.15.7",
                "cores": 8,
                "ram": 16,
                "cam_name": "FaceTime HD Camera",
                "user_agent": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv_str} Safari/537.36",
                "webgl_vendor": "Apple Inc.",
                "webgl_renderer": "Intel(R) Iris(TM) Plus Graphics 640",
            })
        # Windows
        elif "win" in os_type:
            profile.update({
                "platform": "Win32",
                "ch_platform": "Windows",
                "ch_arch": "x86",
                "ch_version": "10.0.0",
                "cores": 16,
                "ram": 16,
                "cam_name": "Integrated Camera",
                "user_agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv_str} Safari/537.36",
                "webgl_vendor": "Google Inc. (NVIDIA)",
                "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            })
        # Android / iOS (Mobile)
        elif "android" in os_type or "ios" in os_type:
            logger.info("Morphing into Mobile Smartphone profile...")
            profile.update({
                "width": 360,
                "height": 800,
                "is_mobile": True,
                "cores": 8,
                "ram": 8,
                "battery_charging": "false",
                "battery_level": "0.85",
                "cam_name": "Front Camera",
                "platform": "Linux armv8l",
                "ch_platform": "Android",
                "ch_arch": "arm",
                "ch_version": "13.0.0",
                "user_agent": f"Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv_str} Mobile Safari/537.36",
                "webgl_vendor": "Qualcomm",
                "webgl_renderer": "Adreno (TM) 730",
            })

        return profile

    # ================================================================
    # 3. STEALTH JS INJECTION PAYLOAD
    # ================================================================

    @staticmethod
    def build_stealth_js(sys_info: Dict) -> str:
        """
        Build the comprehensive JavaScript injection payload that spoofs:
        - WebGL vendor/renderer (main window + Workers + OffscreenCanvas)
        - navigator.hardwareConcurrency, deviceMemory, platform
        - Battery API, Camera/Mic enumeration
        - Worker/SharedWorker constructor interception
        - UserAgentData (Sec-CH-UA) high-entropy values
        """
        mobile_str = "true" if sys_info["is_mobile"] else "false"

        return f"""
    (function() {{
        const makeNative = (fn, name) => {{
            Object.defineProperty(fn, 'name', {{ value: name, configurable: true }});
            const str = "function " + name + "() {{ [native code] }}";
            fn.toString = () => str;
            fn.toString.toString = () => "function toString() {{ [native code] }}";
        }};

        // WebGL Spoofing (Main Window)
        ['WebGLRenderingContext', 'WebGL2RenderingContext'].forEach(function(ctx) {{
            if (window[ctx]) {{
                const orig = window[ctx].prototype.getParameter;
                const spoofed = function(parameter) {{
                    const result = orig.apply(this, arguments);
                    if (parameter === 37445) return '{sys_info["webgl_vendor"]}';
                    if (parameter === 37446) return '{sys_info["webgl_renderer"]}';
                    return result;
                }};
                Object.defineProperty(window[ctx].prototype, 'getParameter', {{
                    value: spoofed, writable: true, configurable: true, enumerable: false
                }});
                makeNative(spoofed, 'getParameter');
            }}
        }});

        // Hardware Sensors (Camera, Mic, Battery)
        if (navigator.mediaDevices) {{
            const mockDevices = [
                {{ kind: 'videoinput', deviceId: 'cam-1', label: '{sys_info["cam_name"]}', groupId: 'g1' }},
                {{ kind: 'audioinput', deviceId: 'mic-1', label: 'Internal Microphone', groupId: 'g2' }},
                {{ kind: 'audiooutput', deviceId: 'spk-1', label: 'Internal Speaker', groupId: 'g2' }}
            ];
            if ({mobile_str}) {{
                mockDevices.push({{ kind: 'videoinput', deviceId: 'cam-2', label: 'Back Camera', groupId: 'g1' }});
            }}
            navigator.mediaDevices.enumerateDevices = () => Promise.resolve(mockDevices);
            makeNative(navigator.mediaDevices.enumerateDevices, 'enumerateDevices');
        }}

        if (navigator.getBattery) {{
            const mockBattery = {{
                charging: {sys_info["battery_charging"]}, chargingTime: 0,
                dischargingTime: Infinity, level: {sys_info["battery_level"]},
                addEventListener: () => {{}}, removeEventListener: () => {{}}, dispatchEvent: () => {{}}
            }};
            navigator.getBattery = () => Promise.resolve(mockBattery);
            makeNative(navigator.getBattery, 'getBattery');
        }}

        // CPU + Memory on prototype
        Object.defineProperty(Navigator.prototype, 'deviceMemory', {{
            get: () => {sys_info["ram"]}, configurable: true, enumerable: true
        }});
        Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
            get: () => {sys_info["cores"]}, configurable: true, enumerable: true
        }});

        // Worker URL resolver
        const resolveURL = (url) => {{
            try {{ return new URL(url, window.location.href).href; }}
            catch (e) {{ return url; }}
        }};

        // Shared Worker injection payload
        const workerPayload = `
            if (self.WorkerNavigator) {{
                const proto = self.WorkerNavigator.prototype;
                Object.defineProperty(proto, 'userAgent', {{ get: () => '{sys_info["user_agent"]}', configurable: true }});
                Object.defineProperty(proto, 'platform', {{ get: () => '{sys_info["platform"]}', configurable: true }});
                Object.defineProperty(proto, 'hardwareConcurrency', {{ get: () => {sys_info["cores"]}, configurable: true }});
                Object.defineProperty(proto, 'deviceMemory', {{ get: () => {sys_info["ram"]}, configurable: true }});

                Object.defineProperty(proto, 'userAgentData', {{
                    get: () => ({{
                        brands: [
                            {{ brand: 'Chromium', version: '{sys_info["cv_major"]}' }},
                            {{ brand: 'Google Chrome', version: '{sys_info["cv_major"]}' }}
                        ],
                        mobile: {mobile_str},
                        platform: '{sys_info["ch_platform"]}',
                        getHighEntropyValues: async () => ({{
                            architecture: '{sys_info["ch_arch"]}',
                            bitness: '64',
                            model: '{"SM-S901B" if sys_info["is_mobile"] else ""}',
                            platform: '{sys_info["ch_platform"]}',
                            platformVersion: '{sys_info["ch_version"]}'
                        }})
                    }}),
                    configurable: true
                }});
            }}

            ['WebGLRenderingContext', 'WebGL2RenderingContext'].forEach(function(ctxName) {{
                if (self[ctxName]) {{
                    const origGetParam = self[ctxName].prototype.getParameter;
                    self[ctxName].prototype.getParameter = function(param) {{
                        const res = origGetParam.apply(this, arguments);
                        if (param === 37445) return '{sys_info["webgl_vendor"]}';
                        if (param === 37446) return '{sys_info["webgl_renderer"]}';
                        return res;
                    }};
                }}
            }});

            if (self.OffscreenCanvas) {{
                const origGetContext = self.OffscreenCanvas.prototype.getContext;
                self.OffscreenCanvas.prototype.getContext = function(type, attributes) {{
                    const ctx = origGetContext.apply(this, arguments);
                    if (ctx && (type === 'webgl' || type === 'webgl2')) {{
                        const origGetParam = ctx.getParameter;
                        ctx.getParameter = function(param) {{
                            const res = origGetParam.apply(this, arguments);
                            if (param === 37445) return '{sys_info["webgl_vendor"]}';
                            if (param === 37446) return '{sys_info["webgl_renderer"]}';
                            return res;
                        }};
                    }}
                    return ctx;
                }};
            }}
        `;

        // Intercept dedicated Workers
        const OriginalWorker = window.Worker;
        window.Worker = function(scriptURL, options) {{
            const resolved = resolveURL(scriptURL);
            const originUrl = window.location.href;
            const originHost = window.location.host;
            const originHostname = window.location.hostname;
            const locPayload = "Object.defineProperty(self, 'location', {{ get: () => ({{ href: '" + originUrl + "', protocol: 'https:', host: '" + originHost + "', hostname: '" + originHostname + "', pathname: '/', search: '', hash: '' }}), configurable: true }});";
            const rawScript = locPayload + "\\n" + workerPayload + "\\nimportScripts('" + resolved + "');";
            const blob = new Blob([rawScript], {{ type: 'application/javascript' }});
            return new OriginalWorker(URL.createObjectURL(blob), options);
        }};
        makeNative(window.Worker, 'Worker');

        // Intercept SharedWorkers
        const OriginalSharedWorker = window.SharedWorker;
        window.SharedWorker = function(scriptURL, options) {{
            const resolved = resolveURL(scriptURL);
            const originUrl = window.location.href;
            const originHost = window.location.host;
            const originHostname = window.location.hostname;
            const locPayload = "Object.defineProperty(self, 'location', {{ get: () => ({{ href: '" + originUrl + "', protocol: 'https:', host: '" + originHost + "', hostname: '" + originHostname + "', pathname: '/', search: '', hash: '' }}), configurable: true }});";
            const rawScript = locPayload + "\\n" + workerPayload + "\\nimportScripts('" + resolved + "');";
            const blob = new Blob([rawScript], {{ type: 'application/javascript' }});
            return new OriginalSharedWorker(URL.createObjectURL(blob), options);
        }};
        makeNative(window.SharedWorker, 'SharedWorker');
    }})();
    """

    # ================================================================
    # 4. DISPLAY + CACHE MANAGEMENT
    # ================================================================

    def start_virtual_display(self):
        """Start Xvfb virtual display for non-headless rendering."""
        w, h = self.display_size
        logger.info(f"Starting Xvfb virtual display ({w}x{h})...")
        subprocess.run(["pkill", "-9", "-f", "Xvfb"], capture_output=True)
        subprocess.run(["rm", "-f", "/tmp/.X99-lock"], capture_output=True)
        subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", f"{w}x{h}x24"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        os.environ["DISPLAY"] = ":99"
        time.sleep(2)
        self._display_started = True

    @staticmethod
    def purge_cached_workers(profile_dir: str):
        """Remove Service Worker + Cache directories to prevent fingerprint leaks."""
        targets = ["Service Worker", "Cache", "Code Cache"]
        for target in targets:
            path = os.path.join(profile_dir, "Default", target)
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                except Exception:
                    pass

    @staticmethod
    def cleanup_zombie_chrome(profile_path: str):
        """Kill Chrome instances using the same profile to avoid locking."""
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline", [])
                    if (
                        cmdline
                        and profile_path
                        and any(profile_path in cmd for cmd in cmdline)
                        and "chrome" in proc.info.get("name", "").lower()
                    ):
                        proc.kill()
                except Exception:
                    pass
        except ImportError:
            pass

        # Clean lock files
        for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = os.path.join(profile_path, lock_file)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

    # ================================================================
    # 5. BROWSER LAUNCH
    # ================================================================

    def launch(self) -> "uc.Chrome":
        """
        Full stealth launch sequence:
        1. Build dynamic fingerprint profile
        2. Verify SOCKS5 connectivity + fetch geolocation
        3. Start Xvfb virtual display
        4. Configure UC Chrome with stealth options
        5. Apply CDP overrides + JS injection
        """
        import undetected_chromedriver as uc

        # 1. Dynamic profile
        self.sys_info = self.get_dynamic_profile()

        # 2. SOCKS5 verification + timezone sync
        geo_data = self.verify_socks5()
        self.sys_info["timezone"] = geo_data.get("timezone", "UTC")

        # 3. Virtual display
        self.start_virtual_display()

        # 4. Clean profile caches
        if self.profile_path:
            self.cleanup_zombie_chrome(self.profile_path)
            self.purge_cached_workers(self.profile_path)

        # 5. Prevent Xauth errors
        xauth_path = os.path.expanduser("~/.Xauthority")
        if not os.path.exists(xauth_path):
            try:
                with open(xauth_path, "wb") as f:
                    f.write(b"")
            except Exception:
                pass

        # 6. Configure Chrome options
        options = uc.ChromeOptions()
        options.add_argument(f"--proxy-server=socks5://127.0.0.1:{self.socks_port}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # SwiftShader software rendering (fixes missing WebGL in headless env)
        options.add_argument("--use-gl=angle")
        options.add_argument("--use-angle=swiftshader")
        options.add_argument("--disable-gpu-sandbox")
        options.add_argument("--ignore-gpu-blocklist")

        # Prevent Service Worker + UDP leaks
        options.add_argument("--disable-service-workers")
        options.add_argument("--disable-features=ServiceWorker,UserAgentClientHint")
        options.add_experimental_option("prefs", {
            "webrtc.ip_handling_policy": "disable_non_proxied_udp",
            "webrtc.multiple_routes_enabled": False,
            "webrtc.nonproxied_udp_enabled": False,
        })

        w, h = self.sys_info["width"], self.sys_info["height"]
        options.add_argument(f"--window-size={w},{h}")
        options.add_argument("--window-position=0,0")
        options.add_argument(f"--user-agent={self.sys_info['user_agent']}")

        if self.profile_path:
            options.add_argument(f"--user-data-dir={self.profile_path}")

        # 7. Launch
        logger.info("Launching Stealth Chrome...")
        self.driver = uc.Chrome(
            options=options,
            headless=False,  # Using Xvfb, not --headless flag
            version_main=int(self.sys_info["cv_major"]),
        )

        # 8. Apply CDP overrides
        ua_metadata = {
            "brands": [
                {"brand": "Chromium", "version": self.sys_info["cv_major"]},
                {"brand": "Google Chrome", "version": self.sys_info["cv_major"]},
                {"brand": "Not-A.Brand", "version": "99"},
            ],
            "fullVersionList": [
                {"brand": "Chromium", "version": self.sys_info["cv_full"]},
                {"brand": "Google Chrome", "version": self.sys_info["cv_full"]},
                {"brand": "Not-A.Brand", "version": "99.0.0.0"},
            ],
            "platform": self.sys_info.get("ch_platform", "Linux"),
            "platformVersion": self.sys_info.get("ch_version", "5.15.0"),
            "architecture": self.sys_info.get("ch_arch", "x86"),
            "model": "SM-S901B" if self.sys_info["is_mobile"] else "",
            "mobile": self.sys_info["is_mobile"],
            "bitness": "64",
            "wow64": False,
        }

        self.driver.execute_cdp_cmd(
            "Emulation.setTimezoneOverride",
            {"timezoneId": self.sys_info["timezone"]},
        )
        self.driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": self.sys_info["user_agent"],
                "platform": self.sys_info["platform"],
                "acceptLanguage": "en-US,en",
                "userAgentMetadata": ua_metadata,
            },
        )

        # Mobile-specific CDP overrides
        if self.sys_info["is_mobile"]:
            self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": w, "height": h, "deviceScaleFactor": 3,
                "mobile": True, "fitWindow": False,
            })
            self.driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
                "enabled": True, "maxTouchPoints": 5,
            })
            self.driver.execute_cdp_cmd("Emulation.setEmitTouchEventsForMouse", {
                "enabled": True, "configuration": "mobile",
            })

        # 9. Inject stealth JS on every new document
        stealth_js = self.build_stealth_js(self.sys_info)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js}
        )

        logger.info("Stealth Chrome launched successfully.")
        return self.driver

    # ================================================================
    # 6. EVIDENCE CAPTURE
    # ================================================================

    def save_evidence(self, step_name: str, output_dir: str = "."):
        """Save full-page screenshot + HTML source for audit/debugging."""
        if not self.driver:
            return

        # HTML source
        html_path = os.path.join(output_dir, f"{step_name}_source.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)

        # Full-page screenshot via CDP
        try:
            metrics = self.driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
            width = math.ceil(metrics["contentSize"]["width"])
            height = min(math.ceil(metrics["contentSize"]["height"]), 16000)

            screenshot = self.driver.execute_cdp_cmd("Page.captureScreenshot", {
                "format": "png",
                "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1},
                "captureBeyondViewport": True,
            })

            import base64
            png_path = os.path.join(output_dir, f"{step_name}_screenshot.png")
            with open(png_path, "wb") as f:
                f.write(base64.b64decode(screenshot["data"]))
        except Exception:
            fallback_path = os.path.join(output_dir, f"{step_name}_screenshot.png")
            self.driver.save_screenshot(fallback_path)

    # ================================================================
    # 7. SHUTDOWN
    # ================================================================

    def quit(self):
        """Gracefully quit browser and virtual display."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        if self._display_started:
            subprocess.run(["pkill", "-9", "-f", "Xvfb"], capture_output=True)
            self._display_started = False

        logger.info("Stealth Chrome shut down.")
