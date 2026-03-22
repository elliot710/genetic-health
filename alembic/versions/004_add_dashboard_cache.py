"""Add dashboard_cache table for pre-computed dashboard JSON.

Turns the 18-query dashboard-data endpoint into a single row read.
Refreshed after each analysis completion.

Revision ID: 004_add_dashboard_cache
Revises: 003_drop_unused_indexes
Create Date: 2026-03-16
"""
import sqlalchemy as sa
from alembic import op


revision = '004_add_dashboard_cache'
down_revision = '003_drop_unused_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dashboard_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dashboard_json', sa.JSON(), nullable=False),
        sa.Column('analysis_fingerprint', sa.String(), nullable=True),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_dashboard_cache_user_id', 'dashboard_cache', ['user_id'], unique=True)


def downgrade():
    op.drop_index('ix_dashboard_cache_user_id', table_name='dashboard_cache')
    op.drop_table('dashboard_cache')
