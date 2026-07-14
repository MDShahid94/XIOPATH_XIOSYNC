"""
XIOPATH Phantom Infrastructure — Data Models
==============================================
Educational-purpose data models for synthetic identity management,
Google account representation, service credentials, and phantom identity
lifecycle tracking.

All models use Python dataclasses with full type hints.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
import time
import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
# NOTE: PhantomState and TrustTier are DEPRECATED in favor of canonical
# constants in core.ontology_models (LIFECYCLE_STATES, AGENT_SUBTYPES).
# They are kept here for backward compatibility with existing code.
# Use phantom.ontology_bridge.PHANTOM_STATE_MAP for state translation.
# ---------------------------------------------------------------------------

class PhantomState(Enum):
    """
    Lifecycle states for a phantom identity.

    DEPRECATED: Use LIFECYCLE_STATES from core.ontology_models instead.
    Mapping: provisioning→provisioning, aging→aging, active→active,
    locked→locked, recovering→recovering, dead→terminated, revoked→archived.
    """

    PROVISIONING = "provisioning"
    AGING = "aging"
    ACTIVE = "active"
    LOCKED = "locked"
    RECOVERING = "recovering"
    DEAD = "dead"
    REVOKED = "revoked"


class ServiceState(Enum):
    """Operational states for an external service credential."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEAD = "dead"


class TrustTier(Enum):
    """
    Trust classification tiers for mesh participants.

    DEPRECATED: The canonical trust_tier field is stored directly as a
    string on mesh_nodes in the D1 Control Plane schema. Values are
    identical: newcomer, contributor, trusted, core, admin.
    """

    NEWCOMER = "newcomer"
    CONTRIBUTOR = "contributor"
    TRUSTED = "trusted"
    CORE = "core"
    ADMIN = "admin"


# Backward-compatible mapping: PhantomState → (ontology_state, ontology_phase)
PHANTOM_STATE_TO_ONTOLOGY = {
    PhantomState.PROVISIONING: ("provisioning", "birth"),
    PhantomState.AGING:        ("aging", "birth"),
    PhantomState.ACTIVE:       ("active", "operational"),
    PhantomState.LOCKED:       ("locked", "operational"),
    PhantomState.RECOVERING:   ("recovering", "operational"),
    PhantomState.DEAD:         ("terminated", "end_of_life"),
    PhantomState.REVOKED:      ("archived", "end_of_life"),
}


# ---------------------------------------------------------------------------
# SyntheticIdentity
# ---------------------------------------------------------------------------

@dataclass
class SyntheticIdentity:
    """Represents a fully-fabricated human identity used for phantom accounts.

    Attributes:
        first_name: Given name of the synthetic persona.
        last_name: Family name of the synthetic persona.
        dob: Date of birth as an ISO-8601 date string (YYYY-MM-DD).
        gender: Gender identifier (e.g. 'male', 'female', 'non-binary').
        email: Primary email address assigned to this identity.
        username: Preferred username / handle.
        password: Cleartext password (stored encrypted at rest in production).
        locale: IETF language tag (e.g. 'en-US').
        timezone: IANA timezone name (e.g. 'America/New_York').
        profile_picture_url: Optional URL pointing to an avatar image.
    """

    first_name: str
    last_name: str
    dob: str
    gender: str
    email: str
    username: str
    password: str
    locale: str
    timezone: str
    profile_picture_url: Optional[str] = None


# ---------------------------------------------------------------------------
# TOTPSeed
# ---------------------------------------------------------------------------

