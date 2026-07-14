"""v5_0_rename_agent_to_actor

Revision ID: b50a0c7e3d12
Revises: a3b7e2d5f819
Create Date: 2026-07-12

Phase v5.0: The Great Rename — Agent → Actor ontology.

Renames:
  agents              → actors           (+ column renames: agent_type→actor_type, etc.)
  agent_operations    → operations       (+ agent_id→actor_id)
  agent_edges         → actor_edges
  tool_registry       → capabilities     (+ tool_type→capability_type)
  capability_grants   (column renames: agent_id→actor_id, tool_id→capability_id)
  event_log           → events           (+ agent_id→actor_id)
  runtime_connections → connections      (+ source_agent_id→source_actor_id, etc.)
  agent_profiles      → actor_profiles   (+ agent_id→actor_id)
  agent_environments  → bundles          (+ structural changes)
  agent_versions      → actor_versions   (+ agent_id→actor_id)

Strategy:
  - SQLite doesn't support ALTER TABLE RENAME COLUMN, so we use batch mode.
  - PostgreSQL supports it natively, so we use conditional logic.
  - All renames are wrapped in batch_alter_table for SQLite compatibility.
"""
from alembic import op
import sqlalchemy as sa
from alembic.operations import BatchOperations


# revision identifiers, used by Alembic.
revision = 'b50a0c7e3d12'
down_revision = 'a3b7e2d5f819'
branch_labels = None
depends_on = None


def _is_postgres():
    """Check if we're running against PostgreSQL."""
    return 'postgresql' in str(op.get_bind().engine.url)


