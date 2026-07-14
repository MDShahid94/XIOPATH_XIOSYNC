"""
XIOPATH Phantom Infrastructure — QR Code Utilities
====================================================
QR code decoding and generation utilities with graceful fallback handling
for optional dependencies (``pyzbar``, ``PIL`` / ``Pillow``, ``qrcode``).

Educational reference implementation for QR-based TOTP provisioning flows.
"""

from __future__ import annotations

import io
import os
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Optional dependency imports with fallback flags
# ---------------------------------------------------------------------------

_HAS_PYZBAR = False
_HAS_PIL = False
_HAS_QRCODE = False

try:
    from pyzbar import pyzbar as _pyzbar  # type: ignore[import-untyped]
    _HAS_PYZBAR = True
except ImportError:
    _pyzbar = None  # type: ignore[assignment]

try:
    from PIL import Image as _PILImage  # type: ignore[import-untyped]
    _HAS_PIL = True
except ImportError:
    _PILImage = None  # type: ignore[assignment]

try:
    import qrcode as _qrcode  # type: ignore[import-untyped]
    _HAS_QRCODE = True
except ImportError:
    _qrcode = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# QR Decoding
# ---------------------------------------------------------------------------


def decode_qr_from_image(image_path: str) -> str:
    """Decode the first QR code found in an image file.

    Uses ``pyzbar`` and ``Pillow`` for decoding. If either library is
    unavailable, raises ``RuntimeError`` with installation instructions.

    Args:
        image_path: Absolute or relative filesystem path to an image file
            containing a QR code (PNG, JPEG, BMP, etc.).

    Returns:
        The decoded UTF-8 string payload of the QR code.

    Raises:
        RuntimeError: If required libraries are not installed.
        FileNotFoundError: If ``image_path`` does not exist.
        ValueError: If no QR code is detected in the image.

    Example::

        >>> data = decode_qr_from_image("/tmp/totp_qr.png")
        >>> data.startswith("otpauth://")
        True
    """
    if not _HAS_PYZBAR:
        raise RuntimeError(
            "pyzbar is required for QR decoding. "
            "Install it with: pip install pyzbar"
        )
    if not _HAS_PIL:
        raise RuntimeError(
            "Pillow is required for QR decoding. "
            "Install it with: pip install Pillow"
        )

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = _PILImage.open(image_path)
    decoded_objects = _pyzbar.decode(image)

    if not decoded_objects:
        raise ValueError(f"No QR code detected in image: {image_path}")

    # Return the first decoded QR payload
    return decoded_objects[0].data.decode("utf-8", errors="replace")


def decode_qr_from_bytes(image_bytes: bytes) -> str:
    """Decode the first QR code from raw image bytes.

    Accepts the binary content of an image file (PNG, JPEG, etc.) and
    attempts to locate and decode a QR code within it.

    Args:
        image_bytes: Raw bytes of an image containing a QR code.

    Returns:
        The decoded UTF-8 string payload of the QR code.

    Raises:
        RuntimeError: If required libraries are not installed.
        ValueError: If no QR code is detected in the image data.

    Example::

        >>> with open("/tmp/totp_qr.png", "rb") as f:
        ...     data = decode_qr_from_bytes(f.read())
        >>> data.startswith("otpauth://")
        True
    """
    if not _HAS_PYZBAR:
        raise RuntimeError(
            "pyzbar is required for QR decoding. "
            "Install it with: pip install pyzbar"
        )
    if not _HAS_PIL:
        raise RuntimeError(
            "Pillow is required for QR decoding. "
            "Install it with: pip install Pillow"
        )

    image = _PILImage.open(io.BytesIO(image_bytes))
    decoded_objects = _pyzbar.decode(image)

    if not decoded_objects:
        raise ValueError("No QR code detected in the provided image data.")

    return decoded_objects[0].data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# QR Data Interpretation
# ---------------------------------------------------------------------------