@dataclass
class TOTPSeed:
    """Encapsulates the seed material required for TOTP code generation.

    The ``generate_code`` method is a self-contained, inline TOTP
    implementation using only the Python standard library (hmac, hashlib,
    struct).

    Attributes:
        secret: Base32-encoded shared secret.
        issuer: Issuer label shown in authenticator apps.
        algorithm: Hash algorithm name ('SHA1', 'SHA256', 'SHA512').
        digits: Number of digits in the generated code (typically 6 or 8).
        period: Time-step duration in seconds (default 30).
    """

    secret: str
    issuer: str = "XIOPATH"
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30

    def generate_code(self) -> str:
        """Generate a TOTP code for the current time.

        Uses an inline HMAC-based OTP implementation with no external
        dependencies beyond the Python standard library.

        Returns:
            A zero-padded string of ``self.digits`` length representing the
            current TOTP code.
        """
        # Decode the base32 secret, tolerating missing padding
        secret_bytes = base64.b32decode(
            self.secret.upper() + "=" * ((8 - len(self.secret) % 8) % 8)
        )

        # Compute the time counter
        counter = int(time.time()) // self.period

        # Pack counter as big-endian unsigned 64-bit integer
        counter_bytes = struct.pack(">Q", counter)

        # Select the hash algorithm
        algo_map = {
            "SHA1": hashlib.sha1,
            "SHA256": hashlib.sha256,
            "SHA512": hashlib.sha512,
        }
        hash_func = algo_map.get(self.algorithm.upper(), hashlib.sha1)

        # Compute HMAC
        hmac_digest = hmac.new(secret_bytes, counter_bytes, hash_func).digest()

        # Dynamic truncation (RFC 4226 §5.4)
        offset = hmac_digest[-1] & 0x0F
        truncated = struct.unpack(">I", hmac_digest[offset : offset + 4])[0]
        truncated &= 0x7FFFFFFF

        # Modular reduction to the desired number of digits
        code = truncated % (10 ** self.digits)
        return str(code).zfill(self.digits)


# ---------------------------------------------------------------------------
# GoogleAccount
# ---------------------------------------------------------------------------

@dataclass
class GoogleAccount:
    """Represents a Google account bound to a phantom identity.

    Attributes:
        email: Google account email address.
        password: Account password.
        totp_seed: TOTP seed for 2FA on this account.
        backup_codes: List of single-use backup verification codes.
        recovery_phone: Phone number registered for account recovery.
        recovery_email: Alternate email for account recovery.
        session_state: Opaque string describing current session status
            (e.g. 'authenticated', 'expired', 'challenged').
        browser_profile_key: Optional key linking to a browser profile
            directory for session persistence.
    """

    email: str
    password: str
    totp_seed: TOTPSeed
    backup_codes: list[str]
    recovery_phone: str
    recovery_email: str
    session_state: str
    browser_profile_key: Optional[str] = None


# ---------------------------------------------------------------------------
# ServiceCredential
# ---------------------------------------------------------------------------

@dataclass
class ServiceCredential:
    """Credential set for an external service linked to a phantom identity.

    Attributes:
        service_name: Canonical name of the external service.
        account_id: Service-specific account identifier.
        api_token: Bearer / API token for programmatic access.
        username: Optional service username if different from account_id.
        extra_data: Arbitrary key-value metadata for service-specific fields.
        state: Current operational state of this credential.
    """

    service_name: str
    account_id: str
    api_token: str
    username: Optional[str] = None
    extra_data: dict = field(default_factory=dict)
    state: ServiceState = ServiceState.PENDING


# ---------------------------------------------------------------------------
# PhantomIdentity
# ---------------------------------------------------------------------------