def upgrade() -> None:
    # =========================================================================
    # 1. agents → actors
    # =========================================================================
    op.rename_table('agents', 'actors')
    if _is_postgres():
        op.alter_column('actors', 'agent_type', new_column_name='actor_type')
        op.alter_column('actors', 'agent_subtype', new_column_name='actor_subtype')
        op.add_column('actors', sa.Column('trust_tier', sa.Text, server_default='standard'))
        # Rename runtime_args → runtime_state
        op.alter_column('actors', 'runtime_args', new_column_name='runtime_state')
    else:
        # SQLite: use batch mode for column renames
        with op.batch_alter_table('actors') as batch_op:
            batch_op.alter_column('agent_type', new_column_name='actor_type')
            batch_op.alter_column('agent_subtype', new_column_name='actor_subtype')
            batch_op.add_column(sa.Column('trust_tier', sa.Text, server_default='standard'))
            batch_op.alter_column('runtime_args', new_column_name='runtime_state')

    # =========================================================================
    # 2. agent_operations → operations
    # =========================================================================
    op.rename_table('agent_operations', 'operations')
    if _is_postgres():
        op.alter_column('operations', 'agent_id', new_column_name='actor_id')
    else:
        with op.batch_alter_table('operations') as batch_op:
            batch_op.alter_column('agent_id', new_column_name='actor_id')

    # =========================================================================
    # 3. agent_edges → actor_edges
    # =========================================================================
    op.rename_table('agent_edges', 'actor_edges')

    # =========================================================================
    # 4. tool_registry → capabilities
    # =========================================================================
    op.rename_table('tool_registry', 'capabilities')
    if _is_postgres():
        op.alter_column('capabilities', 'tool_type', new_column_name='capability_type')
    else:
        with op.batch_alter_table('capabilities') as batch_op:
            batch_op.alter_column('tool_type', new_column_name='capability_type')

    # =========================================================================
    # 5. capability_grants — column renames only
    # =========================================================================
    if _is_postgres():
        op.alter_column('capability_grants', 'agent_id', new_column_name='actor_id')
        op.alter_column('capability_grants', 'tool_id', new_column_name='capability_id')
    else:
        with op.batch_alter_table('capability_grants') as batch_op:
            batch_op.alter_column('agent_id', new_column_name='actor_id')
            batch_op.alter_column('tool_id', new_column_name='capability_id')

    # =========================================================================
    # 6. event_log → events
    # =========================================================================
    op.rename_table('event_log', 'events')
    if _is_postgres():
        op.alter_column('events', 'agent_id', new_column_name='actor_id')
    else:
        with op.batch_alter_table('events') as batch_op:
            batch_op.alter_column('agent_id', new_column_name='actor_id')

    # =========================================================================
    # 7. runtime_connections → connections
    # =========================================================================
    op.rename_table('runtime_connections', 'connections')
    if _is_postgres():
        op.alter_column('connections', 'source_agent_id', new_column_name='source_actor_id')
        op.alter_column('connections', 'target_agent_id', new_column_name='target_actor_id')
        op.alter_column('connections', 'exit_node_agent_id', new_column_name='exit_node_actor_id')
    else:
        with op.batch_alter_table('connections') as batch_op:
            batch_op.alter_column('source_agent_id', new_column_name='source_actor_id')
            batch_op.alter_column('target_agent_id', new_column_name='target_actor_id')
            batch_op.alter_column('exit_node_agent_id', new_column_name='exit_node_actor_id')

    # =========================================================================
    # 8. agent_profiles → actor_profiles
    # =========================================================================
    op.rename_table('agent_profiles', 'actor_profiles')
    if _is_postgres():
        op.alter_column('actor_profiles', 'agent_id', new_column_name='actor_id')
    else:
        with op.batch_alter_table('actor_profiles') as batch_op:
            batch_op.alter_column('agent_id', new_column_name='actor_id')

    # =========================================================================
    # 9. agent_environments → bundles
    # =========================================================================
    op.rename_table('agent_environments', 'bundles')
    if _is_postgres():
        op.alter_column('bundles', 'agent_id', new_column_name='creator_id')
        op.alter_column('bundles', 'environment_type', new_column_name='bundle_type')
    else:
        with op.batch_alter_table('bundles') as batch_op:
            batch_op.alter_column('agent_id', new_column_name='creator_id')
            batch_op.alter_column('environment_type', new_column_name='bundle_type')

    # =========================================================================
    # 10. agent_versions → actor_versions
    # =========================================================================
    op.rename_table('agent_versions', 'actor_versions')
    if _is_postgres():
        op.alter_column('actor_versions', 'agent_id', new_column_name='actor_id')
        op.alter_column('actor_versions', 'runtime_args_snapshot', new_column_name='runtime_state_snapshot')
        op.alter_column('actor_versions', 'tool_grants_snapshot', new_column_name='capability_grants_snapshot')
        op.alter_column('actor_versions', 'environment_id', new_column_name='bundle_id')
    else:
        with op.batch_alter_table('actor_versions') as batch_op:
            batch_op.alter_column('agent_id', new_column_name='actor_id')
            batch_op.alter_column('runtime_args_snapshot', new_column_name='runtime_state_snapshot')
            batch_op.alter_column('tool_grants_snapshot', new_column_name='capability_grants_snapshot')
            batch_op.alter_column('environment_id', new_column_name='bundle_id')

    # =========================================================================
    # 11. Update memory_nodes FK column
    # =========================================================================
    # owner_agent_id was added in the ontology migration — rename it
    try:
        if _is_postgres():
            op.alter_column('memory_nodes', 'owner_agent_id', new_column_name='owner_actor_id')
        else:
            with op.batch_alter_table('memory_nodes') as batch_op:
                batch_op.alter_column('owner_agent_id', new_column_name='owner_actor_id')
    except Exception:
        pass  # Column may not exist in all environments


