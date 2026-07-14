"""add_extension_4_tables

Revision ID: 9fc8d1c36f34
Revises: d677c600b9c0
Create Date: 2026-07-10

Phase O.4: Creates the 4 extension tables from the approved ontology blueprint.
These extend the core agent model with runtime networking, profiles, environments,
and versioning/CI/CD support.

New tables:
  1. runtime_connections  — Tailscale/WireGuard tunnels, exit node routing, service pinning
  2. agent_profiles       — Persistent browser/service profiles with encrypted Drive storage
  3. agent_environments   — Portable runtime bundles (tools + context + services)
  4. agent_versions       — Git-like version history with human-gated approval model
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9fc8d1c36f34'
down_revision = 'd677c600b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. RUNTIME_CONNECTIONS — Inter-agent networking
    # =========================================================================
    # Models Tailscale tunnels, exit node routing, and service pinning.
    # Supports dynamic exit node switching with auth-pinning constraints.
    op.create_table(
        'runtime_connections',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('source_agent_id', sa.Text, nullable=False),       # → agents.id
        sa.Column('target_agent_id', sa.Text, nullable=False),       # → agents.id

        # --- CONNECTION IDENTITY ---
        sa.Column('protocol', sa.Text, nullable=False),              # tailnet_http | tailnet_ws | tailnet_socks5 | direct_http | direct_ws
        sa.Column('transport', sa.Text, nullable=False),             # tailscale | wireguard | direct | tor
        sa.Column('source_endpoint', sa.Text),                       # "100.96.27.123:5000"
        sa.Column('target_endpoint', sa.Text),                       # "100.86.149.127:8000"

        # --- DYNAMIC EXIT NODE ROUTING ---
        sa.Column('current_exit_node_ip', sa.Text),                  # Currently active exit node
        sa.Column('default_exit_node_ip', sa.Text),                  # Fallback from config
        sa.Column('exit_node_agent_id', sa.Text),                    # → agents.id (whose IP to route through)
        sa.Column('proxy_config', sa.Text),                          # JSON: {"socks5": "localhost:1055", "http": null}
        sa.Column('routing_rule', sa.Text),                          # host_via_admin_ip | worker_via_client_ip | dynamic | direct

        # --- SERVICE PINNING (auth-bound to specific exit nodes) ---
        sa.Column('pinned_services', sa.Text),                       # JSON: [{"service": "google_auth", "pinned_exit_ip": "100.x.x.x"}]

        # --- STATE PERSISTENCE ---
        sa.Column('auth_state_path', sa.Text),                       # Drive path for tailscaled.state etc.
        sa.Column('auth_state_storage', sa.Text),                    # google_drive | s3 | vault | local
        sa.Column('auth_persistence', sa.Text),                      # per_runtime | per_session | per_account

        # --- HEALTH ---
        sa.Column('state', sa.Text, server_default='pending'),       # pending | connected | degraded | disconnected
        sa.Column('last_ping_ms', sa.Integer),
        sa.Column('last_verified_at', sa.DateTime),
        sa.Column('exit_node_switched_at', sa.DateTime),             # Track exit node changes

        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('metadata', sa.Text),                              # JSON
    )

    # =========================================================================
    # 2. AGENT_PROFILES — Persistent service/browser profiles
    # =========================================================================
    # Encrypted browser profiles, Tailscale identities, etc. stored on Google Drive.
    op.create_table(
        'agent_profiles',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('agent_id', sa.Text, nullable=False),              # → agents.id

        # --- PROFILE IDENTITY ---
        sa.Column('profile_type', sa.Text, nullable=False),          # browser_chrome | tailscale | cli_tool | ai_context
        sa.Column('account_identity', sa.Text),                      # user@gmail.com | tailscale_node_key | null

        # --- STORAGE ---
        sa.Column('storage_backend', sa.Text, nullable=False),       # google_drive | s3 | vault | local
        sa.Column('storage_path', sa.Text, nullable=False),          # /drive/MyDrive/profiles/chrome_profile_1.xio
        sa.Column('storage_folder_id', sa.Text),                     # Google Drive folder ID

        # --- ENCRYPTION ---
        sa.Column('encryption_method', sa.Text, server_default='fernet'),  # fernet | aes256_gcm | none
        sa.Column('encryption_key_ref', sa.Text),                    # Reference to vault key (not the key itself!)

        # --- PERSISTENCE STRATEGY ---
        sa.Column('persistence_mode', sa.Text, nullable=False),      # periodic | on_milestone | on_terminate | once_per_account
        sa.Column('save_interval_seconds', sa.Integer),              # For periodic: 600 (10 min)
        sa.Column('last_saved_at', sa.DateTime),
        sa.Column('save_count', sa.Integer, server_default='0'),

        # --- PROFILE HEALTH ---
        sa.Column('state', sa.Text, server_default='fresh'),         # fresh | active | stale | corrupted
        sa.Column('checksum', sa.Text),                              # SHA-256 of last saved profile
        sa.Column('size_bytes', sa.Integer),

        # --- LIFECYCLE ---
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('expires_at', sa.DateTime),                        # For session-bound profiles
        sa.Column('metadata', sa.Text),                              # JSON
    )

    # =========================================================================
    # 3. AGENT_ENVIRONMENTS — Portable runtime bundles
    # =========================================================================
    # Serialized bundles of tools + AI context + services + workflow state.
    # Supports marketplace-ready distribution and cross-runtime portability.
    op.create_table(
        'agent_environments',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('agent_id', sa.Text, nullable=False),              # → agents.id

        # --- ENVIRONMENT TYPE ---
        sa.Column('environment_type', sa.Text, nullable=False),      # runtime_sandbox | workflow_bundle | tool_kit

        # --- CONTENTS MANIFEST ---
        sa.Column('manifest', sa.Text, nullable=False),              # JSON: {services, tools, ai_context, workflow_vars}

        # --- STORAGE ---
        sa.Column('storage_backend', sa.Text, nullable=False),       # google_drive | s3 | vault
        sa.Column('storage_path', sa.Text, nullable=False),
        sa.Column('bundle_checksum', sa.Text),                       # SHA-256
        sa.Column('bundle_size_bytes', sa.Integer),

        # --- PORTABILITY ---
        sa.Column('is_portable', sa.Boolean, server_default='0'),    # Can others download and execute this?
        sa.Column('visibility', sa.Text, server_default='private'),  # private | shared | marketplace
        sa.Column('compatible_runtimes', sa.Text),                   # JSON: ["compute.colab_runtime", "compute.host_runtime"]

        # --- LIFECYCLE ---
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_serialized_at', sa.DateTime),
        sa.Column('version', sa.Text, server_default='1.0.0'),
        sa.Column('state', sa.Text, server_default='active'),        # active | archived | corrupted
    )

    # =========================================================================
    # 4. AGENT_VERSIONS — Git-like version history
    # =========================================================================
    # Every config/tool/environment change is versioned. Supports human-gated
    # approval (AI proposes, human approves) and optional git CI/CD integration.
    op.create_table(
        'agent_versions',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('agent_id', sa.Text, nullable=False),              # → agents.id

        # --- VERSION IDENTITY ---
        sa.Column('version_tag', sa.Text, nullable=False),           # Semver: "1.0.0"
        sa.Column('version_hash', sa.Text, nullable=False),          # SHA-256 of serialized state
        sa.Column('parent_version_id', sa.Text),                     # → agent_versions.id (forms chain)
        sa.Column('branch', sa.Text, server_default='main'),         # main | experiment/new-locator | user/shahid/custom

        # --- SNAPSHOT ---
        sa.Column('config_snapshot', sa.Text, nullable=False),       # JSON: frozen agents.config
        sa.Column('runtime_args_snapshot', sa.Text),                 # JSON: frozen agents.runtime_args
        sa.Column('tool_grants_snapshot', sa.Text),                  # JSON: list of grant IDs active at this version
        sa.Column('environment_id', sa.Text),                        # → agent_environments.id

        # --- CHANGE METADATA ---
        sa.Column('change_type', sa.Text, nullable=False),           # patch | minor | major | rollback | fork
        sa.Column('change_summary', sa.Text),                        # Human-readable
        sa.Column('diff_from_parent', sa.Text),                      # JSON: structured diff

        # --- AUTHORSHIP ---
        sa.Column('authored_by', sa.Text, nullable=False),           # → agents.id
        sa.Column('reviewed_by', sa.Text),                           # → agents.id (optional reviewer)
        sa.Column('operation_id', sa.Text),                          # → agent_operations.id

        # --- AUTHORITY (human-gated approval model) ---
        sa.Column('requires_human_approval', sa.Boolean, server_default='0'),
        sa.Column('approval_status', sa.Text),                       # pending | approved | rejected | auto_approved
        sa.Column('approved_by', sa.Text),                           # → agents.id
        sa.Column('approved_at', sa.DateTime),

        # --- CI/CD INTEGRATION ---
        sa.Column('git_repo_url', sa.Text),
        sa.Column('git_commit_hash', sa.Text),
        sa.Column('git_branch', sa.Text),
        sa.Column('ci_pipeline_status', sa.Text),                    # pending | passed | failed | skipped
        sa.Column('ci_pipeline_url', sa.Text),

        # --- STATE ---
        sa.Column('state', sa.Text, server_default='active'),        # active | superseded | rolled_back | archived
        sa.Column('is_current', sa.Boolean, server_default='0'),     # Only one per agent per branch is current

        sa.Column('created_at', sa.DateTime, nullable=False),
    )

    # --- INDEXES ---
    op.create_index('ix_rtconn_source', 'runtime_connections', ['source_agent_id'])
    op.create_index('ix_rtconn_target', 'runtime_connections', ['target_agent_id'])
    op.create_index('ix_rtconn_state', 'runtime_connections', ['state'])

    op.create_index('ix_profiles_agent', 'agent_profiles', ['agent_id'])
    op.create_index('ix_profiles_type', 'agent_profiles', ['profile_type'])

    op.create_index('ix_envs_agent', 'agent_environments', ['agent_id'])
    op.create_index('ix_envs_visibility', 'agent_environments', ['visibility'])

    op.create_index('ix_versions_agent', 'agent_versions', ['agent_id'])
    op.create_index('ix_versions_branch', 'agent_versions', ['agent_id', 'branch'])
    op.create_index('ix_versions_current', 'agent_versions', ['agent_id', 'is_current'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_versions_current', 'agent_versions')
    op.drop_index('ix_versions_branch', 'agent_versions')
    op.drop_index('ix_versions_agent', 'agent_versions')
    op.drop_index('ix_envs_visibility', 'agent_environments')
    op.drop_index('ix_envs_agent', 'agent_environments')
    op.drop_index('ix_profiles_type', 'agent_profiles')
    op.drop_index('ix_profiles_agent', 'agent_profiles')
    op.drop_index('ix_rtconn_state', 'runtime_connections')
    op.drop_index('ix_rtconn_target', 'runtime_connections')
    op.drop_index('ix_rtconn_source', 'runtime_connections')

    # Drop tables
    op.drop_table('agent_versions')
    op.drop_table('agent_environments')
    op.drop_table('agent_profiles')
    op.drop_table('runtime_connections')
