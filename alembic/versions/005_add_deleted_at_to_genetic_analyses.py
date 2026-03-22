"""add_deleted_at_to_genetic_analyses

Revision ID: 005
Revises: 004_add_dashboard_cache
Create Date: 2026-03-16 17:06:19.375610

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, Sequence[str], None] = '004_add_dashboard_cache'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'genetic_analyses',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_genetic_analyses_deleted_at', 'genetic_analyses', ['deleted_at'])


def downgrade() -> None:
    op.drop_index('ix_genetic_analyses_deleted_at', table_name='genetic_analyses')
    op.drop_column('genetic_analyses', 'deleted_at')
