"""
XIOPATH Phantom Infrastructure — Browser Profile Manager
==========================================================
Manages anti-detect browser profiles for phantom accounts.
Each phantom gets a completely isolated browser environment with:
  - Unique fingerprint (Canvas, WebGL, fonts, screen, navigator)
  - Isolated storage (cookies, localStorage, IndexedDB)
  - Bound proxy (consistent IP per phantom)
  - Behavioral profile (deterministic human simulation)
  - Profile persistence (save/load for session continuity)

Supports both Playwright and Selenium as automation backends.

Educational purpose only.
"""

import json
import os
import shutil
import hashlib
import random
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path


# ════════════════════════════════════════════════
# Browser Fingerprint Generation
# ════════════════════════════════════════════════

# Common real-world screen resolutions
SCREEN_RESOLUTIONS = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720), (1600, 900), (2560, 1440), (1680, 1050),
    (1280, 1024), (1280, 800), (1024, 768), (2560, 1600),
]

# Real-world user-agent templates (Chrome on various OS)
UA_TEMPLATES = {
    "windows_11": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36",
    "windows_10": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36",
    "macos_14": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_{macos_minor}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36",
    "macos_15": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_{macos_minor}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36",
    "linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36",
}

CHROME_VERSIONS = [
    "125.0.6422.112", "126.0.6478.63", "126.0.6478.127",
    "127.0.6533.72", "127.0.6533.100", "128.0.6613.85",
    "129.0.6668.59", "130.0.6723.70", "131.0.6778.85",
    "132.0.6834.57", "133.0.6890.45", "134.0.6946.90",
    "135.0.7049.63", "136.0.7103.48", "137.0.7151.68",
]

# Common GPU renderers (for WebGL fingerprint consistency)
GPU_RENDERERS = [
    "ANGLE (Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Apple GPU",
    "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
    "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
    "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)",
    "Mesa Intel(R) UHD Graphics 630 (CFL GT2)",
]

# Common font lists per OS
FONT_SETS = {
    "windows": [
        "Arial", "Calibri", "Cambria", "Comic Sans MS", "Consolas", "Courier New",
        "Georgia", "Impact", "Lucida Console", "Microsoft Sans Serif", "Palatino Linotype",
        "Segoe UI", "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
    ],
    "macos": [
        "Arial", "Avenir", "Futura", "Georgia", "Gill Sans", "Helvetica",
        "Helvetica Neue", "Lucida Grande", "Menlo", "Monaco", "Optima",
        "Palatino", "SF Pro", "Times New Roman", "Trebuchet MS", "Verdana",
    ],
    "linux": [
        "Arial", "Cantarell", "DejaVu Sans", "DejaVu Sans Mono", "Droid Sans",
        "FreeSans", "Liberation Sans", "Liberation Serif", "Noto Sans",
        "Ubuntu", "Ubuntu Mono",
    ],
}

# Common language/locale combinations
LANGUAGE_CONFIGS = {
    "en-US": {"accept_language": "en-US,en;q=0.9", "nav_language": "en-US", "nav_languages": ["en-US", "en"]},
    "en-GB": {"accept_language": "en-GB,en;q=0.9", "nav_language": "en-GB", "nav_languages": ["en-GB", "en"]},
    "en-IN": {"accept_language": "en-IN,en;q=0.9,hi;q=0.8", "nav_language": "en-IN", "nav_languages": ["en-IN", "en", "hi"]},
    "hi-IN": {"accept_language": "hi-IN,hi;q=0.9,en;q=0.8", "nav_language": "hi", "nav_languages": ["hi", "en-IN", "en"]},
}


