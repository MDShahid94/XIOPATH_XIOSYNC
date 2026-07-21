"""Worker-enrollment & credential use cases (doc 07 §2; Phase 4).

``WorkerService`` is the sanctioned entry point for the worker-enrollment
lifecycle and short-lived credential issuance.  It will enforce:

* **INV-WORKER-CRED-2 — enrollment token is hashed on receipt; the plaintext
  is never stored.**  ``register_worker`` receives the raw token, hashes it,
  and stores only the hash.
* **INV-WORKER-CRED-1 — credentials are short-lived, capability-scoped, and
  individually revocable.**  ``issue_credential`` mints a new row with a
  caller-supplied ``duration`` and ``scoped_capabilities`` list;
  ``revoke_credential`` sets ``revoked_at`` immediately.

All methods are **stubs** in Phase 4 Step 1.  They carry precise docstrings
and typed signatures so callers, integration tests, and the static-analysis
gate can be written against them before the implementations land in Step 2.
Each stub raises ``NotImplementedError`` so any premature call is caught
loudly.

The service follows the ``WorkflowService`` shape: it takes the caller's
``Session`` (the caller owns the transaction via ``org_scoped_session``),
flushes writes within it, and returns frozen dataclass values so the service
holds no live ORM state.  ``organization_id`` always comes from the context,
never from the caller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from xiosync.domain.context import OrgContext

__all__ = [
    "CredentialNotFoundError",
    "EnrollmentNotFoundError",
    "InactiveWorkerError",
    "InvalidEnrollmentTokenError",
    "WorkerAlreadyEnrolledError",
    "WorkerCredentialRecord",
    "WorkerEnrollmentRecord",
    "WorkerService",
]


# ---------------------------------------------------------------------------
# Read-model dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerEnrollmentRecord:
    """Frozen snapshot of a ``worker_enrollments`` row."""

    id: uuid.UUID
    organization_id: uuid.UUID
    worker_id: uuid.UUID
    enrollment_state: str
    pool_type: str
    public_key: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class WorkerCredentialRecord:
    """Frozen snapshot of a ``worker_credentials`` row."""

    id: uuid.UUID
    organization_id: uuid.UUID
    enrollment_id: uuid.UUID
    scoped_capabilities: list[Any]
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class EnrollmentNotFoundError(ValueError):
    """Raised when the requested enrollment row does not exist in the org."""


class WorkerAlreadyEnrolledError(ValueError):
    """Raised when a worker already has an enrollment record in the org.

    INV-WORKER-ENROLL-1: one enrollment per worker per org is enforced by the
    ``uq_worker_enrollments_org_worker`` unique constraint; this error surfaces
    the constraint violation as a domain error before hitting the DB.
    """


class InvalidEnrollmentTokenError(ValueError):
    """Raised when the supplied enrollment token does not match the stored hash."""


class CredentialNotFoundError(ValueError):
    """Raised when the requested credential row does not exist in the org."""


class InactiveWorkerError(ValueError):
    """Raised when an operation requires an approved worker but the enrollment
    is in state ``pending``, ``suspended``, or ``revoked``."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class WorkerService:
    """Use-cases for worker enrollment and credential lifecycle (doc 07 §2).

    Instantiate with the caller's ``Session``; the caller owns the transaction
    boundary via ``org_scoped_session``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Enrollment lifecycle
    # ------------------------------------------------------------------

    def register_worker(
        self,
        ctx: OrgContext,
        *,
        enrollment_token: str,
        public_key: str,
    ) -> WorkerEnrollmentRecord:
        """Register a worker by hashing its one-time enrollment token.

        Creates a ``pending`` enrollment row in the worker's org.  The raw
        token is never stored; only its hash is persisted (INV-WORKER-CRED-2).
        The ``worker_id`` is resolved from the token's embedded claims at
        implementation time.

        Raises:
            InvalidEnrollmentTokenError: if the token is malformed or not
                associated with a known worker actor in this org.
            WorkerAlreadyEnrolledError: if an enrollment already exists for
                the resolved worker in this org.
        """
        raise NotImplementedError

    def approve_worker(
        self,
        ctx: OrgContext,
        enrollment_id: uuid.UUID,
        *,
        approved_by: uuid.UUID,
    ) -> WorkerEnrollmentRecord:
        """Approve a pending enrollment: ``pending`` → ``approved``.

        For ``managed`` pool workers the platform operator auto-approves; for
        ``volunteer`` pool workers explicit operator/org-admin action is
        required.  Sets ``approved_by`` and ``approved_at`` on the row.

        Raises:
            EnrollmentNotFoundError: if ``enrollment_id`` does not exist in
                this org.
            ValueError: if the enrollment is not in state ``pending``.
        """
        raise NotImplementedError

    def suspend_worker(
        self,
        ctx: OrgContext,
        enrollment_id: uuid.UUID,
    ) -> WorkerEnrollmentRecord:
        """Suspend an approved worker: ``approved`` → ``suspended``.

        A suspended worker may not receive new credentials or lease tasks.
        Existing active credentials are not automatically revoked here; the
        caller should revoke them separately.

        Raises:
            EnrollmentNotFoundError: if ``enrollment_id`` does not exist.
            ValueError: if the enrollment is not in state ``approved``.
        """
        raise NotImplementedError

    def revoke_worker(
        self,
        ctx: OrgContext,
        enrollment_id: uuid.UUID,
    ) -> WorkerEnrollmentRecord:
        """Permanently revoke a worker: any state → ``revoked``.

        Revocation is immediate and irreversible.  All active credentials for
        this enrollment should be revoked by the caller before or after this
        call (implementation may cascade this in Step 2).

        Raises:
            EnrollmentNotFoundError: if ``enrollment_id`` does not exist.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Credential lifecycle
    # ------------------------------------------------------------------

    def issue_credential(
        self,
        ctx: OrgContext,
        enrollment_id: uuid.UUID,
        *,
        scoped_capabilities: list[Any],
        duration: timedelta,
        now: datetime,
    ) -> WorkerCredentialRecord:
        """Mint a new short-lived, capability-scoped credential.

        Creates a ``worker_credentials`` row with ``expires_at = now +
        duration`` and ``revoked_at = None``.  The capability list is stored
        as JSONB; it is the caller's responsibility to pass valid capability
        UUIDs that the worker is authorised to use.

        INV-WORKER-CRED-1: credentials are always short-lived (``duration``
        bounded by policy) and scoped to a non-empty capability set.

        Raises:
            EnrollmentNotFoundError: if ``enrollment_id`` does not exist.
            InactiveWorkerError: if the enrollment is not in state
                ``approved``.
        """
        raise NotImplementedError

    def revoke_credential(
        self,
        ctx: OrgContext,
        credential_id: uuid.UUID,
    ) -> None:
        """Revoke a credential immediately by setting ``revoked_at = now()``.

        INV-WORKER-CRED-1: credentials are individually revocable; revocation
        is an additive write (the row is never deleted).

        Raises:
            CredentialNotFoundError: if ``credential_id`` does not exist in
                this org.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_enrollment(
        self,
        ctx: OrgContext,
        enrollment_id: uuid.UUID,
    ) -> WorkerEnrollmentRecord | None:
        """Return the enrollment record or ``None`` if not found in this org."""
        raise NotImplementedError

    def get_credential(
        self,
        ctx: OrgContext,
        credential_id: uuid.UUID,
    ) -> WorkerCredentialRecord | None:
        """Return the credential record or ``None`` if not found in this org."""
        raise NotImplementedError
