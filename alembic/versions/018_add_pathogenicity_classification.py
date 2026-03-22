"""Add pathogenicity_classification column to health_risks

Revision ID: 018_pathogenicity_classification
Revises: 017_ai_insight_cache
Create Date: 2026-03-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '018_pathogenicity_classification'
down_revision: Union[str, Sequence[str], None] = '017_ai_insight_cache'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('health_risks', sa.Column('pathogenicity_classification', sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column('health_risks', 'pathogenicity_classification')
