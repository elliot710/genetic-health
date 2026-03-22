"""add job_logs column to genetic_analyses

Revision ID: cf76f2735c9e
Revises: 005
Create Date: 2026-03-16 19:36:52.012994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf76f2735c9e'
down_revision: Union[str, Sequence[str], None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('genetic_analyses', sa.Column('job_logs', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('genetic_analyses', 'job_logs')
