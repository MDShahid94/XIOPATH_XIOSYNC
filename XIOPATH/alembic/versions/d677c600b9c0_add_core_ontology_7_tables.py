"""add_core_ontology_7_tables

Revision ID: d677c600b9c0
Revises: 5f7f5f1793c7
Create Date: 2026-07-08

Phase O.3: Creates the 7 core ontology tables from the approved Universal Agent
Ontology Blueprint v2.0. These implement the "Everything is an Agent" architecture.

New tables:
  1. agents              — Universal entity registry (humans, AIs, runtimes, tools)
  2. agent_operations     — Full lifecycle ledger with collaborative tracking
  3. agent_edges          — Typed relationships between agents (DAG)
  4. tool_registry        — Registered tools/capabilities available to agents
  5. capability_grants    — Permission matrix: which agent can use which tool
  6. event_log            — Append-only telemetry/audit stream

Modified tables:
  7. memory_nodes         — Add owner_agent_id FK column
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd677c600b9c0'
down_revision = '5f7f5f1793c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. AGENTS — Universal entity registry
    # =========================================================================
    # Every actor in the ecosystem: humans, AI models, runtimes, tools, workflows.
    # Type hierarchy: agent_type.agent_subtype (e.g. "compute.colab_runtime")
    op.create_table(
        'agents',
        sa.Column('id', sa.Text, primary_key=True),              # UUIDv7

        # --- IDENTITY ---
        sa.Column('agent_type', sa.Text, nullable=False),         # "human" | "ai" | "compute" | "tool" | "workflow" | "ecosystem"
        sa.Column('agent_subtype', sa.Text),                      # "super_admin" | "llm_worker" | "colab_runtime" | "browser_tool" | ...
        sa.Column('role', sa.Text),                               # Functional role: "master_orchestrator" | "worker" | "keepalive_sentinel"
        sa.Column('alias', sa.Text),                              # Human-readable name: "Colab Worker Alpha"
        sa.Column('parent_id', sa.Text),                          # → agents.id (hierarchical ownership)

        # --- LIFECYCLE ---
        sa.Column('state', sa.Text, server_default='proposed'),   # Current state in the lifecycle
        # Full lifecycle vocabulary:
        #   Pre-birth:  proposed | designed | implementing | experimenting | validated
        #   Birth:      initializing
        #   Operational: active | updating | upgrading | scaling | suspended | migrating
        #   End-of-life: terminating | terminated | demolished | archived
        sa.Column('lifecycle_phase', sa.Text, server_default='pre_birth'),
        # Coarse phase: "pre_birth" | "birth" | "operational" | "end_of_life"

        # --- CONFIGURATION ---
        sa.Column('config', sa.Text),                             # JSON: immutable init args (tailscale key, model name, etc.)
        sa.Column('runtime_args', sa.Text),                       # JSON: mutable live state (current URL, active task, etc.)

        # --- HEALTH ---
        sa.Column('last_heartbeat', sa.DateTime),
        sa.Column('health_status', sa.Text, server_default='unknown'),  # "healthy" | "degraded" | "offline" | "unknown"

        # --- METADATA ---
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('created_by', sa.Text),                         # → agents.id (who created this agent)
        sa.Column('metadata', sa.Text),                           # JSON: arbitrary extra context
    )

    # =========================================================================
    # 2. AGENT_OPERATIONS — Full lifecycle ledger
    # =========================================================================
    # Every state transition, upgrade, migration, etc. is recorded as an operation.
    # Supports collaborative tracking (who did what together).
    op.create_table(
        'agent_operations',
        sa.Column('id', sa.Text, primary_key=True),               # UUIDv7
        sa.Column('agent_id', sa.Text, nullable=False),            # → agents.id (the subject)

        # --- OPERATION ---
        sa.Column('operation', sa.Text, nullable=False),           # proposition | design | implementation | experimentation
                                                                   # | validation | initiation | updation | upgradation
                                                                   # | scaling | suspension | migration | termination
                                                                   # | demolition | archival | rollback
        sa.Column('from_state', sa.Text),                          # State before this operation
        sa.Column('to_state', sa.Text),                            # State after this operation
        sa.Column('trigger', sa.Text),                             # "user_command" | "schedule" | "auto" | "error" | "system"

        # --- COLLABORATIVE DIMENSION ---
        sa.Column('initiated_by', sa.Text, nullable=False),        # → agents.id (who started this)
        sa.Column('collaborators', sa.Text),                       # JSON: [{agent_id, role_in_operation}]

        # --- OPERATION CONTEXT ---
        sa.Column('scope', sa.Text),                               # "agent" | "component" | "ecosystem"
        sa.Column('depth_level', sa.Integer, server_default='0'),  # 0 = agent itself, 1 = sub-component, 2 = sub-sub...
        sa.Column('parent_operation_id', sa.Text),                 # → agent_operations.id (for nested operations)

        # --- EVIDENCE ---
        sa.Column('artifacts', sa.Text),                           # JSON: {plan_id, test_results, approval_record, diff_hash}
        sa.Column('rationale', sa.Text),                           # Why this operation was performed
        sa.Column('outcome', sa.Text),                             # "success" | "partial" | "failed" | "pending"

        # --- TIMING ---
        sa.Column('metadata', sa.Text),                            # JSON: additional context
        sa.Column('started_at', sa.DateTime, nullable=False),
        sa.Column('completed_at', sa.DateTime),                    # NULL if still in progress
        sa.Column('duration_ms', sa.Integer),                      # Computed on completion
    )

    # =========================================================================
    # 3. AGENT_EDGES — Typed relationships between agents (DAG)
    # =========================================================================
    # Directed edges: source → target with typed semantics.
    # Supports: manages, delegates_to, collaborates_with, keeps_alive, maintains_repo, etc.
    op.create_table(
        'agent_edges',
        sa.Column('id', sa.Text, primary_key=True),                # UUIDv7
        sa.Column('source_id', sa.Text, nullable=False),           # → agents.id
        sa.Column('target_id', sa.Text, nullable=False),           # → agents.id

        # --- EDGE SEMANTICS ---
        sa.Column('edge_type', sa.Text, nullable=False),           # "manages" | "delegates_to" | "collaborates_with"
                                                                   # | "provides_tool" | "keeps_alive" | "maintains_repo"
        sa.Column('config', sa.Text),                              # JSON: edge-specific configuration
        sa.Column('weight', sa.Float, server_default='1.0'),       # Relationship strength/priority
        sa.Column('bidirectional', sa.Boolean, server_default='0'),# Is the relationship symmetric?

        # --- LIFECYCLE ---
        sa.Column('state', sa.Text, server_default='active'),      # "active" | "suspended" | "archived"
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('metadata', sa.Text),                            # JSON
    )

    # =========================================================================
    # 4. TOOL_REGISTRY — Available tools/capabilities
    # =========================================================================
    # Tools are first-class citizens: browser automation, API calls, plugins, etc.
    op.create_table(
        'tool_registry',
        sa.Column('id', sa.Text, primary_key=True),                # UUIDv7
        sa.Column('name', sa.Text, nullable=False, unique=True),   # "playwright_click" | "captcha_solver" | "gemini_inference"
        sa.Column('tool_type', sa.Text, nullable=False),           # "browser" | "api" | "plugin" | "llm" | "system"
        sa.Column('version', sa.Text),                             # Semver: "1.0.0"

        # --- CAPABILITY DESCRIPTION ---
        sa.Column('description', sa.Text),                         # Human-readable description
        sa.Column('input_schema', sa.Text),                        # JSON Schema for tool inputs
        sa.Column('output_schema', sa.Text),                       # JSON Schema for tool outputs
        sa.Column('config', sa.Text),                              # JSON: default configuration

        # --- EXECUTION ---
        sa.Column('execution_mode', sa.Text, server_default='sync'),  # "sync" | "async" | "streaming"
        sa.Column('timeout_ms', sa.Integer, server_default='30000'),  # Default timeout
        sa.Column('retry_policy', sa.Text),                        # JSON: {max_retries, backoff_ms, retry_on}

        # --- METADATA ---
        sa.Column('state', sa.Text, server_default='active'),      # "active" | "deprecated" | "disabled"
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('metadata', sa.Text),                            # JSON
    )

    # =========================================================================
    # 5. CAPABILITY_GRANTS — Permission matrix
    # =========================================================================
    # Which agent can use which tool, with what constraints.
    op.create_table(
        'capability_grants',
        sa.Column('id', sa.Text, primary_key=True),                # UUIDv7
        sa.Column('agent_id', sa.Text, nullable=False),            # → agents.id (who gets the permission)
        sa.Column('tool_id', sa.Text, nullable=False),             # → tool_registry.id (what tool)
        sa.Column('granted_by', sa.Text, nullable=False),          # → agents.id (who granted it)

        # --- SCOPE & CONSTRAINTS ---
        sa.Column('scope', sa.Text, server_default='full'),        # "full" | "read_only" | "execute_only" | "limited"
        sa.Column('constraints', sa.Text),                         # JSON: rate limits, time windows, domain restrictions
        sa.Column('expires_at', sa.DateTime),                      # NULL = permanent

        # --- LIFECYCLE ---
        sa.Column('state', sa.Text, server_default='active'),      # "active" | "revoked" | "expired"
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('revoked_at', sa.DateTime),
        sa.Column('revoked_by', sa.Text),                          # → agents.id
        sa.Column('metadata', sa.Text),                            # JSON
    )

    # =========================================================================
    # 6. EVENT_LOG — Append-only telemetry/audit stream
    # =========================================================================
    # Every significant event: action executions, errors, state changes, heartbeats.
    op.create_table(
        'event_log',
        sa.Column('id', sa.Text, primary_key=True),                # UUIDv7 (time-sortable)
        sa.Column('agent_id', sa.Text, nullable=False),            # → agents.id (who generated the event)
        sa.Column('event_type', sa.Text, nullable=False),          # "action_executed" | "error" | "state_change" | "heartbeat"
                                                                   # | "tool_invoked" | "auth_event" | "metric"
        sa.Column('severity', sa.Text, server_default='info'),     # "debug" | "info" | "warn" | "error" | "critical"

        # --- EVENT DATA ---
        sa.Column('summary', sa.Text),                             # Human-readable: "Clicked login button"
        sa.Column('payload', sa.Text),                             # JSON: full event data
        sa.Column('correlation_id', sa.Text),                      # Links related events across agents
        sa.Column('operation_id', sa.Text),                        # → agent_operations.id (which operation caused this)

        # --- CONTEXT ---
        sa.Column('source_ip', sa.Text),                           # Originating IP
        sa.Column('user_agent', sa.Text),                          # Browser/client UA string

        # --- TIMING ---
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('metadata', sa.Text),                            # JSON
    )

    # =========================================================================
    # 7. MEMORY_NODES — Add owner_agent_id FK column
    # =========================================================================
    # Links existing memory nodes to the agents that own them.
    with op.batch_alter_table('memory_nodes') as batch_op:
        batch_op.add_column(
            sa.Column('owner_agent_id', sa.Text)                   # → agents.id
        )

    # --- INDEXES for query performance ---
    op.create_index('ix_agents_type', 'agents', ['agent_type'])
    op.create_index('ix_agents_state', 'agents', ['state'])
    op.create_index('ix_agents_parent', 'agents', ['parent_id'])

    op.create_index('ix_operations_agent', 'agent_operations', ['agent_id'])
    op.create_index('ix_operations_type', 'agent_operations', ['operation'])
    op.create_index('ix_operations_initiated_by', 'agent_operations', ['initiated_by'])
    op.create_index('ix_operations_parent', 'agent_operations', ['parent_operation_id'])

    op.create_index('ix_edges_source', 'agent_edges', ['source_id'])
    op.create_index('ix_edges_target', 'agent_edges', ['target_id'])
    op.create_index('ix_edges_type', 'agent_edges', ['edge_type'])

    op.create_index('ix_grants_agent', 'capability_grants', ['agent_id'])
    op.create_index('ix_grants_tool', 'capability_grants', ['tool_id'])

    op.create_index('ix_events_agent', 'event_log', ['agent_id'])
    op.create_index('ix_events_type', 'event_log', ['event_type'])
    op.create_index('ix_events_correlation', 'event_log', ['correlation_id'])
    op.create_index('ix_events_created', 'event_log', ['created_at'])

    op.create_index('ix_memory_owner', 'memory_nodes', ['owner_agent_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_memory_owner', 'memory_nodes')
    op.drop_index('ix_events_created', 'event_log')
    op.drop_index('ix_events_correlation', 'event_log')
    op.drop_index('ix_events_type', 'event_log')
    op.drop_index('ix_events_agent', 'event_log')
    op.drop_index('ix_grants_tool', 'capability_grants')
    op.drop_index('ix_grants_agent', 'capability_grants')
    op.drop_index('ix_edges_type', 'agent_edges')
    op.drop_index('ix_edges_target', 'agent_edges')
    op.drop_index('ix_edges_source', 'agent_edges')
    op.drop_index('ix_operations_parent', 'agent_operations')
    op.drop_index('ix_operations_initiated_by', 'agent_operations')
    op.drop_index('ix_operations_type', 'agent_operations')
    op.drop_index('ix_operations_agent', 'agent_operations')
    op.drop_index('ix_agents_parent', 'agents')
    op.drop_index('ix_agents_state', 'agents')
    op.drop_index('ix_agents_type', 'agents')

    # Remove owner_agent_id from memory_nodes
    with op.batch_alter_table('memory_nodes') as batch_op:
        batch_op.drop_column('owner_agent_id')

    # Drop tables in reverse dependency order
    op.drop_table('event_log')
    op.drop_table('capability_grants')
    op.drop_table('tool_registry')
    op.drop_table('agent_edges')
    op.drop_table('agent_operations')
    op.drop_table('agents')
