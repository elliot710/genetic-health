"""add ai_insight_cache table

Revision ID: 017_ai_insight_cache
Revises: 016_worker_jobs
Create Date: 2026-03-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '017_ai_insight_cache'
down_revision: Union[str, Sequence[str], None] = '016_worker_jobs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_insight_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cache_key', sa.String(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('provider', sa.String(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ai_insight_cache_key', 'ai_insight_cache', ['cache_key'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_ai_insight_cache_key', table_name='ai_insight_cache')
    op.drop_table('ai_insight_cache')
