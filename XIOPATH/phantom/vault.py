"""
XIOPATH Phantom Infrastructure — Credential Vault
===================================================

Educational-purpose encrypted credential vault backed by SQLite.

* Each phantom identity record is encrypted with a **per-record** HKDF-derived
  key so that compromising one record does not expose others.
* Browser profiles (arbitrary binary) are encrypted similarly.
* Every mutation is logged in the ``vault_log`` table for auditability.

Dependencies:
    * ``phantom.crypto`` (this project)
    * ``cryptography`` (via ``phantom.crypto``)
    * Python ≥ 3.10 standard library (``sqlite3``, ``json``, ``datetime``, …)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from phantom.crypto import AESCipher, uuid7

# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_DDL_PHANTOM_IDENTITIES = """
CREATE TABLE IF NOT EXISTS phantom_identities (
    id              TEXT PRIMARY KEY,
    encrypted_data  TEXT    NOT NULL,
    state           TEXT    NOT NULL DEFAULT 'active',
    member_donor_id TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    revoked_at      TEXT,
    revoke_reason   TEXT
);
"""

_DDL_BROWSER_PROFILES = """
CREATE TABLE IF NOT EXISTS browser_profiles (
    phantom_id        TEXT PRIMARY KEY,
    encrypted_profile BLOB NOT NULL,
    updated_at        TEXT NOT NULL
);
"""

_DDL_VAULT_LOG = """
CREATE TABLE IF NOT EXISTS vault_log (
    id          TEXT PRIMARY KEY,
    phantom_id  TEXT,
    action      TEXT NOT NULL,
    details     TEXT,
    timestamp   TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# CredentialVault
# ---------------------------------------------------------------------------


class CredentialVault:
    """Encrypted credential vault for phantom identities.

    Each identity is encrypted with a unique key derived via HKDF from the
    master key and the ``phantom_id``, ensuring per-record isolation.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file (created if it does not exist).
    master_key : bytes
        32-byte master key for the underlying :class:`~phantom.crypto.AESCipher`.

    Example
    -------
    >>> from phantom.crypto import generate_master_key
    >>> vault = CredentialVault(":memory:", generate_master_key())
    >>> vault.store_identity("phx-001", {"name": "Alice", "email": "a@b.c"})
    >>> vault.get_identity("phx-001")
    {'name': 'Alice', 'email': 'a@b.c'}
    """

    _RECORD_INFO: str = "vault-record"
    _PROFILE_INFO: str = "vault-browser-profile"

    def __init__(self, db_path: str, master_key: bytes) -> None:
        self._cipher = AESCipher(master_key)
        self._db_path: str = db_path
        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._create_tables()

    # -- schema bootstrap ---------------------------------------------------

    def _create_tables(self) -> None:
        """Idempotently create the required tables."""
        with self._conn:
            self._conn.execute(_DDL_PHANTOM_IDENTITIES)
            self._conn.execute(_DDL_BROWSER_PROFILES)
            self._conn.execute(_DDL_VAULT_LOG)

    # -- per-record key derivation ------------------------------------------

    def _record_cipher(self, phantom_id: str) -> AESCipher:
        """Return an :class:`AESCipher` keyed for a specific phantom record.

        Key = HKDF(master_key, salt=phantom_id, info='vault-record').
        """
        derived: bytes = self._cipher.derive_key(
            context=phantom_id, info=self._RECORD_INFO
        )
        return AESCipher(derived)

    def _profile_cipher(self, phantom_id: str) -> AESCipher:
        """Return an :class:`AESCipher` keyed for a browser profile blob.

        Key = HKDF(master_key, salt=phantom_id, info='vault-browser-profile').
        """
        derived: bytes = self._cipher.derive_key(
            context=phantom_id, info=self._PROFILE_INFO
        )
        return AESCipher(derived)

    # -- audit logging ------------------------------------------------------

    def _log(self, phantom_id: Optional[str], action: str, details: str = "") -> None:
        """Append an entry to the ``vault_log`` table."""
        self._conn.execute(
            "INSERT INTO vault_log (id, phantom_id, action, details, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid7(), phantom_id, action, details, _now_iso()),
        )

    # -- identity CRUD ------------------------------------------------------

    def store_identity(self, phantom_id: str, identity_data: dict) -> None:
        """Encrypt and store a phantom identity record.

        Parameters
        ----------
        phantom_id : str
            Unique identifier for the phantom (e.g. ``"phx-001"``).
        identity_data : dict
            Arbitrary JSON-serialisable identity payload.

        Raises
        ------
        sqlite3.IntegrityError
            If *phantom_id* already exists.
        """
        cipher = self._record_cipher(phantom_id)
        encrypted: str = cipher.encrypt(
            json.dumps(identity_data, default=str),
            associated_data=phantom_id.encode("utf-8"),
        )
        now = _now_iso()
        donor_id: Optional[str] = identity_data.get("member_donor_id")

        with self._conn:
            self._conn.execute(
                "INSERT INTO phantom_identities "
                "(id, encrypted_data, state, member_donor_id, created_at, updated_at) "
                "VALUES (?, ?, 'active', ?, ?, ?)",
                (phantom_id, encrypted, donor_id, now, now),
            )
            self._log(phantom_id, "store_identity", "Created new identity record")

    def get_identity(self, phantom_id: str) -> Optional[dict]:
        """Decrypt and return a phantom identity record.

        Parameters
        ----------
        phantom_id : str
            The identity to retrieve.

        Returns
        -------
        dict | None
            The decrypted identity payload, or ``None`` if not found.
        """
        row = self._conn.execute(
            "SELECT encrypted_data, state FROM phantom_identities WHERE id = ?",
            (phantom_id,),
        ).fetchone()

        if row is None:
            return None

        if row["state"] == "revoked":
            self._log(phantom_id, "get_identity", "Attempted read on revoked identity")
            return {"_revoked": True, "_phantom_id": phantom_id}

        cipher = self._record_cipher(phantom_id)
        plaintext: str = cipher.decrypt(
            row["encrypted_data"],
            associated_data=phantom_id.encode("utf-8"),
        )
        self._log(phantom_id, "get_identity", "Decrypted identity record")
        return json.loads(plaintext)

    def update_field(self, phantom_id: str, field_path: str, value: Any) -> None:
        """Update a single nested field within an identity record.

        The *field_path* uses **dot notation** (e.g. ``"address.city"``).

        Parameters
        ----------
        phantom_id : str
            The identity to update.
        field_path : str
            Dot-separated path to the field.
        value : Any
            New value (must be JSON-serialisable).

        Raises
        ------
        KeyError
            If the identity does not exist.
        ValueError
            If the identity is revoked.
        """
        identity = self.get_identity(phantom_id)
        if identity is None:
            raise KeyError(f"Identity '{phantom_id}' not found")
        if identity.get("_revoked"):
            raise ValueError(f"Identity '{phantom_id}' is revoked")

        _set_nested(identity, field_path, value)

        cipher = self._record_cipher(phantom_id)
        encrypted: str = cipher.encrypt(
            json.dumps(identity, default=str),
            associated_data=phantom_id.encode("utf-8"),
        )

        with self._conn:
            self._conn.execute(
                "UPDATE phantom_identities SET encrypted_data = ?, updated_at = ? WHERE id = ?",
                (encrypted, _now_iso(), phantom_id),
            )
            self._log(
                phantom_id,
                "update_field",
                f"Updated field '{field_path}'",
            )

    def list_identities(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return metadata for all identities (no secrets).

        Parameters
        ----------
        state : str | None
            If provided, filter to identities with this state
            (``'active'``, ``'revoked'``, …).

        Returns
        -------
        list[dict]
            A list of metadata dictionaries with keys ``id``, ``state``,
            ``member_donor_id``, ``created_at``, ``updated_at``,
            ``revoked_at``, ``revoke_reason``.
        """
        if state is not None:
            rows = self._conn.execute(
                "SELECT id, state, member_donor_id, created_at, updated_at, "
                "revoked_at, revoke_reason FROM phantom_identities WHERE state = ?",
                (state,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, state, member_donor_id, created_at, updated_at, "
                "revoked_at, revoke_reason FROM phantom_identities"
            ).fetchall()

        return [dict(row) for row in rows]

    def revoke_identity(self, phantom_id: str, reason: str) -> None:
        """Mark an identity as revoked and redact its encrypted payload.

        The encrypted data is replaced with a redaction stub so the
        original secrets are no longer recoverable.

        Parameters
        ----------
        phantom_id : str
            The identity to revoke.
        reason : str
            Human-readable revocation reason (stored in plaintext).

        Raises
        ------
        KeyError
            If the identity does not exist.
        """
        row = self._conn.execute(
            "SELECT id FROM phantom_identities WHERE id = ?",
            (phantom_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Identity '{phantom_id}' not found")

        now = _now_iso()
        redacted_stub: str = json.dumps({"_redacted": True, "_reason": reason})

        with self._conn:
            self._conn.execute(
                "UPDATE phantom_identities "
                "SET encrypted_data = ?, state = 'revoked', "
                "    revoked_at = ?, revoke_reason = ?, updated_at = ? "
                "WHERE id = ?",
                (redacted_stub, now, reason, now, phantom_id),
            )
            # Also remove any associated browser profile
            self._conn.execute(
                "DELETE FROM browser_profiles WHERE phantom_id = ?",
                (phantom_id,),
            )
            self._log(phantom_id, "revoke_identity", f"Reason: {reason}")

    # -- browser profiles ---------------------------------------------------

    def store_browser_profile(self, phantom_id: str, profile_data: bytes) -> None:
        """Encrypt and store a binary browser profile.

        Parameters
        ----------
        phantom_id : str
            Associated phantom identity.
        profile_data : bytes
            Raw profile blob (e.g. compressed tarball of a browser profile
            directory).
        """
        import base64 as _b64

        cipher = self._profile_cipher(phantom_id)
        # Encrypt the profile bytes as a base64 string (AESCipher works on str)
        encrypted_token: str = cipher.encrypt(
            _b64.b64encode(profile_data).decode("ascii"),
            associated_data=phantom_id.encode("utf-8"),
        )
        now = _now_iso()

        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO browser_profiles "
                "(phantom_id, encrypted_profile, updated_at) "
                "VALUES (?, ?, ?)",
                (phantom_id, encrypted_token.encode("utf-8"), now),
            )
            self._log(
                phantom_id,
                "store_browser_profile",
                f"Stored {len(profile_data)} bytes",
            )

    def get_browser_profile(self, phantom_id: str) -> Optional[bytes]:
        """Decrypt and return a stored browser profile.

        Parameters
        ----------
        phantom_id : str
            The phantom whose profile to retrieve.

        Returns
        -------
        bytes | None
            Raw profile bytes, or ``None`` if no profile is stored.
        """
        import base64 as _b64

        row = self._conn.execute(
            "SELECT encrypted_profile FROM browser_profiles WHERE phantom_id = ?",
            (phantom_id,),
        ).fetchone()
        if row is None:
            return None

        cipher = self._profile_cipher(phantom_id)
        decrypted_b64: str = cipher.decrypt(
            row["encrypted_profile"].decode("utf-8")
            if isinstance(row["encrypted_profile"], bytes)
            else row["encrypted_profile"],
            associated_data=phantom_id.encode("utf-8"),
        )
        self._log(phantom_id, "get_browser_profile", "Decrypted browser profile")
        return _b64.b64decode(decrypted_b64)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> "CredentialVault":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _set_nested(d: dict, path: str, value: Any) -> None:
    """Set a value in a nested dict using dot-notation *path*.

    Intermediate dicts are created automatically if they do not exist.

    Parameters
    ----------
    d : dict
        The dictionary to mutate.
    path : str
        Dot-separated key path (e.g. ``"address.city"``).
    value : Any
        The value to set at the terminal key.

    Example
    -------
    >>> data = {"a": {"b": 1}}
    >>> _set_nested(data, "a.b", 42)
    >>> data
    {'a': {'b': 42}}
    >>> _set_nested(data, "x.y.z", "new")
    >>> data
    {'a': {'b': 42}, 'x': {'y': {'z': 'new'}}}
    """
    keys = path.split(".")
    current = d
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
