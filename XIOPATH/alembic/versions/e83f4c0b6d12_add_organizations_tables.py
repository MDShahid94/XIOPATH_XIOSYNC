"""add_organizations_tables

Revision ID: e83f4c0b6d12
Revises: d72e3b9a5c01
Create Date: 2026-07-12

Phase 4: Organizations — multi-tenant org layer.

New tables:
  1. organizations    — Org entity (name, billing, plan, limits)
  2. org_memberships  — Actor↔Org many-to-many with role

Also:
  - Adds org_id FK to actors table
  - org_id already exists on type_registry (prep from Phase 2)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e83f4c0b6d12'
down_revision = 'd72e3b9a5c01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. ORGANIZATIONS
    # =========================================================================
    op.create_table(
        'organizations',
        sa.Column('id', sa.Text, primary_key=True),              # UUIDv7
        sa.Column('name', sa.Text, nullable=False, unique=True),
        sa.Column('display_name', sa.Text),
        sa.Column('slug', sa.Text, unique=True),                  # URL-safe identifier
        sa.Column('plan', sa.Text, server_default='free'),        # free | pro | enterprise
        sa.Column('state', sa.Text, server_default='active'),     # active | suspended | archived
        sa.Column('owner_actor_id', sa.Text),                     # → actors.id (org creator)
        sa.Column('max_actors', sa.Integer, server_default='50'),
        sa.Column('max_custom_types', sa.Integer, server_default='100'),
        sa.Column('max_knowledge_nodes', sa.Integer, server_default='10000'),
        sa.Column('billing_email', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('metadata', sa.Text),                           # JSON extension
    )

    # =========================================================================
    # 2. ORG_MEMBERSHIPS
    # =========================================================================
    op.create_table(
        'org_memberships',
        sa.Column('id', sa.Text, primary_key=True),              # UUIDv7
        sa.Column('org_id', sa.Text, nullable=False),             # → organizations.id
        sa.Column('actor_id', sa.Text, nullable=False),           # → actors.id
        sa.Column('role', sa.Text, nullable=False, server_default='member'),
        # role: "owner" | "admin" | "member" | "viewer"
        sa.Column('state', sa.Text, server_default='active'),     # active | invited | suspended
        sa.Column('invited_by', sa.Text),                         # → actors.id
        sa.Column('joined_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('metadata', sa.Text),                           # JSON extension
    )

    op.create_index('ix_org_memberships_org_id', 'org_memberships', ['org_id'])
    op.create_index('ix_org_memberships_actor_id', 'org_memberships', ['actor_id'])
    op.create_index(
        'ix_org_memberships_unique',
        'org_memberships',
        ['org_id', 'actor_id'],
        unique=True,
    )

    # =========================================================================
    # 3. Add org_id to actors
    # =========================================================================
    # The default org for an actor (their primary org)
    try:
        op.add_column('actors', sa.Column('org_id', sa.Text))
        op.create_index('ix_actors_org_id', 'actors', ['org_id'])
    except Exception:
        pass  # Column may already exist


def downgrade() -> None:
    try:
        op.drop_index('ix_actors_org_id')
        op.drop_column('actors', 'org_id')
    except Exception:
        pass

    op.drop_index('ix_org_memberships_unique')
    op.drop_index('ix_org_memberships_actor_id')
    op.drop_index('ix_org_memberships_org_id')
    op.drop_table('org_memberships')
    op.drop_table('organizations')
