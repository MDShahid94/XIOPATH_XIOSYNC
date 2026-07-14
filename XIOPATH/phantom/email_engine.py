"""
XIOPATH Phantom Infrastructure — Email Strategy Engine
========================================================
Educational reference implementation demonstrating email aliasing
strategies (Gmail dot-trick, plus-addressing), disposable inbox
management via the mail.tm public API, and verification extraction.

EDUCATIONAL PURPOSE ONLY.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from itertools import combinations
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 1. EmailStrategy — dot variants, plus aliases, waterfall ordering
# ---------------------------------------------------------------------------

class EmailStrategy:
    """Generates ordered lists of email aliases for a single Gmail address.

    Gmail ignores dots in the local part and supports ``+tag`` suffixes,
    so ``j.doe@gmail.com``, ``jd.oe@gmail.com``, and
    ``jdoe+shop@gmail.com`` all land in the same inbox.
    """

    def __init__(self, base_email: str) -> None:
        """
        Parameters
        ----------
        base_email : str
            The phantom's canonical Gmail address (e.g. ``phantom42@gmail.com``).
        """
        if "@" not in base_email:
            raise ValueError(f"Invalid email address: {base_email!r}")
        local, domain = base_email.split("@", 1)
        self._local: str = local.replace(".", "")  # canonical (no dots)
        self._domain: str = domain
        self._base: str = f"{self._local}@{self._domain}"

    # -- dot variants -------------------------------------------------------

    def generate_dot_variants(self, count: int = 3) -> list[str]:
        """Return up to *count* unique dot-placement variants.

        A dot can be inserted between any two adjacent characters in the
        local part.  We enumerate a random subset of all legal placements.
        """
        local = self._local
        if len(local) < 2:
            return [self._base]

        # Possible insertion points: indices 1 .. len-1
        positions: list[int] = list(range(1, len(local)))

        all_variants: list[str] = []
        # Try every combination size from 1 up to len(positions)
        for r in range(1, len(positions) + 1):
            for combo in combinations(positions, r):
                parts: list[str] = []
                prev = 0
                for pos in combo:
                    parts.append(local[prev:pos])
                    prev = pos
                parts.append(local[prev:])
                variant = ".".join(parts) + f"@{self._domain}"
                all_variants.append(variant)

        # Deduplicate (shouldn't happen, but safety) & exclude exact base
        seen: set[str] = set()
        unique: list[str] = []
        for v in all_variants:
            if v not in seen and v != self._base:
                seen.add(v)
                unique.append(v)

        random.shuffle(unique)
        return unique[:count]

    # -- plus aliases -------------------------------------------------------

    def generate_plus_aliases(self, service_names: list[str]) -> dict[str, str]:
        """Return ``{service_name: local+service@domain}`` for each service."""
        result: dict[str, str] = {}
        for svc in service_names:
            tag = re.sub(r"[^a-zA-Z0-9_]", "", svc).lower()
            result[svc] = f"{self._local}+{tag}@{self._domain}"
        return result

    # -- waterfall ----------------------------------------------------------

    def get_waterfall(self, service_name: str) -> list[str]:
        """Ordered list of addresses to attempt for *service_name*.

        Priority:
        1. Canonical address (no dots, no plus).
        2. Plus-alias for the service.
        3. Dot variants (up to 3).
        """
        waterfall: list[str] = [self._base]
        plus = self.generate_plus_aliases([service_name])
        waterfall.append(plus[service_name])
        waterfall.extend(self.generate_dot_variants(count=3))
        return waterfall


# ---------------------------------------------------------------------------
# 2. DisposableEmailManager — mail.tm public API via urllib.request
# ---------------------------------------------------------------------------

class DisposableEmailManager:
    """Create and poll disposable inboxes using the **mail.tm** REST API.

    All HTTP calls use :mod:`urllib.request` (stdlib only).
    """

    _MAILTM_BASE: str = "https://api.mail.tm"

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _request(
        url: str,
        method: str = "GET",
        data: Optional[dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fire an HTTP request and return parsed JSON."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body: Optional[bytes] = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"mail.tm API error {exc.code}: {error_body}"
            ) from exc

    def _get_domains(self) -> list[str]:
        """Fetch currently available mail.tm domains."""
        resp = self._request(f"{self._MAILTM_BASE}/domains")
        members = resp.get("hydra:member", resp) if isinstance(resp, dict) else resp
        if isinstance(members, list):
            return [d["domain"] for d in members if "domain" in d]
        return []

    # -- public API ---------------------------------------------------------

    def create_inbox(self, provider: str = "auto") -> dict[str, str]:
        """Create a fresh disposable inbox.

        Returns
        -------
        dict
            ``{"email": ..., "inbox_id": ..., "provider": "mail.tm",
              "password": ..., "token": ...}``
        """
        if provider not in ("auto", "mail.tm"):
            raise ValueError(f"Unsupported provider: {provider!r}")

        domains = self._get_domains()
        if not domains:
            raise RuntimeError("No mail.tm domains available")

        domain = random.choice(domains)
        local = f"phantom{random.randint(100000, 999999)}"
        address = f"{local}@{domain}"
        password = f"Px{random.randint(10**11, 10**12 - 1)}"

        # Create account
        self._request(
            f"{self._MAILTM_BASE}/accounts",
            method="POST",
            data={"address": address, "password": password},
        )

        # Obtain JWT token
        token_resp = self._request(
            f"{self._MAILTM_BASE}/token",
            method="POST",
            data={"address": address, "password": password},
        )
        token: str = token_resp.get("token", "")
        account_id: str = token_resp.get("id", "")

        return {
            "email": address,
            "inbox_id": account_id,
            "provider": "mail.tm",
            "password": password,
            "token": token,
        }

    def check_inbox(self, inbox_id: str, provider: str, token: str = "") -> list[dict[str, Any]]:
        """Return a list of message summaries in the disposable inbox.

        Parameters
        ----------
        inbox_id : str
            Account / inbox identifier returned by :meth:`create_inbox`.
        provider : str
            Must be ``"mail.tm"``.
        token : str
            Bearer token for authentication.
        """
        if provider != "mail.tm":
            raise ValueError(f"Unsupported provider: {provider!r}")

        resp = self._request(
            f"{self._MAILTM_BASE}/messages",
            token=token,
        )
        members = resp.get("hydra:member", []) if isinstance(resp, dict) else resp

        messages: list[dict[str, Any]] = []
        for msg in members:
            messages.append(
                {
                    "id": msg.get("id", ""),
                    "from": msg.get("from", {}).get("address", ""),
                    "subject": msg.get("subject", ""),
                    "intro": msg.get("intro", ""),
                    "seen": msg.get("seen", False),
                    "date": msg.get("createdAt", ""),
                }
            )
        return messages

    # -- verification extraction --------------------------------------------

    @staticmethod
    def extract_verification(email_body: str) -> Optional[dict[str, str]]:
        """Parse a 6-digit code **or** verification link from *email_body*.

        Returns
        -------
        dict or None
            ``{"type": "code", "value": "123456"}`` or
            ``{"type": "link", "value": "https://..."}`` or ``None``.
        """
        # 6-digit numeric code (standalone)
        code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", email_body)

        # Verification / confirmation links
        link_pattern = re.compile(
            r'https?://[^\s"\'<>]+(?:verif|confirm|activate|validate|token)[^\s"\'<>]*',
            re.IGNORECASE,
        )
        link_match = link_pattern.search(email_body)

        # Prefer explicit link over bare code when both are present
        if link_match:
            return {"type": "link", "value": link_match.group(0).rstrip(".,;)")}
        if code_match:
            return {"type": "code", "value": code_match.group(1)}
        return None

    def wait_for_verification(
        self,
        inbox_id: str,
        provider: str,
        timeout: int = 120,
        token: str = "",
    ) -> Optional[dict[str, str]]:
        """Poll the inbox until a verification code/link arrives or *timeout* elapses.

        Parameters
        ----------
        inbox_id : str
            Inbox identifier.
        provider : str
            Provider name (``"mail.tm"``).
        timeout : int
            Maximum seconds to wait.
        token : str
            Bearer token for mail.tm authentication.

        Returns
        -------
        dict or None
            Verification payload or ``None`` on timeout.
        """
        deadline = time.monotonic() + timeout
        seen_ids: set[str] = set()

        while time.monotonic() < deadline:
            try:
                messages = self.check_inbox(inbox_id, provider, token=token)
            except Exception:
                time.sleep(5)
                continue

            for msg in messages:
                msg_id = msg.get("id", "")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                # Fetch full message body
                try:
                    full = self._request(
                        f"{self._MAILTM_BASE}/messages/{msg_id}",
                        token=token,
                    )
                except Exception:
                    continue

                body_text: str = full.get("text", "") or full.get("intro", "")
                body_html: str = full.get("html", "") or ""

                result = self.extract_verification(body_text)
                if result:
                    return result
                result = self.extract_verification(body_html)
                if result:
                    return result

            remaining = deadline - time.monotonic()
            time.sleep(min(5.0, max(1.0, remaining / 4)))

        return None


# ---------------------------------------------------------------------------
# 3. SERVICE_EMAIL_SUPPORT — per-service capability flags
# ---------------------------------------------------------------------------

SERVICE_EMAIL_SUPPORT: dict[str, dict[str, bool]] = {
    "twitter": {
        "dot_variants": True,
        "plus_aliases": False,
        "disposable": False,
    },
    "instagram": {
        "dot_variants": True,
        "plus_aliases": False,
        "disposable": False,
    },
    "facebook": {
        "dot_variants": True,
        "plus_aliases": True,
        "disposable": False,
    },
    "reddit": {
        "dot_variants": True,
        "plus_aliases": True,
        "disposable": True,
    },
    "discord": {
        "dot_variants": True,
        "plus_aliases": True,
        "disposable": False,
    },
    "github": {
        "dot_variants": True,
        "plus_aliases": True,
        "disposable": True,
    },
    "linkedin": {
        "dot_variants": True,
        "plus_aliases": False,
        "disposable": False,
    },
    "tiktok": {
        "dot_variants": True,
        "plus_aliases": False,
        "disposable": False,
    },
    "spotify": {
        "dot_variants": True,
        "plus_aliases": True,
        "disposable": True,
    },
    "netflix": {
        "dot_variants": True,
        "plus_aliases": False,
        "disposable": False,
    },
}


# ---------------------------------------------------------------------------
# CLI quick-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== EmailStrategy Demo ===")
    strat = EmailStrategy("phantom.user42@gmail.com")
    print(f"Dot variants : {strat.generate_dot_variants(3)}")
    print(f"Plus aliases : {strat.generate_plus_aliases(['twitter', 'reddit'])}")
    print(f"Waterfall    : {strat.get_waterfall('github')}")

    print("\n=== SERVICE_EMAIL_SUPPORT ===")
    for svc, flags in SERVICE_EMAIL_SUPPORT.items():
        print(f"  {svc:12s} -> {flags}")

    print("\n=== DisposableEmailManager (extract_verification demo) ===")
    demo_body = "Your verification code is 482917. Click https://example.com/verify?token=abc123"
    result = DisposableEmailManager.extract_verification(demo_body)
    print(f"  Extracted: {result}")
