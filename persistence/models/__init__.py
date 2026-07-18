"""ORM models — the metadata the migration chain is checked against.

Importing this package registers every model on ``Base.metadata`` so the
autogenerate-drift gate (INV-TEST-SCHEMA-2) sees the whole schema. Every new
model module MUST be imported here.
"""

from __future__ import annotations

from xiosync.persistence.models.authorization import Capability, Event, Grant
from xiosync.persistence.models.base import Base
from xiosync.persistence.models.identity import (
    Actor,
    AuthIdentity,
    Membership,
    Organization,
    Session,
)
from xiosync.persistence.models.ontology import (
    Edge,
    Memory,
    TypeRegistry,
    TypeRegistryAlias,
)
from xiosync.persistence.models.operations import Operation

__all__ = [
    "Actor",
    "AuthIdentity",
    "Base",
    "Capability",
    "Edge",
    "Event",
    "Grant",
    "Membership",
    "Memory",
    "Operation",
    "Organization",
    "Session",
    "TypeRegistry",
    "TypeRegistryAlias",
]
