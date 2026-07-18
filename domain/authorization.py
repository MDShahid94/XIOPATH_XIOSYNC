"""Pure, fail-closed capability authorization policy (doc 05 §4)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

TRUST_ORDER = {"newcomer": 0, "contributor": 1, "trusted": 2, "core": 3, "admin": 4}
SUPPORTED_CONSTRAINTS = {
    "operations",
    "resource_types",
    "resource_ids",
    "arguments",
    "minimum_trust_tier",
    "not_before",
    "not_after",
    "rate",
}


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID
    organization_id: uuid.UUID
    state: str
    trust_tier: str


@dataclass(frozen=True)
class Organization:
    id: uuid.UUID
    state: str


@dataclass(frozen=True)
class Resource:
    type: str
    id: uuid.UUID
    organization_id: uuid.UUID


@dataclass(frozen=True)
class Grant:
    id: uuid.UUID
    organization_id: uuid.UUID
    actor_id: uuid.UUID
    capability: str
    state: str
    constraints: Mapping[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    decision_id: uuid.UUID
    reason: str
    grant_id: uuid.UUID | None = None


RateChecker = Callable[[Mapping[str, Any]], bool]


def _deny(reason: str, grant_id: uuid.UUID | None = None) -> Decision:
    return Decision(False, uuid.uuid4(), reason, grant_id)


def _constraints_allow(
    grant: Grant,
    actor: Actor,
    resource: Resource,
    operation: str,
    arguments: Mapping[str, Any],
    now: datetime,
    rate_checker: RateChecker | None,
) -> bool:
    constraints = grant.constraints
    if not isinstance(constraints, Mapping) or set(constraints) - SUPPORTED_CONSTRAINTS:
        return False
    operations = constraints.get("operations")
    if operations is not None and (not isinstance(operations, list) or operation not in operations):
        return False
    resource_types = constraints.get("resource_types")
    if resource_types is not None and (
        not isinstance(resource_types, list) or resource.type not in resource_types
    ):
        return False
    resource_ids = constraints.get("resource_ids")
    if resource_ids is not None and (
        not isinstance(resource_ids, list) or str(resource.id) not in resource_ids
    ):
        return False
    minimum = constraints.get("minimum_trust_tier")
    if minimum is not None and (
        minimum not in TRUST_ORDER
        or actor.trust_tier not in TRUST_ORDER
        or TRUST_ORDER[actor.trust_tier] < TRUST_ORDER[minimum]
    ):
        return False
    not_before = constraints.get("not_before")
    not_after = constraints.get("not_after")
    try:
        if not_before is not None and now < datetime.fromisoformat(not_before):
            return False
        if not_after is not None and now >= datetime.fromisoformat(not_after):
            return False
    except (TypeError, ValueError):
        return False
    expected_arguments = constraints.get("arguments")
    if expected_arguments is not None:
        if not isinstance(expected_arguments, Mapping):
            return False
        for name, allowed in expected_arguments.items():
            if (
                not isinstance(allowed, list)
                or name not in arguments
                or arguments[name] not in allowed
            ):
                return False
    rate = constraints.get("rate")
    if rate is not None:
        if not isinstance(rate, Mapping) or rate_checker is None or not rate_checker(rate):
            return False
    return True


def authorize(
    *,
    requested_organization_id: uuid.UUID,
    actor: Actor | None,
    organization: Organization | None,
    resource: Resource,
    capability: str,
    operation: str,
    grants: Sequence[Grant],
    arguments: Mapping[str, Any],
    now: datetime,
    rate_checker: RateChecker | None = None,
) -> Decision:
    """Evaluate in the normative order and deny on every unknown/error path."""
    try:
        if (
            actor is None
            or actor.organization_id != requested_organization_id
            or actor.state != "active"
        ):
            return _deny("actor_invalid")
        if resource.organization_id != requested_organization_id:
            return _deny("resource_ownership_mismatch")
        if (
            organization is None
            or organization.id != requested_organization_id
            or organization.state != "active"
        ):
            return _deny("organization_inactive")
        candidates = [
            grant
            for grant in grants
            if grant.organization_id == requested_organization_id
            and grant.actor_id == actor.id
            and grant.capability == capability
            and grant.state == "active"
            and (grant.expires_at is None or grant.expires_at > now)
        ]
        if not candidates:
            return _deny("grant_missing")
        for grant in candidates:
            if _constraints_allow(grant, actor, resource, operation, arguments, now, rate_checker):
                return Decision(True, uuid.uuid4(), "allowed", grant.id)
        return _deny("constraints_unsatisfied")
    except Exception:
        return _deny("policy_evaluation_failed")
