"""add_swarm_intelligence_tables

Revision ID: 14c2c1f29abe
Revises: b16c7f3a9e45
Create Date: 2026-07-12 18:09:22.042709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14c2c1f29abe'
down_revision: Union[str, Sequence[str], None] = 'b16c7f3a9e45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS trust_ledger (
            actor_id TEXT PRIMARY KEY,
            tier INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            reputation_score REAL DEFAULT 0.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT,
            error_message TEXT,
            execution_trace TEXT,
            status TEXT,
            resolution_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS trust_ledger")
    op.execute("DROP TABLE IF EXISTS dead_letter_queue")
