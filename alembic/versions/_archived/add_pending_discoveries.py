"""add pending_discoveries table

Revision ID: add_pending_discoveries
Revises: add_variant_lookup_cache
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_pending_discoveries'
down_revision = None  # Set appropriately
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pending_discoveries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('discovery_type', sa.String(), nullable=False),
        sa.Column('rsid', sa.String(), nullable=False),
        sa.Column('gene', sa.String(), nullable=True),
        sa.Column('panel_id', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('map_type', sa.String(), nullable=True),
        sa.Column('mapping_category', sa.String(), nullable=True),
        sa.Column('mapping_data', sa.JSON(), nullable=True),
        sa.Column('source_data', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(), nullable=True),
        sa.Column('discovered_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('lookup_count', sa.Integer(), server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_pending_discoveries_rsid', 'pending_discoveries', ['rsid'])
    op.create_index('ix_pending_discoveries_type_rsid_panel', 'pending_discoveries',
                     ['discovery_type', 'rsid', 'panel_id'], unique=True)
    op.create_index('ix_pending_discoveries_status', 'pending_discoveries', ['status'])


def downgrade() -> None:
    op.drop_table('pending_discoveries')
