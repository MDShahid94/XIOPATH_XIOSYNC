"""
XIOPATH Phantom Infrastructure — Encryption Core
==================================================

Educational-purpose cryptographic module providing:

* **AESCipher** — AES-256-GCM authenticated encryption with HKDF-based
  per-context key derivation.
* **ShamirSecret** — Shamir's Secret Sharing over GF(2⁸) for splitting /
  reconstructing master keys.
* Utility helpers: master-key generation, password generation, UUIDv7.

Dependencies:
    pip install cryptography

All randomness sourced from ``os.urandom`` (CSPRNG).
"""

from __future__ import annotations

import base64
import json
import os
import string
import struct
import time
from typing import List, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# ---------------------------------------------------------------------------
# GF(256) arithmetic helpers for Shamir Secret Sharing
# ---------------------------------------------------------------------------

# AES irreducible polynomial: x⁸ + x⁴ + x³ + x + 1  →  0x11B
_GF256_MODULUS: int = 0x11B

# Pre-computed log / exp tables (generator = 3)
_EXP_TABLE: list[int] = [0] * 512
_LOG_TABLE: list[int] = [0] * 256


def _init_gf256_tables() -> None:
    """Build log / exp lookup tables for GF(256) with generator 3."""
    x = 1
    for i in range(255):
        _EXP_TABLE[i] = x
        _LOG_TABLE[x] = i
        x = _gf256_mul_nomod(x, 3)
    # Wrap the table so indices > 254 still work.
    for i in range(255, 512):
        _EXP_TABLE[i] = _EXP_TABLE[i - 255]


def _gf256_mul_nomod(a: int, b: int) -> int:
    """Multiply *a* × *b* in GF(256) using Russian-peasant algorithm."""
    result = 0
    while b > 0:
        if b & 1:
            result ^= a
        a <<= 1
        if a & 0x100:
            a ^= _GF256_MODULUS
        b >>= 1
    return result


_init_gf256_tables()


def _gf256_add(a: int, b: int) -> int:
    """Addition in GF(256) is XOR."""
    return a ^ b


def _gf256_mul(a: int, b: int) -> int:
    """Multiply two GF(256) elements via log/exp tables."""
    if a == 0 or b == 0:
        return 0
    return _EXP_TABLE[_LOG_TABLE[a] + _LOG_TABLE[b]]


def _gf256_inv(a: int) -> int:
    """Multiplicative inverse in GF(256)."""
    if a == 0:
        raise ZeroDivisionError("No inverse for 0 in GF(256)")
    return _EXP_TABLE[255 - _LOG_TABLE[a]]


def _gf256_div(a: int, b: int) -> int:
    """Division a / b in GF(256)."""
    if b == 0:
        raise ZeroDivisionError("Division by zero in GF(256)")
    if a == 0:
        return 0
    return _EXP_TABLE[(_LOG_TABLE[a] + 255 - _LOG_TABLE[b]) % 255]


# ---------------------------------------------------------------------------
# AESCipher
# ---------------------------------------------------------------------------