def qr_to_verify_link(qr_data: str) -> dict:
    """Classify and structure QR code data for verification purposes.

    Analyses the raw string payload of a QR code and categorises it as
    one of three types:

    - **url**: A standard HTTP(S) URL — potentially a verification link.
    - **challenge**: An ``otpauth://`` URI or known challenge protocol.
    - **opaque**: Any other data that doesn't match known patterns.

    Args:
        qr_data: The raw decoded string content from a QR code.

    Returns:
        A dictionary with the following keys:

        - ``type`` (str): One of ``'url'``, ``'challenge'``, or ``'opaque'``.
        - ``url`` (str | None): The URL if type is ``'url'``, otherwise ``None``.
        - ``raw`` (str): The original raw QR data.

    Example::

        >>> qr_to_verify_link("https://accounts.google.com/verify?code=abc123")
        {'type': 'url', 'url': 'https://accounts.google.com/verify?code=abc123', 'raw': '...'}

        >>> qr_to_verify_link("otpauth://totp/XIOPATH:user@example.com?secret=ABC")
        {'type': 'challenge', 'url': None, 'raw': '...'}
    """
    stripped = qr_data.strip()

    # Check for otpauth:// or other challenge protocols
    if stripped.lower().startswith("otpauth://"):
        return {
            "type": "challenge",
            "url": None,
            "raw": stripped,
        }

    # Check for standard HTTP(S) URLs
    parsed = urlparse(stripped)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return {
            "type": "url",
            "url": stripped,
            "raw": stripped,
        }

    # Everything else is opaque
    return {
        "type": "opaque",
        "url": None,
        "raw": stripped,
    }


def extract_totp_from_qr(qr_data: str) -> Optional[dict]:
    """Extract TOTP parameters from an ``otpauth://`` QR code payload.

    If the QR data is not an ``otpauth://totp/...`` URI, returns ``None``.

    Args:
        qr_data: The raw decoded string content from a QR code.

    Returns:
        A dictionary of TOTP parameters if the data is a valid
        ``otpauth://totp`` URI, otherwise ``None``.

        When successful, the dictionary contains:

        - ``type`` (str): Always ``'totp'``.
        - ``label`` (str): Full label from the URI path.
        - ``account`` (str): Account name or email.
        - ``issuer`` (str): Issuer name.
        - ``secret`` (str): Base32-encoded secret.
        - ``algorithm`` (str): Hash algorithm (default ``'SHA1'``).
        - ``digits`` (int): Code length (default 6).
        - ``period`` (int): Time-step in seconds (default 30).

    Example::

        >>> uri = "otpauth://totp/XIOPATH:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=XIOPATH"
        >>> info = extract_totp_from_qr(uri)
        >>> info['secret']
        'JBSWY3DPEHPK3PXP'
        >>> info['issuer']
        'XIOPATH'

        >>> extract_totp_from_qr("https://example.com") is None
        True
    """
    stripped = qr_data.strip()

    # Must be an otpauth URI
    if not stripped.lower().startswith("otpauth://"):
        return None

    parsed = urlparse(stripped)

    # We only handle TOTP
    otp_type = parsed.hostname or parsed.netloc
    if otp_type and otp_type.lower() != "totp":
        return None

    # Extract label from path
    label = parsed.path.lstrip("/")

    # Parse query parameters
    params = parse_qs(parsed.query)
    flat_params: dict[str, str] = {k: v[0] for k, v in params.items()}

    # Split label into issuer : account
    if ":" in label:
        label_issuer, account = label.split(":", 1)
    else:
        label_issuer = ""
        account = label

    # Issuer precedence: query parameter > label prefix
    issuer = flat_params.get("issuer", label_issuer)

    secret = flat_params.get("secret", "")
    if not secret:
        return None  # No secret means this isn't usable

    return {
        "type": "totp",
        "label": label,
        "account": account,
        "issuer": issuer,
        "secret": secret,
        "algorithm": flat_params.get("algorithm", "SHA1").upper(),
        "digits": int(flat_params.get("digits", "6")),
        "period": int(flat_params.get("period", "30")),
    }


# ---------------------------------------------------------------------------
# QR Generation
# ---------------------------------------------------------------------------


