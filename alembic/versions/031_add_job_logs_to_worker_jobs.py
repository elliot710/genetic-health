"""Add job_logs column to worker_jobs

Revision ID: 031
Revises: 030
"""
from alembic import op
import sqlalchemy as sa

revision = '031_add_job_logs_to_worker_jobs'
down_revision = '030_add_inferred_sex'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('worker_jobs', sa.Column('job_logs', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('worker_jobs', 'job_logs')
