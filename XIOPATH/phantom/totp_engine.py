"""
XIOPATH Phantom Infrastructure — Native TOTP Engine
=====================================================
A zero-external-dependency TOTP implementation built entirely on the
Python standard library (hmac, hashlib, struct, time, base64, secrets).

Educational reference implementation of RFC 6238 (TOTP) and RFC 4226 (HOTP).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import string
import struct
import time
from urllib.parse import quote, urlencode, urlparse, parse_qs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ALGO_MAP: dict[str, type] = {
    "SHA1": hashlib.sha1,      # type: ignore[dict-item]
    "SHA256": hashlib.sha256,  # type: ignore[dict-item]
    "SHA512": hashlib.sha512,  # type: ignore[dict-item]
}

# Base32 alphabet for secret generation
_BASE32_ALPHABET: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _decode_secret(secret_b32: str) -> bytes:
    """Decode a base32-encoded secret, tolerating missing padding.

    Args:
        secret_b32: The base32-encoded secret string. Case-insensitive;
            spaces and hyphens are stripped automatically.

    Returns:
        The decoded raw bytes of the secret.
    """
    cleaned = secret_b32.upper().replace(" ", "").replace("-", "")
    # Add missing padding
    padding = (8 - len(cleaned) % 8) % 8
    cleaned += "=" * padding
    return base64.b32decode(cleaned)


def _hotp(secret_bytes: bytes, counter: int, digits: int, algorithm: str) -> str:
    """Compute an HOTP value per RFC 4226.

    Args:
        secret_bytes: Raw secret key bytes.
        counter: 8-byte big-endian counter value.
        digits: Number of output digits (6 or 8 recommended).
        algorithm: Hash algorithm name ('SHA1', 'SHA256', 'SHA512').

    Returns:
        Zero-padded HOTP code string of length ``digits``.
    """
    hash_func = _ALGO_MAP.get(algorithm.upper(), hashlib.sha1)
    counter_bytes = struct.pack(">Q", counter)
    hmac_digest = hmac.new(secret_bytes, counter_bytes, hash_func).digest()

    # Dynamic truncation (RFC 4226 §5.4)
    offset = hmac_digest[-1] & 0x0F
    truncated = struct.unpack(">I", hmac_digest[offset : offset + 4])[0]
    truncated &= 0x7FFFFFFF

    code = truncated % (10 ** digits)
    return str(code).zfill(digits)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_totp(
    secret_b32: str,
    period: int = 30,
    digits: int = 6,
    algorithm: str = "SHA1",
) -> str:
    """Generate a TOTP code for the current time.

    Implements RFC 6238 using the current system clock.

    Args:
        secret_b32: Base32-encoded shared secret.
        period: Time-step duration in seconds (default 30).
        digits: Number of digits in the output code (default 6).
        algorithm: Hash algorithm — one of 'SHA1', 'SHA256', 'SHA512'.

    Returns:
        A zero-padded string of ``digits`` length.

    Example::

        >>> secret = generate_secret()
        >>> code = generate_totp(secret)
        >>> len(code)
        6
    """
    secret_bytes = _decode_secret(secret_b32)
    counter = int(time.time()) // period
    return _hotp(secret_bytes, counter, digits, algorithm)


def generate_totp_at(
    secret_b32: str,
    timestamp: float,
    period: int = 30,
    digits: int = 6,
    algorithm: str = "SHA1",
) -> str:
    """Generate a TOTP code for a specific Unix timestamp.

    Useful for testing, replaying, or pre-computing codes.

    Args:
        secret_b32: Base32-encoded shared secret.
        timestamp: Unix timestamp (seconds since epoch) to evaluate at.
        period: Time-step duration in seconds (default 30).
        digits: Number of digits in the output code (default 6).
        algorithm: Hash algorithm — one of 'SHA1', 'SHA256', 'SHA512'.

    Returns:
        A zero-padded string of ``digits`` length.

    Example::

        >>> generate_totp_at("JBSWY3DPEHPK3PXP", 1234567890)
        '005924'
    """
    secret_bytes = _decode_secret(secret_b32)
    counter = int(timestamp) // period
    return _hotp(secret_bytes, counter, digits, algorithm)


def verify_totp(
    secret_b32: str,
    code: str,
    window: int = 1,
    period: int = 30,
    digits: int = 6,
    algorithm: str = "SHA1",
) -> bool:
    """Verify a TOTP code against the current time within a tolerance window.

    Checks the code against the current counter value and ``window``
    adjacent counter values on either side to compensate for clock drift.

    Args:
        secret_b32: Base32-encoded shared secret.
        code: The TOTP code string to verify.
        window: Number of time-steps to check on each side of the current
            counter (default 1, meaning codes from -30s to +30s are valid).
        period: Time-step duration in seconds (default 30).
        digits: Expected number of digits (default 6).
        algorithm: Hash algorithm — one of 'SHA1', 'SHA256', 'SHA512'.

    Returns:
        ``True`` if the code matches any counter value within the window,
        ``False`` otherwise.

    Example::

        >>> secret = generate_secret()
        >>> code = generate_totp(secret)
        >>> verify_totp(secret, code)
        True
    """
    secret_bytes = _decode_secret(secret_b32)
    current_counter = int(time.time()) // period

    for offset in range(-window, window + 1):
        expected = _hotp(secret_bytes, current_counter + offset, digits, algorithm)
        if hmac.compare_digest(expected, code.zfill(digits)):
            return True

    return False


def parse_otpauth_uri(uri: str) -> dict:
    """Parse an ``otpauth://`` URI into its constituent parameters.

    Handles both ``totp`` and ``hotp`` URI types as defined by the
    Google Authenticator key-URI format.

    Args:
        uri: A full ``otpauth://`` URI string.

    Returns:
        A dictionary with the following keys (when present):

        - ``type`` (str): 'totp' or 'hotp'.
        - ``label`` (str): The full label (issuer:account or just account).
        - ``account`` (str): The account/email portion of the label.
        - ``issuer`` (str): Issuer name.
        - ``secret`` (str): Base32-encoded secret.
        - ``algorithm`` (str): Hash algorithm (default 'SHA1').
        - ``digits`` (int): Code length (default 6).
        - ``period`` (int): Time-step in seconds (default 30, TOTP only).
        - ``counter`` (int): Initial counter (HOTP only).

    Raises:
        ValueError: If the URI scheme is not ``otpauth``.

    Example::

        >>> uri = "otpauth://totp/XIOPATH:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=XIOPATH"
        >>> info = parse_otpauth_uri(uri)
        >>> info['secret']
        'JBSWY3DPEHPK3PXP'
    """
    parsed = urlparse(uri)
    if parsed.scheme != "otpauth":
        raise ValueError(f"Invalid OTP auth URI scheme: {parsed.scheme!r}")

    otp_type = parsed.hostname or parsed.netloc  # 'totp' or 'hotp'
    # The path contains the label, URL-encoded
    label = parsed.path.lstrip("/")

    params = parse_qs(parsed.query)
    # parse_qs returns lists — unwrap single values
    flat_params: dict[str, str] = {k: v[0] for k, v in params.items()}

    # Split label into issuer and account
    if ":" in label:
        label_issuer, account = label.split(":", 1)
    else:
        label_issuer = ""
        account = label

    # Issuer precedence: query param > label prefix
    issuer = flat_params.get("issuer", label_issuer)

    result: dict = {
        "type": otp_type,
        "label": label,
        "account": account,
        "issuer": issuer,
        "secret": flat_params.get("secret", ""),
        "algorithm": flat_params.get("algorithm", "SHA1").upper(),
        "digits": int(flat_params.get("digits", "6")),
    }

    if otp_type == "totp":
        result["period"] = int(flat_params.get("period", "30"))
    elif otp_type == "hotp":
        result["counter"] = int(flat_params.get("counter", "0"))

    return result


def generate_otpauth_uri(
    secret: str,
    account: str,
    issuer: str = "XIOPATH",
    algorithm: str = "SHA1",
    digits: int = 6,
    period: int = 30,
) -> str:
    """Generate an ``otpauth://`` TOTP URI suitable for QR encoding.

    Produces a URI compatible with Google Authenticator and other TOTP
    apps following the key-URI format specification.

    Args:
        secret: Base32-encoded shared secret.
        account: Account name or email to display in the authenticator.
        issuer: Issuer label (default 'XIOPATH').
        algorithm: Hash algorithm (default 'SHA1').
        digits: Number of digits (default 6).
        period: Time-step in seconds (default 30).

    Returns:
        A fully-formed ``otpauth://totp/...`` URI string.

    Example::

        >>> generate_otpauth_uri("JBSWY3DPEHPK3PXP", "user@example.com")
        'otpauth://totp/XIOPATH:user%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=XIOPATH&algorithm=SHA1&digits=6&period=30'
    """
    label = f"{quote(issuer)}:{quote(account)}"
    params = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": algorithm.upper(),
            "digits": str(digits),
            "period": str(period),
        }
    )
    return f"otpauth://totp/{label}?{params}"


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically random base32-encoded secret.

    Uses ``secrets.choice`` for cryptographic randomness to produce a
    secret string composed of valid base32 characters.

    Args:
        length: Number of base32 characters in the output (default 32).
            Longer secrets provide more entropy.

    Returns:
        An uppercase base32 string of the specified length.

    Example::

        >>> secret = generate_secret()
        >>> len(secret)
        32
        >>> all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567' for c in secret)
        True
    """
    return "".join(secrets.choice(_BASE32_ALPHABET) for _ in range(length))
