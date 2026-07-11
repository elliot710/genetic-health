"""add completed_at to genetic_analyses

Revision ID: 038_analysis_completed_at
Revises: 037_user_analyses_cascade
Create Date: 2026-07-11
"""
import sqlalchemy as sa
from alembic import op

revision = '038_analysis_completed_at'
down_revision = '037_user_analyses_cascade'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'genetic_analyses',
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('genetic_analyses', 'completed_at')