class AESCipher:
    """AES-256-GCM authenticated encryption with HKDF-based key derivation.

    Parameters
    ----------
    master_key : bytes
        Exactly 32 bytes (256 bits).  Typically produced by
        :func:`generate_master_key` or reconstructed via
        :class:`ShamirSecret`.

    Raises
    ------
    ValueError
        If *master_key* is not 32 bytes.

    Example
    -------
    >>> key = generate_master_key()
    >>> cipher = AESCipher(key)
    >>> token = cipher.encrypt("top secret", b"context-aad")
    >>> cipher.decrypt(token, b"context-aad")
    'top secret'
    """

    _KEY_LENGTH: int = 32  # 256-bit key

    def __init__(self, master_key: bytes) -> None:
        if not isinstance(master_key, bytes) or len(master_key) != self._KEY_LENGTH:
            raise ValueError(
                f"master_key must be exactly {self._KEY_LENGTH} bytes, "
                f"got {len(master_key) if isinstance(master_key, bytes) else type(master_key)}"
            )
        self._master_key: bytes = master_key

    # -- public API ---------------------------------------------------------

    def encrypt(self, plaintext: str, associated_data: bytes = b"") -> str:
        """Encrypt *plaintext* with AES-256-GCM.

        Parameters
        ----------
        plaintext : str
            UTF-8 text to encrypt.
        associated_data : bytes
            Optional additional authenticated data (AAD).

        Returns
        -------
        str
            Base64-encoded JSON string with keys ``nonce``, ``ciphertext``,
            and ``tag`` — each value is Base64-encoded bytes.
        """
        nonce: bytes = os.urandom(12)  # 96-bit nonce recommended for GCM
        aesgcm = AESGCM(self._master_key)
        # AESGCM.encrypt returns ciphertext || tag (last 16 bytes = tag)
        ct_with_tag: bytes = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data)
        ciphertext: bytes = ct_with_tag[:-16]
        tag: bytes = ct_with_tag[-16:]

        payload = {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
        }
        return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted: str, associated_data: bytes = b"") -> str:
        """Decrypt a token produced by :meth:`encrypt`.

        Parameters
        ----------
        encrypted : str
            Base64-encoded JSON string as returned by :meth:`encrypt`.
        associated_data : bytes
            Must match the AAD used during encryption.

        Returns
        -------
        str
            The original plaintext.

        Raises
        ------
        cryptography.exceptions.InvalidTag
            If the authentication tag does not verify (wrong key / tampered data).
        ValueError
            If the token is malformed.
        """
        try:
            payload: dict = json.loads(base64.b64decode(encrypted))
        except (json.JSONDecodeError, Exception) as exc:
            raise ValueError(f"Malformed encrypted token: {exc}") from exc

        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
        tag = base64.b64decode(payload["tag"])

        aesgcm = AESGCM(self._master_key)
        plaintext_bytes: bytes = aesgcm.decrypt(nonce, ciphertext + tag, associated_data)
        return plaintext_bytes.decode("utf-8")

    def derive_key(self, context: str, info: str = "") -> bytes:
        """Derive a 256-bit sub-key via HKDF-SHA256.

        Parameters
        ----------
        context : str
            Used as the HKDF *salt* (UTF-8 encoded).
        info : str
            Used as the HKDF *info* parameter (UTF-8 encoded).

        Returns
        -------
        bytes
            32-byte derived key.
        """
        hkdf = HKDF(
            algorithm=SHA256(),
            length=self._KEY_LENGTH,
            salt=context.encode("utf-8"),
            info=info.encode("utf-8"),
        )
        return hkdf.derive(self._master_key)


# ---------------------------------------------------------------------------
# Shamir Secret Sharing (GF(256))
# ---------------------------------------------------------------------------


class ShamirSecret:
    """Shamir's Secret Sharing over GF(2⁸).

    Secrets are split **byte-by-byte**: for an *N*-byte secret each share
    is also *N* bytes, with each byte position sharing an independent
    polynomial of degree *threshold − 1*.

    Example
    -------
    >>> secret = generate_master_key()
    >>> shares = ShamirSecret.split(secret, threshold=3, shares=5)
    >>> recovered = ShamirSecret.reconstruct(shares[:3])
    >>> recovered == secret
    True
    """

    @staticmethod
    def split(secret: bytes, threshold: int, shares: int) -> List[Tuple[int, bytes]]:
        """Split *secret* into *shares* pieces; any *threshold* can reconstruct.

        Parameters
        ----------
        secret : bytes
            The secret to split.
        threshold : int
            Minimum number of shares needed for reconstruction (2 ≤ *threshold* ≤ *shares*).
        shares : int
            Total number of shares to generate (≤ 255).

        Returns
        -------
        list[tuple[int, bytes]]
            Each element is ``(x, share_bytes)`` where *x* ∈ [1, 255].

        Raises
        ------
        ValueError
            If parameter constraints are violated.
        """
        if threshold < 2:
            raise ValueError("threshold must be ≥ 2")
        if shares < threshold:
            raise ValueError("shares must be ≥ threshold")
        if shares > 255:
            raise ValueError("shares must be ≤ 255 (GF(256) constraint)")
        if len(secret) == 0:
            raise ValueError("secret must be non-empty")

        # For each byte position, build an independent random polynomial
        # whose constant term is the secret byte.
        share_values: list[list[int]] = [[] for _ in range(shares)]

        for byte_val in secret:
            # Random coefficients a_1 … a_{t-1}; a_0 = byte_val
            coeffs: list[int] = [byte_val] + [
                int.from_bytes(os.urandom(1), "big") for _ in range(threshold - 1)
            ]
            for idx in range(shares):
                x = idx + 1  # evaluation point (1-based)
                y = ShamirSecret._eval_poly(coeffs, x)
                share_values[idx].append(y)

        return [(i + 1, bytes(share_values[i])) for i in range(shares)]

    @staticmethod
    def reconstruct(shares: List[Tuple[int, bytes]]) -> bytes:
        """Reconstruct the secret from *threshold* or more shares.

        Parameters
        ----------
        shares : list[tuple[int, bytes]]
            Subset of shares produced by :meth:`split`.

        Returns
        -------
        bytes
            The reconstructed secret.

        Raises
        ------
        ValueError
            If fewer than 2 shares are provided or lengths mismatch.
        """
        if len(shares) < 2:
            raise ValueError("Need at least 2 shares to reconstruct")

        length = len(shares[0][1])
        if any(len(s) != length for _, s in shares):
            raise ValueError("All shares must have the same length")

        xs: list[int] = [x for x, _ in shares]
        secret_bytes: list[int] = []

        for byte_idx in range(length):
            ys = [s[byte_idx] for _, s in shares]
            secret_bytes.append(ShamirSecret._lagrange_interpolate_at_zero(xs, ys))

        return bytes(secret_bytes)

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _eval_poly(coeffs: list[int], x: int) -> int:
        """Evaluate polynomial at *x* in GF(256) using Horner's method."""
        result = 0
        for coeff in reversed(coeffs):
            result = _gf256_add(_gf256_mul(result, x), coeff)
        return result

    @staticmethod
    def _lagrange_interpolate_at_zero(xs: list[int], ys: list[int]) -> int:
        """Lagrange interpolation at x = 0 in GF(256)."""
        result = 0
        k = len(xs)
        for i in range(k):
            numerator = ys[i]
            for j in range(k):
                if i == j:
                    continue
                # L_i(0) = ∏_{j≠i} (0 - x_j) / (x_i - x_j)
                #         = ∏_{j≠i} x_j / (x_i ⊕ x_j)   [GF(256): subtraction = XOR]
                numerator = _gf256_mul(numerator, xs[j])
                numerator = _gf256_div(numerator, _gf256_add(xs[i], xs[j]))
            result = _gf256_add(result, numerator)
        return result


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def generate_master_key() -> bytes:
    """Generate a cryptographically random 256-bit (32-byte) master key.

    Returns
    -------
    bytes
        32 random bytes from ``os.urandom``.
    """
    return os.urandom(32)