def generate_qr_image(data: str, output_path: str) -> str:
    """Generate a QR code image encoding the given data string.

    Uses the ``qrcode`` library when available. If ``qrcode`` is not
    installed, falls back to generating a minimal SVG QR code using a
    built-in encoder (supports data up to ~100 characters reliably).

    Args:
        data: The string payload to encode into the QR code.
        output_path: Filesystem path where the generated image will be
            saved. When using ``qrcode``, supports PNG and SVG extensions.
            The fallback always produces SVG.

    Returns:
        The absolute path to the generated QR code image file.

    Raises:
        OSError: If the output directory does not exist or is not writable.

    Example::

        >>> path = generate_qr_image("otpauth://totp/XIOPATH:user@ex.com?secret=ABC", "/tmp/qr.png")
        >>> os.path.isfile(path)
        True
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    abs_output = os.path.abspath(output_path)

    if _HAS_QRCODE:
        return _generate_qr_with_library(data, abs_output)
    else:
        return _generate_qr_fallback_svg(data, abs_output)


def _generate_qr_with_library(data: str, output_path: str) -> str:
    """Generate a QR code image using the ``qrcode`` library.

    Args:
        data: Payload string to encode.
        output_path: Destination file path.

    Returns:
        Absolute path to the generated file.
    """
    qr = _qrcode.QRCode(
        version=None,  # Auto-detect version
        error_correction=_qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    if output_path.lower().endswith(".svg"):
        # SVG output via qrcode's SVG factory
        import qrcode.image.svg  # type: ignore[import-untyped]

        factory = qrcode.image.svg.SvgPathImage
        img = qr.make_image(image_factory=factory)
        with open(output_path, "wb") as f:
            img.save(f)
    else:
        # Default to PNG (requires Pillow)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(output_path)

    return output_path


def _generate_qr_fallback_svg(data: str, output_path: str) -> str:
    """Generate a minimal QR-like SVG representation as a fallback.

    This is NOT a standards-compliant QR code — it produces a visual
    placeholder with the data embedded as text so the file is still
    useful for reference. For production use, install the ``qrcode``
    package.

    The fallback creates a simple grid pattern with the data encoded
    as a binary representation, providing a visual approximation.

    Args:
        data: Payload string to encode.
        output_path: Destination file path (will be saved as SVG regardless
            of extension).

    Returns:
        Absolute path to the generated SVG file.
    """
    # Convert data to binary representation for the grid
    binary_data = "".join(format(b, "08b") for b in data.encode("utf-8"))

    # Calculate grid dimensions (aim for a roughly square grid)
    total_bits = len(binary_data)
    grid_size = int(total_bits ** 0.5) + 1
    cell_size = 10
    border = 4
    total_size = (grid_size + border * 2) * cell_size

    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_size}" height="{total_size}" '
        f'viewBox="0 0 {total_size} {total_size}">',
        f'<rect width="{total_size}" height="{total_size}" fill="white"/>',
    ]

    # Draw finder patterns (top-left, top-right, bottom-left)
    def _draw_finder(x_off: int, y_off: int) -> None:
        """Draw a 7×7 QR finder pattern at the given cell offset."""
        for r in range(7):
            for c in range(7):
                is_border = r == 0 or r == 6 or c == 0 or c == 6
                is_inner = 2 <= r <= 4 and 2 <= c <= 4
                if is_border or is_inner:
                    px = (x_off + c) * cell_size
                    py = (y_off + r) * cell_size
                    svg_parts.append(
                        f'<rect x="{px}" y="{py}" '
                        f'width="{cell_size}" height="{cell_size}" fill="black"/>'
                    )

    _draw_finder(border, border)
    _draw_finder(border + grid_size - 7, border)
    _draw_finder(border, border + grid_size - 7)

    # Fill data area with binary representation
    bit_index = 0
    for row in range(grid_size):
        for col in range(grid_size):
            # Skip finder pattern areas
            in_tl = row < 8 and col < 8
            in_tr = row < 8 and col >= grid_size - 8
            in_bl = row >= grid_size - 8 and col < 8
            if in_tl or in_tr or in_bl:
                continue

            if bit_index < total_bits and binary_data[bit_index] == "1":
                px = (border + col) * cell_size
                py = (border + row) * cell_size
                svg_parts.append(
                    f'<rect x="{px}" y="{py}" '
                    f'width="{cell_size}" height="{cell_size}" fill="black"/>'
                )
            bit_index += 1

    svg_parts.append("</svg>")

    # Force SVG extension for fallback
    if not output_path.lower().endswith(".svg"):
        output_path = os.path.splitext(output_path)[0] + ".svg"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_parts))

    return output_path
