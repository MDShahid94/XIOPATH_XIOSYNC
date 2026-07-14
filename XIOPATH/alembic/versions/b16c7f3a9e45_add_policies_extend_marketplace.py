"""add_execution_policies_and_extend_marketplace

Revision ID: b16c7f3a9e45
Revises: a05b6e2f8d34
Create Date: 2026-07-12

Phase 7+8: Execution Security & Universal Marketplace.

Phase 7 — New table:
  execution_policies  — Sandboxing rules for workflow execution

Phase 8 — Extensions to marketplace_listings:
  - Add entity_type, version, dependencies, license, policy_id
  - Rename environment_id → entity_id (conceptual, done via new column)
"""
from alembic import op
import sqlalchemy as sa


revision = 'b16c7f3a9e45'
down_revision = 'a05b6e2f8d34'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. EXECUTION_POLICIES — Sandbox rules
    # =========================================================================
    op.create_table(
        'execution_policies',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('name', sa.Text, nullable=False, unique=True),
        sa.Column('description', sa.Text),

        # ── Permissions ──
        sa.Column('allow_network', sa.Boolean, server_default='0'),
        sa.Column('allow_filesystem', sa.Boolean, server_default='0'),
        sa.Column('allow_subprocess', sa.Boolean, server_default='0'),
        sa.Column('allow_browser', sa.Boolean, server_default='1'),
        sa.Column('allow_llm', sa.Boolean, server_default='1'),

        # ── Limits ──
        sa.Column('max_steps', sa.Integer, server_default='100'),
        sa.Column('max_duration_ms', sa.Integer, server_default='600000'),  # 10 min
        sa.Column('max_memory_mb', sa.Integer, server_default='512'),
        sa.Column('max_retries', sa.Integer, server_default='3'),

        # ── Scope ──
        sa.Column('allowed_domains', sa.Text),           # JSON array (NULL = all)
        sa.Column('blocked_domains', sa.Text),            # JSON array
        sa.Column('allowed_action_types', sa.Text),       # JSON array (NULL = all)

        # ── Meta ──
        sa.Column('is_builtin', sa.Boolean, server_default='1'),
        sa.Column('org_id', sa.Text),
        sa.Column('state', sa.Text, server_default='active'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('metadata', sa.Text),
    )

    # Seed 3 default policies
    from datetime import datetime, timezone
    import uuid
    now = datetime.now(timezone.utc).isoformat()

    def _id():
        try:
            return str(uuid.uuid7())
        except AttributeError:
            return str(uuid.uuid4())

    conn = op.get_bind()

    # Policy 1: permissive (for trusted creators)
    conn.execute(sa.text(
        """INSERT INTO execution_policies (id, name, description, allow_network, allow_filesystem, allow_subprocess,
           allow_browser, allow_llm, max_steps, max_duration_ms, is_builtin, state, created_at)
           VALUES (:id, 'permissive', 'Full access for trusted actors', 1, 1, 1, 1, 1, 500, 1800000, 1, 'active', :now)"""
    ), {"id": _id(), "now": now})

    # Policy 2: standard (default)
    conn.execute(sa.text(
        """INSERT INTO execution_policies (id, name, description, allow_network, allow_filesystem, allow_subprocess,
           allow_browser, allow_llm, max_steps, max_duration_ms, is_builtin, state, created_at)
           VALUES (:id, 'standard', 'Standard access for verified actors', 1, 0, 0, 1, 1, 100, 600000, 1, 'active', :now)"""
    ), {"id": _id(), "now": now})

    # Policy 3: marketplace_strict (for installed marketplace items)
    conn.execute(sa.text(
        """INSERT INTO execution_policies (id, name, description, allow_network, allow_filesystem, allow_subprocess,
           allow_browser, allow_llm, max_steps, max_duration_ms, blocked_domains, is_builtin, state, created_at)
           VALUES (:id, 'marketplace_strict', 'Restricted sandbox for marketplace installs', 0, 0, 0, 1, 0,
           50, 300000, :blocked, 1, 'active', :now)"""
    ), {"id": _id(), "now": now, "blocked": '["localhost","127.0.0.1","*.internal"]'})

    # =========================================================================
    # 2. EXTEND MARKETPLACE_LISTINGS
    # =========================================================================
    try:
        op.add_column('marketplace_listings', sa.Column('entity_type', sa.Text, server_default='workflow'))
        op.add_column('marketplace_listings', sa.Column('entity_id', sa.Text))
        op.add_column('marketplace_listings', sa.Column('version', sa.Text, server_default='1.0.0'))
        op.add_column('marketplace_listings', sa.Column('dependencies', sa.Text))
        op.add_column('marketplace_listings', sa.Column('license', sa.Text, server_default='MIT'))
        op.add_column('marketplace_listings', sa.Column('policy_id', sa.Text))
        op.add_column('marketplace_listings', sa.Column('install_count', sa.Integer, server_default='0'))
        op.add_column('marketplace_listings', sa.Column('avg_rating', sa.Float, server_default='0.0'))
        op.create_index('ix_marketplace_entity_type', 'marketplace_listings', ['entity_type'])
    except Exception:
        pass  # Columns may already exist

    # =========================================================================
    # 3. ADD POLICY_ID TO WORKFLOWS
    # =========================================================================
    try:
        op.add_column('workflows', sa.Column('policy_id', sa.Text))
    except Exception:
        pass  # Already added in workflows migration or column exists


def downgrade() -> None:
    try:
        op.drop_column('workflows', 'policy_id')
    except Exception:
        pass

    try:
        op.drop_index('ix_marketplace_entity_type')
        for col in ('entity_type', 'entity_id', 'version', 'dependencies', 'license', 'policy_id', 'install_count', 'avg_rating'):
            op.drop_column('marketplace_listings', col)
    except Exception:
        pass

    op.drop_table('execution_policies')