@dataclass
class PhantomIdentity:
    """Top-level aggregate representing a complete phantom identity.

    Combines a synthetic persona, a Google account, zero or more external
    service credentials, and mesh/trust metadata into a single cohesive
    entity with full lifecycle tracking.

    Attributes:
        id: Unique identifier for this phantom (UUID string).
        member_donor_id: Identifier linking to the originating member/donor.
        synthetic: The fabricated human identity details.
        google: Associated Google account and 2FA material.
        services: Mapping of service name → credential for linked services.
        mesh_node_id: Optional identifier within the XIOPATH mesh network.
        trust_score: Numeric trust score (0.0–1.0) derived from behaviour.
        state: Current lifecycle state of the phantom identity.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
    """

    id: str
    member_donor_id: str
    synthetic: SyntheticIdentity
    google: GoogleAccount
    services: dict[str, ServiceCredential] = field(default_factory=dict)
    mesh_node_id: Optional[str] = None
    trust_score: float = 0.0
    state: PhantomState = PhantomState.PROVISIONING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the entire phantom identity tree to a plain dictionary.

        All nested dataclasses, enums, and collections are recursively
        converted so the result is JSON-serializable.

        Returns:
            A ``dict`` suitable for ``json.dumps()``.
        """
        return {
            "id": self.id,
            "member_donor_id": self.member_donor_id,
            "synthetic": {
                "first_name": self.synthetic.first_name,
                "last_name": self.synthetic.last_name,
                "dob": self.synthetic.dob,
                "gender": self.synthetic.gender,
                "email": self.synthetic.email,
                "username": self.synthetic.username,
                "password": self.synthetic.password,
                "locale": self.synthetic.locale,
                "timezone": self.synthetic.timezone,
                "profile_picture_url": self.synthetic.profile_picture_url,
            },
            "google": {
                "email": self.google.email,
                "password": self.google.password,
                "totp_seed": {
                    "secret": self.google.totp_seed.secret,
                    "issuer": self.google.totp_seed.issuer,
                    "algorithm": self.google.totp_seed.algorithm,
                    "digits": self.google.totp_seed.digits,
                    "period": self.google.totp_seed.period,
                },
                "backup_codes": list(self.google.backup_codes),
                "recovery_phone": self.google.recovery_phone,
                "recovery_email": self.google.recovery_email,
                "session_state": self.google.session_state,
                "browser_profile_key": self.google.browser_profile_key,
            },
            "services": {
                name: {
                    "service_name": cred.service_name,
                    "account_id": cred.account_id,
                    "api_token": cred.api_token,
                    "username": cred.username,
                    "extra_data": dict(cred.extra_data),
                    "state": cred.state.value,
                }
                for name, cred in self.services.items()
            },
            "mesh_node_id": self.mesh_node_id,
            "trust_score": self.trust_score,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PhantomIdentity:
        """Deserialize a plain dictionary into a fully-typed PhantomIdentity.

        Performs recursive reconstruction of all nested dataclasses and
        enums from their serialized representations.

        Args:
            data: Dictionary previously produced by ``to_dict()`` or an
                equivalent JSON structure.

        Returns:
            A fully-hydrated ``PhantomIdentity`` instance.
        """
        syn_data = data["synthetic"]
        synthetic = SyntheticIdentity(
            first_name=syn_data["first_name"],
            last_name=syn_data["last_name"],
            dob=syn_data["dob"],
            gender=syn_data["gender"],
            email=syn_data["email"],
            username=syn_data["username"],
            password=syn_data["password"],
            locale=syn_data["locale"],
            timezone=syn_data["timezone"],
            profile_picture_url=syn_data.get("profile_picture_url"),
        )

        g_data = data["google"]
        ts_data = g_data["totp_seed"]
        totp_seed = TOTPSeed(
            secret=ts_data["secret"],
            issuer=ts_data.get("issuer", "XIOPATH"),
            algorithm=ts_data.get("algorithm", "SHA1"),
            digits=ts_data.get("digits", 6),
            period=ts_data.get("period", 30),
        )

        google = GoogleAccount(
            email=g_data["email"],
            password=g_data["password"],
            totp_seed=totp_seed,
            backup_codes=list(g_data.get("backup_codes", [])),
            recovery_phone=g_data.get("recovery_phone", ""),
            recovery_email=g_data.get("recovery_email", ""),
            session_state=g_data.get("session_state", "unknown"),
            browser_profile_key=g_data.get("browser_profile_key"),
        )

        services: dict[str, ServiceCredential] = {}
        for name, svc_data in data.get("services", {}).items():
            services[name] = ServiceCredential(
                service_name=svc_data["service_name"],
                account_id=svc_data["account_id"],
                api_token=svc_data["api_token"],
                username=svc_data.get("username"),
                extra_data=dict(svc_data.get("extra_data", {})),
                state=ServiceState(svc_data.get("state", "pending")),
            )

        return cls(
            id=data["id"],
            member_donor_id=data["member_donor_id"],
            synthetic=synthetic,
            google=google,
            services=services,
            mesh_node_id=data.get("mesh_node_id"),
            trust_score=float(data.get("trust_score", 0.0)),
            state=PhantomState(data.get("state", "provisioning")),
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
            updated_at=data.get(
                "updated_at", datetime.now(timezone.utc).isoformat()
            ),
        )