@dataclass
class BrowserFingerprint:
    """Complete browser fingerprint for a phantom identity."""
    phantom_id: str

    # Navigator
    user_agent: str = ""
    platform: str = ""
    vendor: str = "Google Inc."
    hardware_concurrency: int = 4
    device_memory: int = 8
    max_touch_points: int = 0

    # Screen
    screen_width: int = 1920
    screen_height: int = 1080
    color_depth: int = 24
    pixel_ratio: float = 1.0

    # WebGL
    webgl_vendor: str = "Google Inc. (Intel)"
    webgl_renderer: str = ""

    # Fonts
    available_fonts: list = field(default_factory=list)

    # Language
    accept_language: str = "en-US,en;q=0.9"
    navigator_language: str = "en-US"
    navigator_languages: list = field(default_factory=lambda: ["en-US", "en"])

    # Timezone
    timezone_name: str = "America/New_York"
    timezone_offset: int = -300  # Minutes

    # Canvas noise seed (for consistent canvas fingerprint perturbation)
    canvas_noise_seed: int = 0

    # WebRTC
    webrtc_policy: str = "disable_non_proxied_udp"  # Prevent IP leak

    # OS hint
    os_family: str = "windows"

    def __post_init__(self):
        if not self.user_agent:
            self._generate_from_seed()

    def _generate_from_seed(self):
        """Generate consistent fingerprint from phantom_id."""
        seed = int(hashlib.sha256(self.phantom_id.encode()).hexdigest(), 16)
        rng = random.Random(seed)

        # Pick OS family
        self.os_family = rng.choice(["windows", "windows", "macos", "macos", "linux"])

        # Generate user agent
        chrome_ver = rng.choice(CHROME_VERSIONS)
        if self.os_family == "windows":
            template = rng.choice([UA_TEMPLATES["windows_10"], UA_TEMPLATES["windows_11"]])
            self.user_agent = template.format(chrome_ver=chrome_ver)
            self.platform = "Win32"
        elif self.os_family == "macos":
            minor = rng.randint(0, 6)
            template = rng.choice([UA_TEMPLATES["macos_14"], UA_TEMPLATES["macos_15"]])
            self.user_agent = template.format(chrome_ver=chrome_ver, macos_minor=minor)
            self.platform = "MacIntel"
        else:
            self.user_agent = UA_TEMPLATES["linux"].format(chrome_ver=chrome_ver)
            self.platform = "Linux x86_64"

        # Screen
        self.screen_width, self.screen_height = rng.choice(SCREEN_RESOLUTIONS)
        self.pixel_ratio = rng.choice([1.0, 1.0, 1.25, 1.5, 2.0])
        self.color_depth = 24

        # Hardware
        self.hardware_concurrency = rng.choice([2, 4, 4, 6, 8, 8, 12, 16])
        self.device_memory = rng.choice([2, 4, 4, 8, 8, 16, 16, 32])
        self.max_touch_points = 0 if self.os_family != "macos" else 0

        # WebGL
        self.webgl_renderer = rng.choice(GPU_RENDERERS)
        self.webgl_vendor = "Google Inc. (Intel)" if "Intel" in self.webgl_renderer else \
                           "Google Inc. (NVIDIA)" if "NVIDIA" in self.webgl_renderer else \
                           "Google Inc. (AMD)" if "AMD" in self.webgl_renderer else \
                           "Google Inc. (Apple)" if "Apple" in self.webgl_renderer else \
                           "Google Inc."

        # Fonts
        font_set = FONT_SETS.get(self.os_family, FONT_SETS["windows"])
        num_fonts = rng.randint(len(font_set) - 4, len(font_set))
        self.available_fonts = sorted(rng.sample(font_set, num_fonts))

        # Canvas noise
        self.canvas_noise_seed = rng.randint(0, 2**32)

    def to_dict(self) -> dict:
        """Serialize fingerprint to dict."""
        return {
            "phantom_id": self.phantom_id,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "vendor": self.vendor,
            "hardware_concurrency": self.hardware_concurrency,
            "device_memory": self.device_memory,
            "max_touch_points": self.max_touch_points,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "color_depth": self.color_depth,
            "pixel_ratio": self.pixel_ratio,
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
            "available_fonts": self.available_fonts,
            "accept_language": self.accept_language,
            "navigator_language": self.navigator_language,
            "navigator_languages": self.navigator_languages,
            "timezone_name": self.timezone_name,
            "timezone_offset": self.timezone_offset,
            "canvas_noise_seed": self.canvas_noise_seed,
            "webrtc_policy": self.webrtc_policy,
            "os_family": self.os_family,
        }


# ════════════════════════════════════════════════
# Profile Manager
# ════════════════════════════════════════════════

