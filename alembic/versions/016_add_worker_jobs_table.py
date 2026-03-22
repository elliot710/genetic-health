"""add worker_jobs table

Revision ID: 016_worker_jobs
Revises: 015_sources_vm
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '016_worker_jobs'
down_revision: Union[str, Sequence[str], None] = '015_sources_vm'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'worker_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_worker_jobs_status', 'worker_jobs', ['status'])
    op.create_index('ix_worker_jobs_job_type', 'worker_jobs', ['job_type'])


def downgrade() -> None:
    op.drop_index('ix_worker_jobs_job_type', table_name='worker_jobs')
    op.drop_index('ix_worker_jobs_status', table_name='worker_jobs')
    op.drop_table('worker_jobs')
