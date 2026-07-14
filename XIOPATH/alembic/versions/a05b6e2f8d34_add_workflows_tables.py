"""add_workflows_tables

Revision ID: a05b6e2f8d34
Revises: f94a5d1c7e23
Create Date: 2026-07-12

Phase 6: Persistent Workflows.

New tables:
  1. workflows           — Workflow definitions (reusable, shareable)
  2. workflow_executions  — Execution instances with full state tracking

A workflow is a named, versioned sequence of knowledge_node actions
that can be shared via the marketplace, forked, and executed by any actor.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a05b6e2f8d34'
down_revision = 'f94a5d1c7e23'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. WORKFLOWS — Reusable workflow definitions
    # =========================================================================
    op.create_table(
        'workflows',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('version', sa.Text, server_default='1.0.0'),

        # ── Ownership ──
        sa.Column('creator_id', sa.Text, nullable=False),       # → actors.id
        sa.Column('org_id', sa.Text),                            # → organizations.id

        # ── Definition ──
        sa.Column('steps', sa.Text, nullable=False),             # JSON array of step definitions
        # Each step: { "order": 1, "knowledge_node_id": "...", "action_type": "browser",
        #              "action_spec": {...}, "condition": "...", "on_failure": "abort|skip|retry",
        #              "timeout_ms": 30000, "retries": 0 }
        sa.Column('input_schema', sa.Text),                      # JSON Schema for workflow inputs
        sa.Column('output_schema', sa.Text),                     # JSON Schema for workflow outputs
        sa.Column('trigger_type', sa.Text, server_default='manual'),
        # trigger_type: manual, scheduled, webhook, event
        sa.Column('trigger_config', sa.Text),                    # JSON: cron expression, webhook URL, etc.

        # ── Settings ──
        sa.Column('execution_mode', sa.Text, server_default='sequential'),
        # sequential, parallel, conditional
        sa.Column('max_retries', sa.Integer, server_default='0'),
        sa.Column('timeout_ms', sa.Integer, server_default='300000'),  # 5 min default
        sa.Column('policy_id', sa.Text),                         # → execution_policies.id (Phase 7)

        # ── State ──
        sa.Column('state', sa.Text, server_default='draft'),
        # draft, active, paused, deprecated, archived
        sa.Column('visibility', sa.Text, server_default='private'),
        # private, org, public
        sa.Column('tags', sa.Text),                              # JSON array of tags
        sa.Column('total_executions', sa.Integer, server_default='0'),
        sa.Column('success_rate', sa.Float, server_default='0.0'),

        # ── Timestamps ──
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('metadata', sa.Text),
    )

    op.create_index('ix_workflows_creator', 'workflows', ['creator_id'])
    op.create_index('ix_workflows_org', 'workflows', ['org_id'])
    op.create_index('ix_workflows_state', 'workflows', ['state'])

    # =========================================================================
    # 2. WORKFLOW_EXECUTIONS — Execution instances
    # =========================================================================
    op.create_table(
        'workflow_executions',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('workflow_id', sa.Text, nullable=False),       # → workflows.id
        sa.Column('executor_id', sa.Text, nullable=False),       # → actors.id (who ran it)
        sa.Column('org_id', sa.Text),

        # ── Execution State ──
        sa.Column('status', sa.Text, nullable=False, server_default='pending'),
        # pending, running, paused, completed, failed, cancelled, timed_out
        sa.Column('current_step', sa.Integer, server_default='0'),
        sa.Column('total_steps', sa.Integer, server_default='0'),

        # ── I/O ──
        sa.Column('input_data', sa.Text),                        # JSON: workflow input params
        sa.Column('output_data', sa.Text),                       # JSON: workflow output/result
        sa.Column('step_results', sa.Text),                      # JSON array: per-step results
        sa.Column('error', sa.Text),                             # Error message if failed

        # ── Timing ──
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),
        sa.Column('duration_ms', sa.Integer),

        # ── Context ──
        sa.Column('environment', sa.Text),                       # JSON: runtime context (browser, env vars)
        sa.Column('retry_count', sa.Integer, server_default='0'),
        sa.Column('parent_execution_id', sa.Text),               # For nested/sub-workflows

        # ── Timestamps ──
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('metadata', sa.Text),
    )

    op.create_index('ix_workflow_exec_workflow', 'workflow_executions', ['workflow_id'])
    op.create_index('ix_workflow_exec_executor', 'workflow_executions', ['executor_id'])
    op.create_index('ix_workflow_exec_status', 'workflow_executions', ['status'])


def downgrade() -> None:
    op.drop_index('ix_workflow_exec_status')
    op.drop_index('ix_workflow_exec_executor')
    op.drop_index('ix_workflow_exec_workflow')
    op.drop_table('workflow_executions')

    op.drop_index('ix_workflows_state')
    op.drop_index('ix_workflows_org')
    op.drop_index('ix_workflows_creator')
    op.drop_table('workflows')
