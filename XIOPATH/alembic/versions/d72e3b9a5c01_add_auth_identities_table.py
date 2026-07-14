"""add_auth_identities_table

Revision ID: d72e3b9a5c01
Revises: c61f2a8b4e90
Create Date: 2026-07-12

Phase 3: Auth Separation — splits the monolithic `users` table into:
  1. `auth_identities` — credentials, auth method, login tracking
  2. `actors` (existing) — the ontology entity for the human user

This enables:
  - Multiple auth methods per actor (password, OAuth, API key)
  - JWT payloads referencing `actor_id` (ontology entity)
  - Clean separation of authentication vs. identity

Migration strategy:
  - Creates `auth_identities` table
  - Copies existing `users` rows into `auth_identities` + creates
    corresponding `actors` entries
  - Keeps `users` table intact (deprecated) for rollback safety
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = 'd72e3b9a5c01'
down_revision = 'c61f2a8b4e90'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create auth_identities table
    # =========================================================================
    op.create_table(
        'auth_identities',
        sa.Column('id', sa.Text, primary_key=True),              # UUIDv7
        sa.Column('actor_id', sa.Text, nullable=False),           # → actors.id
        sa.Column('username', sa.Text, nullable=False, unique=True),
        sa.Column('auth_method', sa.Text, nullable=False, server_default='password'),
        # auth_method: "password" | "oauth_google" | "oauth_github" | "api_key"
        sa.Column('auth_credential', sa.Text, nullable=False),    # bcrypt hash, OAuth token, API key hash
        sa.Column('auth_role', sa.Text, nullable=False, server_default='client'),
        # auth_role: "admin" | "client" | "worker" | "service"
        sa.Column('state', sa.Text, nullable=False, server_default='active'),
        # state: "active" | "suspended" | "revoked"
        sa.Column('last_login_at', sa.DateTime),
        sa.Column('login_count', sa.Integer, server_default='0'),
        sa.Column('failed_attempts', sa.Integer, server_default='0'),
        sa.Column('locked_until', sa.DateTime),                   # Account lockout
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('metadata', sa.Text),                           # JSON extension bag
    )

    op.create_index('ix_auth_identities_actor_id', 'auth_identities', ['actor_id'])
    op.create_index('ix_auth_identities_username', 'auth_identities', ['username'], unique=True)

    # =========================================================================
    # 2. Migrate existing users → auth_identities + actors
    # =========================================================================
    # This runs as raw SQL for portability across SQLite and PostgreSQL
    conn = op.get_bind()

    try:
        users = conn.execute(sa.text("SELECT id, username, password_hash, role FROM users")).fetchall()
    except Exception:
        users = []  # users table may not exist in fresh installs

    now = datetime.now(timezone.utc).isoformat()

    for user in users:
        user_id = user[0]
        username = user[1]
        password_hash = user[2]
        role = user[3] or 'client'

        # Create actor for this user (if not already exists)
        existing_actor = conn.execute(
            sa.text("SELECT id FROM actors WHERE id = :id"),
            {"id": user_id}
        ).fetchone()

        if not existing_actor:
            conn.execute(
                sa.text("""INSERT INTO actors (id, actor_type, actor_subtype, role, alias,
                           state, lifecycle_phase, trust_tier, created_at, created_by)
                           VALUES (:id, 'human', :subtype, :role, :alias,
                           'active', 'operational', 'standard', :now, 'migration')"""),
                {
                    "id": user_id,
                    "subtype": "admin" if role == "admin" else "member",
                    "role": role,
                    "alias": username,
                    "now": now,
                }
            )

        # Create auth_identity
        import uuid
        try:
            auth_id = str(uuid.uuid7())
        except AttributeError:
            auth_id = str(uuid.uuid4())

        conn.execute(
            sa.text("""INSERT INTO auth_identities
                       (id, actor_id, username, auth_method, auth_credential, auth_role, state, created_at)
                       VALUES (:id, :actor_id, :username, 'password', :credential, :role, 'active', :now)"""),
            {
                "id": auth_id,
                "actor_id": user_id,
                "username": username,
                "credential": password_hash,
                "role": role,
                "now": now,
            }
        )


def downgrade() -> None:
    op.drop_index('ix_auth_identities_username')
    op.drop_index('ix_auth_identities_actor_id')
    op.drop_table('auth_identities')