def downgrade() -> None:
    """Reverse the v5.0 rename: actor → agent."""

    # 11. memory_nodes FK
    try:
        if _is_postgres():
            op.alter_column('memory_nodes', 'owner_actor_id', new_column_name='owner_agent_id')
        else:
            with op.batch_alter_table('memory_nodes') as batch_op:
                batch_op.alter_column('owner_actor_id', new_column_name='owner_agent_id')
    except Exception:
        pass

    # 10. actor_versions → agent_versions
    if _is_postgres():
        op.alter_column('actor_versions', 'actor_id', new_column_name='agent_id')
        op.alter_column('actor_versions', 'runtime_state_snapshot', new_column_name='runtime_args_snapshot')
        op.alter_column('actor_versions', 'capability_grants_snapshot', new_column_name='tool_grants_snapshot')
        op.alter_column('actor_versions', 'bundle_id', new_column_name='environment_id')
    else:
        with op.batch_alter_table('actor_versions') as batch_op:
            batch_op.alter_column('actor_id', new_column_name='agent_id')
            batch_op.alter_column('runtime_state_snapshot', new_column_name='runtime_args_snapshot')
            batch_op.alter_column('capability_grants_snapshot', new_column_name='tool_grants_snapshot')
            batch_op.alter_column('bundle_id', new_column_name='environment_id')
    op.rename_table('actor_versions', 'agent_versions')

    # 9. bundles → agent_environments
    if _is_postgres():
        op.alter_column('bundles', 'creator_id', new_column_name='agent_id')
        op.alter_column('bundles', 'bundle_type', new_column_name='environment_type')
    else:
        with op.batch_alter_table('bundles') as batch_op:
            batch_op.alter_column('creator_id', new_column_name='agent_id')
            batch_op.alter_column('bundle_type', new_column_name='environment_type')
    op.rename_table('bundles', 'agent_environments')

    # 8. actor_profiles → agent_profiles
    if _is_postgres():
        op.alter_column('actor_profiles', 'actor_id', new_column_name='agent_id')
    else:
        with op.batch_alter_table('actor_profiles') as batch_op:
            batch_op.alter_column('actor_id', new_column_name='agent_id')
    op.rename_table('actor_profiles', 'agent_profiles')

    # 7. connections → runtime_connections
    if _is_postgres():
        op.alter_column('connections', 'source_actor_id', new_column_name='source_agent_id')
        op.alter_column('connections', 'target_actor_id', new_column_name='target_agent_id')
        op.alter_column('connections', 'exit_node_actor_id', new_column_name='exit_node_agent_id')
    else:
        with op.batch_alter_table('connections') as batch_op:
            batch_op.alter_column('source_actor_id', new_column_name='source_agent_id')
            batch_op.alter_column('target_actor_id', new_column_name='target_agent_id')
            batch_op.alter_column('exit_node_actor_id', new_column_name='exit_node_agent_id')
    op.rename_table('connections', 'runtime_connections')

    # 6. events → event_log
    if _is_postgres():
        op.alter_column('events', 'actor_id', new_column_name='agent_id')
    else:
        with op.batch_alter_table('events') as batch_op:
            batch_op.alter_column('actor_id', new_column_name='agent_id')
    op.rename_table('events', 'event_log')

    # 5. capability_grants — column renames
    if _is_postgres():
        op.alter_column('capability_grants', 'actor_id', new_column_name='agent_id')
        op.alter_column('capability_grants', 'capability_id', new_column_name='tool_id')
    else:
        with op.batch_alter_table('capability_grants') as batch_op:
            batch_op.alter_column('actor_id', new_column_name='agent_id')
            batch_op.alter_column('capability_id', new_column_name='tool_id')

    # 4. capabilities → tool_registry
    if _is_postgres():
        op.alter_column('capabilities', 'capability_type', new_column_name='tool_type')
    else:
        with op.batch_alter_table('capabilities') as batch_op:
            batch_op.alter_column('capability_type', new_column_name='tool_type')
    op.rename_table('capabilities', 'tool_registry')

    # 3. actor_edges → agent_edges
    op.rename_table('actor_edges', 'agent_edges')

    # 2. operations → agent_operations
    if _is_postgres():
        op.alter_column('operations', 'actor_id', new_column_name='agent_id')
    else:
        with op.batch_alter_table('operations') as batch_op:
            batch_op.alter_column('actor_id', new_column_name='agent_id')
    op.rename_table('operations', 'agent_operations')

    # 1. actors → agents
    if _is_postgres():
        op.alter_column('actors', 'actor_type', new_column_name='agent_type')
        op.alter_column('actors', 'actor_subtype', new_column_name='agent_subtype')
        op.alter_column('actors', 'runtime_state', new_column_name='runtime_args')
        op.drop_column('actors', 'trust_tier')
    else:
        with op.batch_alter_table('actors') as batch_op:
            batch_op.alter_column('actor_type', new_column_name='agent_type')
            batch_op.alter_column('actor_subtype', new_column_name='agent_subtype')
            batch_op.alter_column('runtime_state', new_column_name='runtime_args')
            batch_op.drop_column('trust_tier')
    op.rename_table('actors', 'agents')
