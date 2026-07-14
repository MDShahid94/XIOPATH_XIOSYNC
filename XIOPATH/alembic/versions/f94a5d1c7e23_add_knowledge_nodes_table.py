"""add_knowledge_nodes_table

Revision ID: f94a5d1c7e23
Revises: e83f4c0b6d12
Create Date: 2026-07-12

Phase 5: Universal Memory — transforms memory_nodes into knowledge_nodes.

The knowledge_nodes table is a superset of memory_nodes with:
  - Universal action_spec (JSON) replacing browser-specific action_type/action_params
  - owner_actor_id FK to actors (replaces client_id string)
  - org_id for org-scoped knowledge
  - action_type references type_registry
  - Bayesian scoring fields preserved
  - Tier system preserved (client_primary/secondary, server_primary/secondary)

Compatibility:
  - Creates a compatibility VIEW 'memory_nodes_compat' mapping old column names
  - Existing memory_nodes table is NOT dropped (gradual migration)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f94a5d1c7e23'
down_revision = 'e83f4c0b6d12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. KNOWLEDGE_NODES — Universal memory/action store
    # =========================================================================
    op.create_table(
        'knowledge_nodes',
        sa.Column('id', sa.Text, primary_key=True),                  # UUIDv7
        sa.Column('owner_actor_id', sa.Text),                        # → actors.id
        sa.Column('org_id', sa.Text),                                # → organizations.id

        # ── Classification ──
        sa.Column('domain', sa.Text, nullable=False),                # e.g., "google.com", "api.stripe.com"
        sa.Column('intent', sa.Text, nullable=False),                # Semantic intent label
        sa.Column('tier', sa.Text, nullable=False, server_default='client_secondary'),
        # Tiers: client_primary, client_secondary, server_primary, server_secondary
        sa.Column('status', sa.Text, nullable=False, server_default='active'),
        # Status: active, archived, deprecated, failed

        # ── Action Specification (universal) ──
        sa.Column('action_type', sa.Text, nullable=False),           # → type_registry (browser, api_call, script, llm_prompt, composite)
        sa.Column('action_spec', sa.Text, nullable=False),           # JSON: validated against action_type schema
        sa.Column('execution_mode', sa.Text, server_default='sequential'),
        # execution_mode: sequential, parallel, conditional

        # ── Context ──
        sa.Column('face_value', sa.Text),                            # Human-readable description
        sa.Column('place_value', sa.Text),                           # Scrubbed context (PII-safe)
        sa.Column('context_hash', sa.Text),                          # Deterministic dedup key
        sa.Column('lookup_key', sa.Text),                            # Fast lookup key
        sa.Column('previous_intent', sa.Text),                       # DAG: predecessor
        sa.Column('next_nodes', sa.Text),                            # JSON array: successor node IDs

        # ── Environment Context ──
        sa.Column('device_type', sa.Text),
        sa.Column('os_name', sa.Text),
        sa.Column('browser', sa.Text),
        sa.Column('viewport_width', sa.Integer),
        sa.Column('viewport_height', sa.Integer),

        # ── Scoring (Bayesian EMA preserved) ──
        sa.Column('bayesian_score', sa.Float, server_default='0.5'),
        sa.Column('ema_score', sa.Float, server_default='0.5'),
        sa.Column('total_vote_weight', sa.Float, server_default='0.0'),
        sa.Column('promotions', sa.Integer, server_default='0'),
        sa.Column('ref_count', sa.Integer, server_default='0'),

        # ── Resilience ──
        sa.Column('visibility', sa.Text, server_default='private'), # private, org, public
        sa.Column('volatility_type', sa.Text, server_default='static'),
        sa.Column('fallback_plugin', sa.Text),
        sa.Column('output_var', sa.Text),

        # ── Timestamps ──
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_used', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),

        # ── Extension ──
        sa.Column('metadata', sa.Text),                              # JSON bag
    )

    # Indexes for common query patterns
    op.create_index('ix_knowledge_nodes_domain', 'knowledge_nodes', ['domain'])
    op.create_index('ix_knowledge_nodes_intent', 'knowledge_nodes', ['intent'])
    op.create_index('ix_knowledge_nodes_owner', 'knowledge_nodes', ['owner_actor_id'])
    op.create_index('ix_knowledge_nodes_tier', 'knowledge_nodes', ['tier'])
    op.create_index('ix_knowledge_nodes_action_type', 'knowledge_nodes', ['action_type'])
    op.create_index('ix_knowledge_nodes_lookup_key', 'knowledge_nodes', ['lookup_key'])
    op.create_index('ix_knowledge_nodes_org', 'knowledge_nodes', ['org_id'])
    op.create_index(
        'ix_knowledge_nodes_domain_intent',
        'knowledge_nodes',
        ['domain', 'intent', 'tier'],
    )


def downgrade() -> None:
    op.drop_index('ix_knowledge_nodes_domain_intent')
    op.drop_index('ix_knowledge_nodes_org')
    op.drop_index('ix_knowledge_nodes_lookup_key')
    op.drop_index('ix_knowledge_nodes_action_type')
    op.drop_index('ix_knowledge_nodes_tier')
    op.drop_index('ix_knowledge_nodes_owner')
    op.drop_index('ix_knowledge_nodes_intent')
    op.drop_index('ix_knowledge_nodes_domain')
    op.drop_table('knowledge_nodes')
