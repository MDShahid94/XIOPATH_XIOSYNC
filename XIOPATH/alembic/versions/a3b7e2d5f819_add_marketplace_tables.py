"""add_marketplace_tables

Revision ID: a3b7e2d5f819
Revises: 9fc8d1c36f34
Create Date: 2026-07-10

Phase M.5: Creates marketplace tables for the environment marketplace.

New tables:
  1. marketplace_listings  — Published environments with metadata, stats, and discovery fields
  2. marketplace_reviews   — User ratings and reviews per listing (one review per user per listing)
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b7e2d5f819'
down_revision = '9fc8d1c36f34'
branch_labels = None
depends_on = None


def upgrade():
    # ── marketplace_listings ─────────────────────────────────────────────
    op.create_table(
        'marketplace_listings',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('environment_id', sa.Text, nullable=False),    # → agent_environments.id
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('category', sa.Text, server_default='automation'),
        sa.Column('tags', sa.Text),                               # JSON array
        sa.Column('creator_id', sa.Text, nullable=False),

        # Stats
        sa.Column('install_count', sa.Integer, server_default='0'),
        sa.Column('rating_sum', sa.Float, server_default='0'),
        sa.Column('review_count', sa.Integer, server_default='0'),

        # Lifecycle
        sa.Column('published_at', sa.Text, nullable=False),
        sa.Column('updated_at', sa.Text),
        sa.Column('state', sa.Text, server_default='active'),     # active | suspended | archived

        # Unique constraint: one listing per environment
        sa.UniqueConstraint('environment_id', name='uq_listing_env'),
    )

    # ── marketplace_reviews ──────────────────────────────────────────────
    op.create_table(
        'marketplace_reviews',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('listing_id', sa.Text, nullable=False),         # → marketplace_listings.id
        sa.Column('reviewer_id', sa.Text, nullable=False),
        sa.Column('rating', sa.Integer, nullable=False),          # 1-5
        sa.Column('comment', sa.Text),
        sa.Column('created_at', sa.Text, nullable=False),

        # One review per user per listing
        sa.UniqueConstraint('listing_id', 'reviewer_id', name='uq_review_user_listing'),
    )

    # ── Indexes ──────────────────────────────────────────────────────────
    op.create_index('ix_listings_category', 'marketplace_listings', ['category'])
    op.create_index('ix_listings_creator', 'marketplace_listings', ['creator_id'])
    op.create_index('ix_listings_state', 'marketplace_listings', ['state'])
    op.create_index('ix_reviews_listing', 'marketplace_reviews', ['listing_id'])


def downgrade():
    op.drop_index('ix_reviews_listing', 'marketplace_reviews')
    op.drop_index('ix_listings_state', 'marketplace_listings')
    op.drop_index('ix_listings_creator', 'marketplace_listings')
    op.drop_index('ix_listings_category', 'marketplace_listings')
    op.drop_table('marketplace_reviews')
    op.drop_table('marketplace_listings')