def generate_password(length: int = 24) -> str:
    """Generate a cryptographically random password.

    The password contains mixed-case ASCII letters, digits, and the
    punctuation characters ``!@#$%^&*()-_=+[]{}|;:,.<>?``.

    Parameters
    ----------
    length : int
        Desired password length (default 24, minimum 8).

    Returns
    -------
    str
        A random password string.

    Raises
    ------
    ValueError
        If *length* < 8.
    """
    if length < 8:
        raise ValueError("Password length must be at least 8")

    alphabet: str = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"

    # Guarantee at least one character from each category.
    categories: list[str] = [
        string.ascii_lowercase,
        string.ascii_uppercase,
        string.digits,
        "!@#$%^&*()-_=+[]{}|;:,.<>?",
    ]

    # Pick one mandatory character per category.
    mandatory: list[str] = [
        _secure_choice(cat) for cat in categories
    ]

    # Fill the rest randomly from the full alphabet.
    rest: list[str] = [
        _secure_choice(alphabet) for _ in range(length - len(mandatory))
    ]

    # Combine and shuffle securely.
    password_chars: list[str] = mandatory + rest
    _secure_shuffle(password_chars)
    return "".join(password_chars)


def uuid7() -> str:
    """Generate a UUIDv7 (timestamp-sortable, RFC 9562 draft).

    Layout (128 bits):
        48 bits — Unix timestamp in milliseconds
         4 bits — version (0b0111)
        12 bits — random (rand_a)
         2 bits — variant (0b10)
        62 bits — random (rand_b)

    Returns
    -------
    str
        Standard UUID string representation, e.g.
        ``"018f3b3c-8e4a-7xxx-bxxx-xxxxxxxxxxxx"``.
    """
    timestamp_ms: int = int(time.time() * 1000)

    # 48-bit timestamp → 6 bytes
    ts_bytes: bytes = struct.pack(">Q", timestamp_ms)[2:]  # last 6 bytes of 8-byte big-endian

    # 10 random bytes for the remaining 80 bits
    rand_bytes: bytes = os.urandom(10)

    uuid_bytes = bytearray(ts_bytes + rand_bytes)  # total 16 bytes

    # Set version (bits 48-51) to 0b0111  →  byte index 6, high nibble
    uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x70

    # Set variant (bits 64-65) to 0b10  →  byte index 8, high 2 bits
    uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80

    hex_str: str = uuid_bytes.hex()
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _secure_choice(seq: str) -> str:
    """Pick a random element from *seq* using ``os.urandom``."""
    idx = int.from_bytes(os.urandom(4), "big") % len(seq)
    return seq[idx]


def _secure_shuffle(lst: list) -> None:
    """Fisher–Yates shuffle using ``os.urandom`` for randomness."""
    for i in range(len(lst) - 1, 0, -1):
        j = int.from_bytes(os.urandom(4), "big") % (i + 1)
        lst[i], lst[j] = lst[j], lst[i]
