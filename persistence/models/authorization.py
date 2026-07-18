"""Capability, grant, and append-only authorization event models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from xiosync.persistence.models.base import Base
from xiosync.platform.ids import new_id

_ts = TIMESTAMP(timezone=True)


class Capability(Base):
    __tablename__ = "capabilities"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_ts, nullable=False, server_default=text("now()"))


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["actors.organization_id", "actors.id"],
            name="fk_grants_actor_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "capability_id"],
            ["capabilities.organization_id", "capabilities.id"],
            name="fk_grants_capability_same_org",
        ),
        CheckConstraint("state IN ('active', 'revoked')", name="state_allowed"),
        Index(
            "ix_grants_actor_capability_active",
            "organization_id",
            "actor_id",
            "capability_id",
            postgresql_where=text("state = 'active'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    capability_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    expires_at: Mapped[datetime | None] = mapped_column(_ts)
    created_at: Mapped[datetime] = mapped_column(_ts, nullable=False, server_default=text("now()"))
    revoked_at: Mapped[datetime | None] = mapped_column(_ts)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_org_type_created", "organization_id", "event_type", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(_ts, nullable=False, server_default=text("now()"))
