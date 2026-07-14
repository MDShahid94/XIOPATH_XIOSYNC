"""
XIOPATH Phantom Infrastructure — Proxy Pool Manager
=====================================================
Educational reference implementation for managing a pool of proxy
servers with rotation, health checking, deterministic phantom-to-proxy
mapping, and format conversion for Playwright / Selenium.

EDUCATIONAL PURPOSE ONLY.
"""

from __future__ import annotations

import hashlib
import json
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 1. ProxyConfig — structured proxy definition
# ---------------------------------------------------------------------------

@dataclass
class ProxyConfig:
    """Immutable description of a single proxy endpoint."""

    host: str
    port: int
    username: str = ""
    password: str = ""
    protocol: str = "http"          # http | https | socks5
    country: str = ""               # ISO-3166-1 alpha-2 (e.g. "US")
    sticky_session_id: str = ""     # provider-specific session pin

    # -- convenience --------------------------------------------------------

    @property
    def url(self) -> str:
        """Full proxy URL including credentials when present."""
        auth = ""
        if self.username:
            auth = f"{self.username}:{self.password}@" if self.password else f"{self.username}@"
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (for JSON persistence)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProxyConfig":
        """Deserialize from a plain dict."""
        return cls(
            host=data["host"],
            port=int(data["port"]),
            username=data.get("username", ""),
            password=data.get("password", ""),
            protocol=data.get("protocol", "http"),
            country=data.get("country", ""),
            sticky_session_id=data.get("sticky_session_id", ""),
        )

    def __hash__(self) -> int:
        return hash((self.host, self.port, self.protocol))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProxyConfig):
            return NotImplemented
        return (self.host, self.port, self.protocol) == (other.host, other.port, other.protocol)


# ---------------------------------------------------------------------------
# 2. ProxyPool — rotation, health checking, format conversion
# ---------------------------------------------------------------------------

