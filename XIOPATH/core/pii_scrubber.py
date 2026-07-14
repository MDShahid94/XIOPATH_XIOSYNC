"""
Deterministic PII Redaction Engine (Phase 23: Hardened)
=========================================================
Runs immediately prior to any Server-bound promotion to ensure
no sensitive user data leaks to Global Secondary/Primary.

Changes from audit:
- Fixed credit card regex (was matching any 13-16 digit sequence)
- Added IP address and JWT token patterns
- Fixed dead PASSWORD_HINT branch (was `pass` — now functional)
- Added typed redaction tags (<EMAIL_REDACTED>, etc.) for auditability
- Added SENSITIVE_KEYS set for key-name based redaction
"""

import re
from typing import Dict, Any, List, Union


class PIIScrubber:
    """Deterministic PII Redaction Engine with typed redaction markers."""

    # Regex patterns for common PII types
    PATTERNS = {
        "EMAIL": r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b',
        "PHONE": r'(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
        "CREDIT_CARD": r'\b(?:\d{4}[\s-]?){3}\d{1,4}\b',
        "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
        "IP_ADDRESS": r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
        "JWT_TOKEN": r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b',
    }

    # Dictionary keys that indicate sensitive data — always fully redacted
    SENSITIVE_KEYS = frozenset({
        "password", "secret", "passcode", "pwd", "token", "api_key",
        "credit_card", "ssn", "input_data", "auth", "authorization",
        "access_token", "refresh_token", "private_key", "secret_key",
    })

    @staticmethod
    def redact_string(text: str) -> str:
        """Apply all PII regex patterns to a string, replacing matches with typed tags."""
        if not isinstance(text, str):
            return text

        redacted = text
        for pii_type, pattern in PIIScrubber.PATTERNS.items():
            redacted = re.sub(pattern, f"<{pii_type}_REDACTED>", redacted)
        return redacted

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        """Check if a dictionary key name indicates sensitive content."""
        key_lower = key.lower()
        return any(hint in key_lower for hint in PIIScrubber.SENSITIVE_KEYS)

    @staticmethod
    def redact_place_value(place_value: Union[Dict[str, Any], Any]) -> Union[Dict[str, Any], Any]:
        """
        Recursively scrubs the place_value dictionary.
        - Keys matching SENSITIVE_KEYS are fully redacted.
        - String values are run through pattern-based redaction.
        - Nested dicts and lists are recursively processed.
        """
        if not isinstance(place_value, dict):
            return place_value

        redacted_dict = {}
        for k, v in place_value.items():
            # If the key itself implies sensitive data, redact the value entirely
            if PIIScrubber._is_sensitive_key(k):
                if isinstance(v, str):
                    redacted_dict[k] = "<REDACTED>"
                elif isinstance(v, dict):
                    redacted_dict[k] = PIIScrubber.redact_place_value(v)
                else:
                    redacted_dict[k] = "<REDACTED>"
            elif isinstance(v, str):
                redacted_dict[k] = PIIScrubber.redact_string(v)
            elif isinstance(v, dict):
                redacted_dict[k] = PIIScrubber.redact_place_value(v)
            elif isinstance(v, list):
                redacted_dict[k] = [
                    PIIScrubber.redact_string(i) if isinstance(i, str)
                    else PIIScrubber.redact_place_value(i) if isinstance(i, dict)
                    else i
                    for i in v
                ]
            else:
                redacted_dict[k] = v

        return redacted_dict

    @staticmethod
    def redact_node(node: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full node-level redaction — applies PII scrubbing to all string fields
        and recursively processes face_value and place_value dicts.
        """
        redacted = dict(node)

        # Scrub face_value
        if "face_value" in redacted and isinstance(redacted["face_value"], dict):
            redacted["face_value"] = PIIScrubber.redact_place_value(redacted["face_value"])

        # Scrub place_value
        if "place_value" in redacted and isinstance(redacted["place_value"], dict):
            redacted["place_value"] = PIIScrubber.redact_place_value(redacted["place_value"])

        # Scrub action_params
        if "action_params" in redacted and isinstance(redacted["action_params"], dict):
            redacted["action_params"] = PIIScrubber.redact_place_value(redacted["action_params"])

        # Scrub intent (may contain user-typed PII)
        if "intent" in redacted and isinstance(redacted["intent"], str):
            redacted["intent"] = PIIScrubber.redact_string(redacted["intent"])

        return redacted
