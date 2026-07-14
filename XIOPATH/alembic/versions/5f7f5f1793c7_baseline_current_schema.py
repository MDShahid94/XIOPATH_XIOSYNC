"""baseline_current_schema

Revision ID: 5f7f5f1793c7
Revises: 
Create Date: 2026-07-08

Baseline migration capturing the current XIOPATH schema.
All previous demo data (workflows, actions, user credentials) has been
cleared — this is the canonical starting point for all future migrations.

Tables created:
  - memory_nodes (core workflow/action memory)
  - client_votes (consensus tracking)
  - client_vote_counts (anti-spam vote weighting)
  - users (auth & RBAC)
  - scheduled_jobs (recurring workflow execution)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f7f5f1793c7'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- memory_nodes: Core workflow/action memory ---
    op.create_table(
        'memory_nodes',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('tier', sa.Text, nullable=False),
        sa.Column('domain', sa.Text, nullable=False),
        sa.Column('intent', sa.Text, nullable=False),
        sa.Column('device_type', sa.Text),
        sa.Column('os_name', sa.Text),
        sa.Column('browser', sa.Text),
        sa.Column('viewport_width', sa.Integer),
        sa.Column('viewport_height', sa.Integer),
        sa.Column('visibility', sa.Text, server_default='public'),
        sa.Column('face_value', sa.Text),
        sa.Column('place_value', sa.Text),
        sa.Column('action_type', sa.Text, nullable=False),
        sa.Column('action_params', sa.Text),
        sa.Column('previous_intent', sa.Text),
        sa.Column('next_nodes', sa.Text),
        sa.Column('promotions', sa.Integer, server_default='0'),
        sa.Column('last_used', sa.DateTime, nullable=False),
        sa.Column('client_id', sa.Text, nullable=False),
        sa.Column('volatility_type', sa.Text, server_default='static'),
        sa.Column('fallback_plugin', sa.Text),
        sa.Column('output_var', sa.Text),
        sa.Column('execution_mode', sa.Text, server_default='sequential'),
        sa.Column('context_hash', sa.Text),
        sa.Column('ref_count', sa.Integer, server_default='0'),
        sa.Column('bayesian_score', sa.Float, server_default='0.5'),
        sa.Column('ema_score', sa.Float, server_default='0.5'),
        sa.Column('total_vote_weight', sa.Float, server_default='0.0'),
        sa.Column('status', sa.Text, server_default='ACTIVE'),
        sa.Column('lookup_key', sa.Text),
    )

    # --- client_votes: Consensus tracking ---
    op.create_table(
        'client_votes',
        sa.Column('node_id', sa.Text, nullable=False),
        sa.Column('client_id', sa.Text, nullable=False),
        sa.PrimaryKeyConstraint('node_id', 'client_id'),
    )

    # --- client_vote_counts: Anti-spam vote weighting (E-12) ---
    op.create_table(
        'client_vote_counts',
        sa.Column('client_id', sa.Text, primary_key=True),
        sa.Column('vote_count', sa.Integer, server_default='0'),
        sa.Column('last_voted', sa.DateTime),
    )

    # --- users: Auth & RBAC ---
    op.create_table(
        'users',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('username', sa.Text, nullable=False, unique=True),
        sa.Column('password_hash', sa.Text, nullable=False),
        sa.Column('role', sa.Text, nullable=False, server_default='client'),
    )

    # --- scheduled_jobs: Recurring workflow execution (C8) ---
    op.create_table(
        'scheduled_jobs',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('user_id', sa.Text, nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('intent', sa.Text, nullable=False),
        sa.Column('cron', sa.Text, nullable=False),
        sa.Column('enabled', sa.Boolean, server_default='1'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_run', sa.DateTime),
        sa.Column('next_run', sa.DateTime),
        sa.Column('run_count', sa.Integer, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('scheduled_jobs')
    op.drop_table('users')
    op.drop_table('client_vote_counts')
    op.drop_table('client_votes')
    op.drop_table('memory_nodes')