class ProxyPool:
    """Thread-unsafe proxy pool with rotation, deterministic mapping,
    health checking, and serialisation helpers.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Parameters
        ----------
        config_path : str or None
            Path to a JSON file containing a list of proxy dicts.
            If provided and the file exists, proxies are loaded on init.
        """
        self._proxies: list[ProxyConfig] = []
        self._dead: set[ProxyConfig] = set()
        self._rotation_index: int = 0
        self._config_path: Optional[str] = config_path

        if config_path:
            path = Path(config_path)
            if path.is_file():
                self.load_config()

    # -- pool management ----------------------------------------------------

    def add_proxy(self, proxy: ProxyConfig) -> None:
        """Add a proxy to the pool (de-duplicated by host:port:protocol)."""
        if proxy not in self._proxies:
            self._proxies.append(proxy)

    def get_proxy(
        self,
        country: Optional[str] = None,
        sticky: bool = False,
    ) -> Optional[ProxyConfig]:
        """Return the next live proxy, optionally filtered by *country*.

        Parameters
        ----------
        country : str or None
            ISO country code to filter by.
        sticky : bool
            If ``True``, only return proxies with a ``sticky_session_id``.

        Returns
        -------
        ProxyConfig or None
        """
        candidates = [
            p for p in self._proxies
            if p not in self._dead
            and (country is None or p.country.upper() == country.upper())
            and (not sticky or p.sticky_session_id)
        ]
        if not candidates:
            return None

        idx = self._rotation_index % len(candidates)
        self._rotation_index += 1
        return candidates[idx]

    def get_proxy_for_phantom(self, phantom_id: str) -> Optional[ProxyConfig]:
        """Deterministically map a *phantom_id* to a proxy.

        Uses a SHA-256 hash of the phantom ID to pick a stable index,
        so the same phantom always gets the same proxy (as long as the
        pool doesn't change).
        """
        live = [p for p in self._proxies if p not in self._dead]
        if not live:
            return None
        digest = hashlib.sha256(phantom_id.encode()).hexdigest()
        idx = int(digest, 16) % len(live)
        return live[idx]

    def rotate(self) -> Optional[ProxyConfig]:
        """Advance the rotation counter and return the next live proxy."""
        return self.get_proxy()

    def mark_dead(self, proxy: ProxyConfig) -> None:
        """Mark *proxy* as dead so it is excluded from future selections."""
        self._dead.add(proxy)

    def revive(self, proxy: ProxyConfig) -> None:
        """Remove *proxy* from the dead set."""
        self._dead.discard(proxy)

    # -- health check -------------------------------------------------------

    def health_check(self, proxy: ProxyConfig) -> bool:
        """Return ``True`` if the proxy can reach an external endpoint.

        Attempts to fetch ``http://httpbin.org/ip`` through the proxy
        and verifies a successful JSON response.
        """
        proxy_handler = urllib.request.ProxyHandler(
            {"http": proxy.url, "https": proxy.url}
        )
        opener = urllib.request.build_opener(proxy_handler)

        try:
            req = urllib.request.Request(
                "http://httpbin.org/ip",
                method="GET",
                headers={"User-Agent": "XIOPATH-HealthCheck/1.0"},
            )
            with opener.open(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return "origin" in body
        except (urllib.error.URLError, socket.timeout, OSError, json.JSONDecodeError):
            return False

    def health_check_all(self) -> dict[str, bool]:
        """Run :meth:`health_check` on every proxy and return a status map."""
        results: dict[str, bool] = {}
        for proxy in self._proxies:
            key = f"{proxy.host}:{proxy.port}"
            alive = self.health_check(proxy)
            results[key] = alive
            if not alive:
                self.mark_dead(proxy)
            else:
                self.revive(proxy)
        return results

    # -- format conversion --------------------------------------------------

    @staticmethod
    def to_playwright_proxy(proxy: ProxyConfig) -> dict[str, Any]:
        """Convert to the dict format expected by Playwright's ``proxy=`` kwarg.

        Returns
        -------
        dict
            ``{"server": "protocol://host:port", "username": ..., "password": ...}``
        """
        result: dict[str, Any] = {
            "server": f"{proxy.protocol}://{proxy.host}:{proxy.port}",
        }
        if proxy.username:
            result["username"] = proxy.username
        if proxy.password:
            result["password"] = proxy.password
        return result

    @staticmethod
    def to_selenium_proxy(proxy: ProxyConfig) -> dict[str, Any]:
        """Convert to the dict used to configure Selenium wire / options.

        Returns
        -------
        dict
            ``{"httpProxy": ..., "sslProxy": ..., "proxyType": "MANUAL"}``
            with optional ``socksProxy`` for SOCKS5 proxies.
        """
        url = f"{proxy.host}:{proxy.port}"
        if proxy.username:
            auth = f"{proxy.username}:{proxy.password}@" if proxy.password else f"{proxy.username}@"
            url = auth + url

        result: dict[str, Any] = {"proxyType": "MANUAL"}

        if proxy.protocol in ("socks5", "socks4"):
            result["socksProxy"] = url
            result["socksVersion"] = 5 if proxy.protocol == "socks5" else 4
        else:
            result["httpProxy"] = url
            result["sslProxy"] = url

        return result

    # -- persistence --------------------------------------------------------

    def save_config(self, path: Optional[str] = None) -> None:
        """Serialize the pool to a JSON file.

        Parameters
        ----------
        path : str or None
            Destination file. Falls back to the *config_path* given at init.
        """
        dest = path or self._config_path
        if dest is None:
            raise ValueError("No config path specified")

        data = {
            "proxies": [p.to_dict() for p in self._proxies],
            "dead": [p.to_dict() for p in self._dead],
            "rotation_index": self._rotation_index,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_config(self, path: Optional[str] = None) -> None:
        """Load the pool from a JSON file, replacing current state.

        Parameters
        ----------
        path : str or None
            Source file. Falls back to the *config_path* given at init.
        """
        src = path or self._config_path
        if src is None:
            raise ValueError("No config path specified")

        raw = Path(src).read_text(encoding="utf-8")
        data = json.loads(raw)

        self._proxies = [ProxyConfig.from_dict(p) for p in data.get("proxies", [])]
        self._dead = {ProxyConfig.from_dict(p) for p in data.get("dead", [])}
        self._rotation_index = data.get("rotation_index", 0)

    # -- introspection ------------------------------------------------------

    @property
    def size(self) -> int:
        """Total number of proxies (alive + dead)."""
        return len(self._proxies)

    @property
    def alive_count(self) -> int:
        """Number of proxies not marked dead."""
        return len([p for p in self._proxies if p not in self._dead])

    def __repr__(self) -> str:
        return (
            f"ProxyPool(total={self.size}, alive={self.alive_count}, "
            f"rotation={self._rotation_index})"
        )


# ---------------------------------------------------------------------------
# 3. DirectConnection — no-proxy passthrough
# ---------------------------------------------------------------------------

class DirectConnection:
    """Placeholder that satisfies the same interface as :class:`ProxyPool`
    but routes traffic directly (no proxy).

    Useful for local testing or when proxies are unnecessary.
    """

    def add_proxy(self, proxy: ProxyConfig) -> None:
        """No-op: direct connections don't use proxies."""
        pass

    def get_proxy(
        self,
        country: Optional[str] = None,
        sticky: bool = False,
    ) -> None:
        """Always returns ``None`` (no proxy)."""
        return None

    def get_proxy_for_phantom(self, phantom_id: str) -> None:
        """Always returns ``None``."""
        return None

    def rotate(self) -> None:
        """No-op."""
        return None

    def mark_dead(self, proxy: ProxyConfig) -> None:
        """No-op."""
        pass

    def health_check(self, proxy: ProxyConfig) -> bool:
        """Always returns ``True`` — direct connection is assumed healthy."""
        return True

    @staticmethod
    def to_playwright_proxy(proxy: ProxyConfig) -> dict[str, Any]:
        """Return an empty dict (no proxy config)."""
        return {}

    @staticmethod
    def to_selenium_proxy(proxy: ProxyConfig) -> dict[str, Any]:
        """Return a ``DIRECT`` proxy type dict."""
        return {"proxyType": "DIRECT"}

    def save_config(self, path: Optional[str] = None) -> None:
        """No-op."""
        pass

    def load_config(self, path: Optional[str] = None) -> None:
        """No-op."""
        pass

    def __repr__(self) -> str:
        return "DirectConnection()"


# ---------------------------------------------------------------------------
# CLI quick-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== ProxyPool Demo ===\n")

    pool = ProxyPool()

    # Add sample proxies
    proxies = [
        ProxyConfig(host="proxy1.example.com", port=8080, country="US", protocol="http"),
        ProxyConfig(host="proxy2.example.com", port=8080, country="DE", protocol="http",
                    username="user", password="pass"),
        ProxyConfig(host="proxy3.example.com", port=1080, country="US", protocol="socks5",
                    sticky_session_id="sess_abc123"),
    ]
    for p in proxies:
        pool.add_proxy(p)

    print(f"Pool        : {pool}")
    print(f"Next (any)  : {pool.get_proxy()}")
    print(f"Next (US)   : {pool.get_proxy(country='US')}")
    print(f"Sticky only : {pool.get_proxy(sticky=True)}")
    print(f"Phantom map : {pool.get_proxy_for_phantom('phantom_42')}")

    sample = proxies[1]
    print(f"\nPlaywright  : {ProxyPool.to_playwright_proxy(sample)}")
    print(f"Selenium    : {ProxyPool.to_selenium_proxy(sample)}")

    pool.mark_dead(proxies[0])
    print(f"\nAfter death : {pool}")
    print(f"Next (any)  : {pool.get_proxy()}")

    print("\n=== DirectConnection ===")
    direct = DirectConnection()
    print(f"Proxy       : {direct.get_proxy()}")
    print(f"Selenium    : {direct.to_selenium_proxy(proxies[0])}")
