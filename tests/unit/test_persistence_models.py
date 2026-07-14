"""Metadata-level invariant checks for the ORM models (docs 03, 06).

These are pure-metadata tests (no database): they enforce the universal row
invariants of doc 06 §4 on every registered model so a future table cannot
silently ship without ``organization_id``, an org index, or a UUID PK.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from xiosync.persistence.models import Base
from xiosync.persistence.models.identity import (
    Actor,
    AuthIdentity,
    Membership,
    Organization,
    Session,
)

EXPECTED_TABLES = {"organizations", "actors", "auth_identities", "memberships", "sessions"}

# organizations IS the tenant root; it carries no organization_id (doc 06 §5).
TENANT_BEARING = EXPECTED_TABLES - {"organizations"}


def _tables() -> dict[str, Table]:
    return dict(Base.metadata.tables)


def test_all_five_identity_tables_registered() -> None:
    assert set(_tables()) == EXPECTED_TABLES


def test_every_table_has_uuid_pk_named_id_with_uuid7_default() -> None:
    for name, table in _tables().items():
        pk_cols = list(table.primary_key.columns)
        assert len(pk_cols) == 1, name
        pk = pk_cols[0]
        assert pk.name == "id", name
        assert isinstance(pk.type, postgresql.UUID), name
        # The Python-side default must be platform/ids.new_id (M6: one vetted
        # UUIDv7 source, no uuid4 fallback).
        assert pk.default is not None, name
        # SQLAlchemy wraps the zero-arg callable to accept an execution
        # context; passing None exercises platform/ids.new_id itself.
        generated = pk.default.arg(None)  # type: ignore[attr-defined]
        assert isinstance(generated, uuid.UUID)
        assert generated.version == 7, name


def test_tenant_tables_have_immutable_org_fk_not_null_and_indexed() -> None:
    for name in TENANT_BEARING:
        table = _tables()[name]
        col = table.columns["organization_id"]
        assert not col.nullable, name  # INV-ROW-1
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "organizations.id" in fk_targets, name
        indexed = any(list(index.columns)[0].name == "organization_id" for index in table.indexes)
        assert indexed, name  # doc 06 §7: org-leading index is mandatory


def test_every_table_has_server_defaulted_created_at() -> None:
    for name, table in _tables().items():
        col = table.columns["created_at"]
        assert not col.nullable, name
        assert col.server_default is not None, name


def test_same_org_composite_fks_present() -> None:
    """INV-TENANT-4 / INV-TABLE-1: cross-org references are structurally banned."""
    tables = _tables()
    composite_fk_names = {
        constraint.name
        for table in tables.values()
        for constraint in table.foreign_key_constraints
        if len(constraint.columns) > 1
    }
    assert {
        "fk_actors_parent_same_org",
        "fk_actors_created_by_same_org",
        "fk_auth_identities_human_actor_same_org",
        "fk_sessions_auth_identity_same_org",
    } <= composite_fk_names


def test_membership_identity_fk_is_deliberately_single_column() -> None:
    """Doc 05 §2: an identity MAY hold memberships in multiple organizations."""
    col = _tables()["memberships"].columns["auth_identity_id"]
    assert {fk.target_fullname for fk in col.foreign_keys} == {"auth_identities.id"}


def test_auth_identity_uniqueness_rules() -> None:
    table = _tables()["auth_identities"]
    unique_sets = {
        tuple(sorted(col.name for col in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("email", "organization_id") in unique_sets  # unique within org
    assert ("human_actor_id",) in unique_sets  # INV-AUTH-1: 1:1 with HumanActor


def test_membership_pair_is_unique() -> None:
    table = _tables()["memberships"]
    unique_sets = {
        tuple(sorted(col.name for col in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("auth_identity_id", "organization_id") in unique_sets


def test_models_importable_via_package_root() -> None:
    for model in (Organization, Actor, AuthIdentity, Membership, Session):
        assert model.__mapper__ is not None