@dataclass
class BrowserProfile:
    """A complete browser profile: fingerprint + state + proxy binding."""
    phantom_id: str
    fingerprint: BrowserFingerprint
    proxy_config: Optional[dict] = None
    profile_dir: str = ""
    state: str = "new"  # new, warming, aged, active, locked
    created_at: str = ""
    last_used_at: str = ""
    cookies_count: int = 0
    browsing_history_count: int = 0
    age_days: int = 0

    def to_dict(self) -> dict:
        return {
            "phantom_id": self.phantom_id,
            "fingerprint": self.fingerprint.to_dict(),
            "proxy_config": self.proxy_config,
            "profile_dir": self.profile_dir,
            "state": self.state,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "cookies_count": self.cookies_count,
            "browsing_history_count": self.browsing_history_count,
            "age_days": self.age_days,
        }


class BrowserProfileManager:
    """
    Manages the lifecycle of anti-detect browser profiles.
    
    - Create: Generate new profile with unique fingerprint
    - Load: Restore profile from disk for session continuity
    - Save: Persist profile state after use
    - Age: Pre-warm profiles with organic browsing history
    - Destroy: Securely delete a profile
    """

    def __init__(self, profiles_dir: str, proxy_pool=None):
        """
        Args:
            profiles_dir: Directory to store browser profiles
            proxy_pool: Optional ProxyPool instance for IP binding
        """
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_pool = proxy_pool
        self._profiles_index: dict[str, BrowserProfile] = {}
        self._load_index()

    def create_profile(self, phantom_id: str, locale: str = "en-US",
                       timezone_name: str = "America/New_York") -> BrowserProfile:
        """
        Create a new browser profile with a unique anti-detect fingerprint.
        
        Args:
            phantom_id: The phantom identity ID this profile belongs to
            locale: Locale for language configuration
            timezone_name: Timezone for the fingerprint
        
        Returns:
            BrowserProfile ready for use
        """
        # Generate unique fingerprint
        fingerprint = BrowserFingerprint(phantom_id=phantom_id)

        # Apply locale-specific language config
        lang_config = LANGUAGE_CONFIGS.get(locale, LANGUAGE_CONFIGS["en-US"])
        fingerprint.accept_language = lang_config["accept_language"]
        fingerprint.navigator_language = lang_config["nav_language"]
        fingerprint.navigator_languages = lang_config["nav_languages"]
        fingerprint.timezone_name = timezone_name

        # Create profile directory
        profile_dir = self.profiles_dir / phantom_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Get proxy binding
        proxy_config = None
        if self.proxy_pool:
            proxy = self.proxy_pool.get_proxy_for_phantom(phantom_id)
            proxy_config = {
                "server": f"{proxy.protocol}://{proxy.host}:{proxy.port}",
                "username": proxy.username,
                "password": proxy.password,
            }

        now = datetime.now(timezone.utc).isoformat()
        profile = BrowserProfile(
            phantom_id=phantom_id,
            fingerprint=fingerprint,
            proxy_config=proxy_config,
            profile_dir=str(profile_dir),
            state="new",
            created_at=now,
            last_used_at=now,
        )

        # Save profile metadata
        self._save_profile_meta(profile)
        self._profiles_index[phantom_id] = profile

        return profile

    def get_profile(self, phantom_id: str) -> Optional[BrowserProfile]:
        """Retrieve an existing profile by phantom ID."""
        if phantom_id in self._profiles_index:
            return self._profiles_index[phantom_id]
        return self._load_profile_meta(phantom_id)

    def update_profile_state(self, phantom_id: str, state: str,
                              cookies_count: int = None,
                              browsing_history_count: int = None) -> None:
        """Update profile state after a session."""
        profile = self.get_profile(phantom_id)
        if not profile:
            return

        profile.state = state
        profile.last_used_at = datetime.now(timezone.utc).isoformat()
        if cookies_count is not None:
            profile.cookies_count = cookies_count
        if browsing_history_count is not None:
            profile.browsing_history_count = browsing_history_count

        # Calculate age
        created = datetime.fromisoformat(profile.created_at.replace("Z", "+00:00"))
        age_delta = datetime.now(timezone.utc) - created
        profile.age_days = age_delta.days

        self._save_profile_meta(profile)
        self._profiles_index[phantom_id] = profile

    def destroy_profile(self, phantom_id: str) -> bool:
        """
        Securely destroy a browser profile.
        Overwrites profile data before deletion to prevent recovery.
        """
        profile_dir = self.profiles_dir / phantom_id
        if profile_dir.exists():
            # Overwrite files with random data before deletion
            for file_path in profile_dir.rglob("*"):
                if file_path.is_file():
                    size = file_path.stat().st_size
                    with open(file_path, "wb") as f:
                        f.write(os.urandom(size))
            shutil.rmtree(profile_dir)

        self._profiles_index.pop(phantom_id, None)
        return True

    def list_profiles(self, state: str = None) -> list[dict]:
        """List all profiles, optionally filtered by state."""
        profiles = []
        for pid, profile in self._profiles_index.items():
            if state and profile.state != state:
                continue
            profiles.append({
                "phantom_id": pid,
                "state": profile.state,
                "age_days": profile.age_days,
                "cookies_count": profile.cookies_count,
                "created_at": profile.created_at,
                "last_used_at": profile.last_used_at,
            })
        return profiles

    def get_playwright_context_options(self, phantom_id: str) -> dict:
        """
        Generate Playwright browser context options from a profile.
        Applies the anti-detect fingerprint to the browser context.
        
        Returns:
            Dict suitable for browser.new_context(**options)
        """
        profile = self.get_profile(phantom_id)
        if not profile:
            raise ValueError(f"Profile not found: {phantom_id}")

        fp = profile.fingerprint
        options = {
            "user_agent": fp.user_agent,
            "viewport": {"width": fp.screen_width, "height": fp.screen_height},
            "device_scale_factor": fp.pixel_ratio,
            "locale": fp.navigator_language,
            "timezone_id": fp.timezone_name,
            "color_scheme": "light",
            "extra_http_headers": {
                "Accept-Language": fp.accept_language,
            },
            "permissions": [],
            "geolocation": None,
            "ignore_https_errors": False,
        }

        # Add proxy if configured
        if profile.proxy_config:
            options["proxy"] = profile.proxy_config

        # Add storage state (cookies/localStorage) if profile has been used before
        storage_state_path = Path(profile.profile_dir) / "storage_state.json"
        if storage_state_path.exists():
            options["storage_state"] = str(storage_state_path)

        return options

    def get_fingerprint_injection_script(self, phantom_id: str) -> str:
        """
        Generate a JavaScript script that overrides browser fingerprint APIs.
        Inject this via page.add_init_script() to spoof Canvas, WebGL, fonts, etc.
        
        Returns:
            JavaScript code string
        """
        profile = self.get_profile(phantom_id)
        if not profile:
            raise ValueError(f"Profile not found: {phantom_id}")

        fp = profile.fingerprint
        fp_dict = fp.to_dict()

        return f"""
        // XIOPATH Anti-Detect Fingerprint Injection
        // Phantom: {phantom_id[:8]}
        (function() {{
            'use strict';

            const FP = {json.dumps(fp_dict)};

            // ── Navigator overrides ──
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => FP.hardware_concurrency }});
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => FP.device_memory }});
            Object.defineProperty(navigator, 'platform', {{ get: () => FP.platform }});
            Object.defineProperty(navigator, 'vendor', {{ get: () => FP.vendor }});
            Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => FP.max_touch_points }});
            Object.defineProperty(navigator, 'language', {{ get: () => FP.navigator_language }});
            Object.defineProperty(navigator, 'languages', {{ get: () => Object.freeze(FP.navigator_languages) }});

            // ── Screen overrides ──
            Object.defineProperty(screen, 'width', {{ get: () => FP.screen_width }});
            Object.defineProperty(screen, 'height', {{ get: () => FP.screen_height }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => FP.screen_width }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => FP.screen_height - 40 }});
            Object.defineProperty(screen, 'colorDepth', {{ get: () => FP.color_depth }});
            Object.defineProperty(window, 'devicePixelRatio', {{ get: () => FP.pixel_ratio }});

            // ── Canvas fingerprint noise ──
            const noiseSeed = FP.canvas_noise_seed;
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            const originalGetContext = HTMLCanvasElement.prototype.getContext;

            HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {{
                    try {{
                        const imageData = ctx.getImageData(0, 0, this.width, this.height);
                        const data = imageData.data;
                        let seed = noiseSeed;
                        for (let i = 0; i < data.length; i += 4) {{
                            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF;
                            data[i] = data[i] ^ (seed & 1);     // R: flip LSB
                        }}
                        ctx.putImageData(imageData, 0, 0);
                    }} catch(e) {{}}
                }}
                return originalToDataURL.call(this, type, quality);
            }};

            // ── WebGL fingerprint ──
            const getParameterProxy = new Proxy(WebGLRenderingContext.prototype.getParameter, {{
                apply(target, thisArg, args) {{
                    const param = args[0];
                    if (param === 0x9245) return FP.webgl_vendor;     // UNMASKED_VENDOR_WEBGL
                    if (param === 0x9246) return FP.webgl_renderer;   // UNMASKED_RENDERER_WEBGL
                    return Reflect.apply(target, thisArg, args);
                }}
            }});
            WebGLRenderingContext.prototype.getParameter = getParameterProxy;

            if (typeof WebGL2RenderingContext !== 'undefined') {{
                WebGL2RenderingContext.prototype.getParameter = getParameterProxy;
            }}

            // ── WebRTC IP leak protection ──
            if (typeof RTCPeerConnection !== 'undefined') {{
                const origRTC = RTCPeerConnection;
                window.RTCPeerConnection = function(config, constraints) {{
                    if (config && config.iceServers) {{
                        config.iceServers = [];
                    }}
                    return new origRTC(config, constraints);
                }};
                window.RTCPeerConnection.prototype = origRTC.prototype;
            }}

            // ── Plugins/MimeTypes (consistent with Chrome) ──
            Object.defineProperty(navigator, 'plugins', {{
                get: () => {{
                    const arr = [
                        {{ name: 'PDF Viewer', filename: 'internal-pdf-viewer' }},
                        {{ name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' }},
                        {{ name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' }},
                    ];
                    arr.length = 3;
                    return arr;
                }}
            }});

            console.log('[XIOPATH] Fingerprint injection complete');
        }})();
        """

    def save_session_state(self, phantom_id: str, storage_state: dict) -> None:
        """Save browser storage state (cookies, localStorage) after a session."""
        profile = self.get_profile(phantom_id)
        if not profile:
            return
        state_path = Path(profile.profile_dir) / "storage_state.json"
        with open(state_path, "w") as f:
            json.dump(storage_state, f, indent=2)

    def _save_profile_meta(self, profile: BrowserProfile) -> None:
        """Save profile metadata to disk."""
        meta_path = Path(profile.profile_dir) / "profile_meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w") as f:
            json.dump(profile.to_dict(), f, indent=2)

    def _load_profile_meta(self, phantom_id: str) -> Optional[BrowserProfile]:
        """Load profile metadata from disk."""
        meta_path = self.profiles_dir / phantom_id / "profile_meta.json"
        if not meta_path.exists():
            return None
        with open(meta_path, "r") as f:
            data = json.load(f)
        fp = BrowserFingerprint(phantom_id=phantom_id)
        fp.__dict__.update(data.get("fingerprint", {}))
        profile = BrowserProfile(
            phantom_id=phantom_id,
            fingerprint=fp,
            proxy_config=data.get("proxy_config"),
            profile_dir=str(self.profiles_dir / phantom_id),
            state=data.get("state", "new"),
            created_at=data.get("created_at", ""),
            last_used_at=data.get("last_used_at", ""),
            cookies_count=data.get("cookies_count", 0),
            browsing_history_count=data.get("browsing_history_count", 0),
            age_days=data.get("age_days", 0),
        )
        self._profiles_index[phantom_id] = profile
        return profile

    def _load_index(self) -> None:
        """Load all profile metadata on startup."""
        if not self.profiles_dir.exists():
            return
        for subdir in self.profiles_dir.iterdir():
            if subdir.is_dir() and (subdir / "profile_meta.json").exists():
                self._load_profile_meta(subdir.name)
