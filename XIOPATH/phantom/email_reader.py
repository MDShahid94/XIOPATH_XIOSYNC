"""
XIOPATH Phantom Infrastructure — Email Reader
===============================================
Educational reference implementation for reading Gmail via IMAP,
parsing MIME messages, and extracting verification codes / links.

Requires a Gmail **App Password** (not the account password) with
IMAP enabled in Gmail settings.

EDUCATIONAL PURPOSE ONLY.
"""

from __future__ import annotations

import email
import email.header
import email.policy
import email.utils
import imaplib
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 1. GmailIMAPReader — connect, search, read, extract verification
# ---------------------------------------------------------------------------

class GmailIMAPReader:
    """Read-only Gmail IMAP client for automated verification retrieval.

    Uses :mod:`imaplib` and :mod:`email` from the standard library.
    """

    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993

    def __init__(self, email_address: str, app_password: str) -> None:
        """
        Parameters
        ----------
        email_address : str
            Full Gmail address (e.g. ``phantom42@gmail.com``).
        app_password : str
            A 16-character Google App Password.
        """
        self._email: str = email_address
        self._password: str = app_password
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    # -- connection lifecycle -----------------------------------------------

    def connect(self) -> None:
        """Establish an IMAP4_SSL connection and authenticate."""
        if self._conn is not None:
            try:
                self._conn.noop()
                return  # already connected
            except Exception:
                self._conn = None

        self._conn = imaplib.IMAP4_SSL(self.IMAP_HOST, self.IMAP_PORT)
        self._conn.login(self._email, self._password)
        self._conn.select("INBOX")

    def close(self) -> None:
        """Gracefully close the IMAP connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "GmailIMAPReader":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _decode_header(raw: Optional[str]) -> str:
        """Decode an RFC-2047 encoded header value into a plain string."""
        if raw is None:
            return ""
        parts = email.header.decode_header(raw)
        decoded_fragments: list[str] = []
        for fragment, charset in parts:
            if isinstance(fragment, bytes):
                decoded_fragments.append(
                    fragment.decode(charset or "utf-8", errors="replace")
                )
            else:
                decoded_fragments.append(fragment)
        return " ".join(decoded_fragments)

    @staticmethod
    def _extract_body(msg: email.message.Message) -> tuple[str, str]:
        """Walk a MIME message and return ``(text_plain, text_html)``."""
        text_plain: str = ""
        text_html: str = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if content_type == "text/plain" and not text_plain:
                    text_plain = decoded
                elif content_type == "text/html" and not text_html:
                    text_html = decoded
        else:
            payload = msg.get_payload(decode=True)
            if payload is not None:
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    text_html = decoded
                else:
                    text_plain = decoded

        return text_plain, text_html

    # -- search -------------------------------------------------------------

    def search_recent(
        self,
        from_addr: Optional[str] = None,
        subject_contains: Optional[str] = None,
        max_age_seconds: int = 300,
    ) -> list[dict[str, Any]]:
        """Search INBOX for recent messages matching optional filters.

        Parameters
        ----------
        from_addr : str or None
            Filter by sender address (partial match via IMAP FROM).
        subject_contains : str or None
            Filter by substring in the Subject header.
        max_age_seconds : int
            Only return messages received within this many seconds.

        Returns
        -------
        list[dict]
            Each dict has keys: ``id``, ``from``, ``subject``, ``date``.
        """
        if self._conn is None:
            raise RuntimeError("Not connected — call connect() first")

        # Build IMAP SEARCH criteria
        criteria_parts: list[str] = []

        # IMAP SINCE uses date (not datetime), so we compute the date boundary
        since_dt = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since_str = since_dt.strftime("%d-%b-%Y")
        criteria_parts.append(f'SINCE "{since_str}"')

        if from_addr:
            criteria_parts.append(f'FROM "{from_addr}"')
        if subject_contains:
            criteria_parts.append(f'SUBJECT "{subject_contains}"')

        criteria = " ".join(criteria_parts) if criteria_parts else "ALL"

        status, data = self._conn.search(None, f"({criteria})")
        if status != "OK" or not data or not data[0]:
            return []

        msg_ids: list[bytes] = data[0].split()
        cutoff = time.time() - max_age_seconds
        results: list[dict[str, Any]] = []

        for mid in reversed(msg_ids):  # newest first
            status, msg_data = self._conn.fetch(mid, "(RFC822.HEADER)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw_header = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            if isinstance(raw_header, int):
                continue
            header_msg = email.message_from_bytes(raw_header)

            date_str = header_msg.get("Date", "")
            parsed_date = email.utils.parsedate_to_datetime(date_str) if date_str else None
            if parsed_date and parsed_date.timestamp() < cutoff:
                continue  # too old

            results.append(
                {
                    "id": mid.decode("ascii"),
                    "from": self._decode_header(header_msg.get("From")),
                    "subject": self._decode_header(header_msg.get("Subject")),
                    "date": date_str,
                }
            )

        return results

    # -- read full message --------------------------------------------------

    def read_email(self, email_id: str) -> dict[str, Any]:
        """Fetch and parse a full message by its IMAP sequence number.

        Returns
        -------
        dict
            ``{"from", "subject", "body_text", "body_html", "date"}``
        """
        if self._conn is None:
            raise RuntimeError("Not connected — call connect() first")

        status, msg_data = self._conn.fetch(email_id.encode(), "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            raise RuntimeError(f"Failed to fetch email id={email_id}")

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
        msg = email.message_from_bytes(raw)

        body_text, body_html = self._extract_body(msg)

        return {
            "from": self._decode_header(msg.get("From")),
            "subject": self._decode_header(msg.get("Subject")),
            "body_text": body_text,
            "body_html": body_html,
            "date": msg.get("Date", ""),
        }

    # -- verification extraction from inbox ---------------------------------

    def extract_verification_from_inbox(
        self,
        from_pattern: str,
        timeout: int = 120,
    ) -> Optional[dict[str, str]]:
        """Poll INBOX for a verification code/link from a matching sender.

        Parameters
        ----------
        from_pattern : str
            Substring or regex pattern to match against the ``From`` header.
        timeout : int
            Maximum seconds to wait.

        Returns
        -------
        dict or None
            ``{"type": "code"|"link", "value": "..."}`` or ``None``.
        """
        if self._conn is None:
            raise RuntimeError("Not connected — call connect() first")

        from_re = re.compile(from_pattern, re.IGNORECASE)
        deadline = time.monotonic() + timeout
        seen_ids: set[str] = set()

        while time.monotonic() < deadline:
            recent = self.search_recent(max_age_seconds=timeout + 60)

            for entry in recent:
                eid: str = entry["id"]
                if eid in seen_ids:
                    continue
                seen_ids.add(eid)

                if not from_re.search(entry.get("from", "")):
                    continue

                try:
                    full = self.read_email(eid)
                except Exception:
                    continue

                combined = (full.get("body_text", "") + " " + full.get("body_html", ""))
                result = extract_code_or_link(combined)
                if result:
                    return result

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(5.0, max(1.0, remaining / 4)))

        return None


# ---------------------------------------------------------------------------
# 2. extract_code_or_link — standalone extraction utility
# ---------------------------------------------------------------------------

def extract_code_or_link(text: str) -> Optional[dict[str, str]]:
    """Extract a 6-digit verification code **or** a verification URL from *text*.

    Detection heuristics (in priority order):

    1. **Verification links** — URLs containing keywords like ``verify``,
       ``confirm``, ``activate``, ``validate``, or ``token``.
    2. **Button href links** — ``href="..."`` values with the same keywords.
    3. **6-digit codes** — A standalone sequence of exactly six digits,
       optionally preceded by labels like *code*, *OTP*, or *PIN*.

    Returns
    -------
    dict or None
        ``{"type": "link", "value": "https://..."}`` or
        ``{"type": "code", "value": "123456"}`` or ``None``.
    """
    # -- verification / confirmation links ----------------------------------
    url_keywords = r"(?:verif|confirm|activate|validate|token|auth|signin|signup)"

    # Plain-text URLs
    plain_link_re = re.compile(
        r'https?://[^\s"\'<>]+' + url_keywords + r'[^\s"\'<>]*',
        re.IGNORECASE,
    )
    match = plain_link_re.search(text)
    if match:
        url = match.group(0).rstrip(".,;)>]}")
        return {"type": "link", "value": url}

    # href="..." inside HTML
    href_re = re.compile(
        r'href\s*=\s*["\']([^"\']*' + url_keywords + r'[^"\']*)["\']',
        re.IGNORECASE,
    )
    match = href_re.search(text)
    if match:
        return {"type": "link", "value": match.group(1)}

    # -- 6-digit code -------------------------------------------------------
    # Look for codes near context words first
    context_code_re = re.compile(
        r"(?:code|otp|pin|verification|confirm)\s*(?:is|:)?\s*(\d{6})\b",
        re.IGNORECASE,
    )
    match = context_code_re.search(text)
    if match:
        return {"type": "code", "value": match.group(1)}

    # Fallback: any standalone 6-digit number
    bare_code_re = re.compile(r"(?<!\d)(\d{6})(?!\d)")
    match = bare_code_re.search(text)
    if match:
        return {"type": "code", "value": match.group(1)}

    return None


# ---------------------------------------------------------------------------
# CLI quick-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== extract_code_or_link Demo ===")

    samples = [
        "Your code is 849302. Use it within 10 minutes.",
        "Click here to verify: https://example.com/verify?token=abc123xyz",
        '<a href="https://service.com/confirm/user/98765">Confirm Email</a>',
        "Thank you for signing up! OTP: 112233",
        "No verification info here, just a regular email.",
    ]

    for body in samples:
        result = extract_code_or_link(body)
        preview = body[:60].replace("\n", " ")
        print(f"  Input : {preview}...")
        print(f"  Result: {result}\n")
