"""add_type_registry_table

Revision ID: c61f2a8b4e90
Revises: b50a0c7e3d12
Create Date: 2026-07-12

Phase 2: Creates the type_registry table — the database-backed replacement
for all hardcoded type constants (ACTOR_TYPES, EDGE_TYPES, OPERATION_TYPES,
LIFECYCLE_STATES, EVENT_TYPES, etc.).

This table enables runtime extensibility: creators can register custom types
(e.g., new actor subtypes, edge types, action types) without code changes.

Columns:
  - id:           UUIDv7 primary key
  - category:     Type category (actor_type, actor_subtype, edge_type, operation_type,
                  lifecycle_state, lifecycle_phase, event_type, severity, capability_type,
                  action_type)
  - name:         The type name (e.g., "human", "browser", "manages")
  - parent_name:  For hierarchical types (e.g., subtype "admin" has parent "human")
  - display_name: Human-readable label
  - description:  Longer explanation
  - schema:       JSON Schema for validation (used by action_type specs)
  - is_builtin:   True for system-defined types, False for user-created
  - org_id:       NULL = global, non-NULL = org-scoped (Phase 4)
  - state:        active | deprecated | archived
  - sort_order:   For deterministic UI ordering
  - created_at:   Timestamp
  - created_by:   Actor ID of creator
  - metadata:     JSON bag for extensibility
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c61f2a8b4e90'
down_revision = 'b50a0c7e3d12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'type_registry',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('category', sa.Text, nullable=False),       # actor_type, edge_type, etc.
        sa.Column('name', sa.Text, nullable=False),            # "human", "manages", etc.
        sa.Column('parent_name', sa.Text),                     # For subtypes: parent type name
        sa.Column('display_name', sa.Text),                    # "Human Actor"
        sa.Column('description', sa.Text),                     # Longer explanation
        sa.Column('schema', sa.Text),                          # JSON Schema for action_type validation
        sa.Column('is_builtin', sa.Boolean, server_default='1'),
        sa.Column('org_id', sa.Text),                          # NULL = global (Phase 4: org-scoped)
        sa.Column('state', sa.Text, server_default='active'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('created_by', sa.Text),
        sa.Column('metadata', sa.Text),                        # JSON extension bag
    )

    # Unique constraint: (category, name, org_id) — prevents duplicate types within scope
    op.create_index(
        'ix_type_registry_category_name_org',
        'type_registry',
        ['category', 'name', 'org_id'],
        unique=True,
    )

    # Fast lookup by category
    op.create_index(
        'ix_type_registry_category',
        'type_registry',
        ['category'],
    )


def downgrade() -> None:
    op.drop_index('ix_type_registry_category')
    op.drop_index('ix_type_registry_category_name_org')
    op.drop_table('type_registry')
