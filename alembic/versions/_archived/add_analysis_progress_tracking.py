"""add_analysis_progress_tracking

Revision ID: add_progress_tracking
Revises: e19067c6122a
Create Date: 2025-08-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_progress_tracking'
down_revision = 'e19067c6122a'
branch_labels = None
depends_on = None


def upgrade():
    # Add progress tracking columns to genetic_analyses table
    op.add_column('genetic_analyses', sa.Column('analysis_status', sa.String(), nullable=True, server_default='pending'))
    op.add_column('genetic_analyses', sa.Column('progress_percentage', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('genetic_analyses', sa.Column('total_variants', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('genetic_analyses', sa.Column('processed_variants', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('genetic_analyses', sa.Column('current_step', sa.String(), nullable=True, server_default='initializing'))
    op.add_column('genetic_analyses', sa.Column('estimated_completion', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Remove progress tracking columns
    op.drop_column('genetic_analyses', 'estimated_completion')
    op.drop_column('genetic_analyses', 'current_step')
    op.drop_column('genetic_analyses', 'processed_variants')
    op.drop_column('genetic_analyses', 'total_variants')
    op.drop_column('genetic_analyses', 'progress_percentage')
    op.drop_column('genetic_analyses', 'analysis_status')