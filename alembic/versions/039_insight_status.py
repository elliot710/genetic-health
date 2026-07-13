"""add insight_status column to genetic_analyses

Revision ID: 039_insight_status
Revises: 038_analysis_completed_at
Create Date: 2026-07-13

Per-category insight-generation outcome (which generators produced rows, which
were empty, which failed), so a partially-generated dashboard is an honest,
visible state rather than a silent gap.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '039_insight_status'
down_revision: Union[str, Sequence[str], None] = '038_analysis_completed_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('genetic_analyses', sa.Column('insight_status', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('genetic_analyses', 'insight_status')
