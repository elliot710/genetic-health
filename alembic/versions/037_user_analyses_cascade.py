"""cascade user deletion through genetic_analyses

Revision ID: 037_user_analyses_cascade
Revises: 036_hot_column_defaults
Create Date: 2026-07-10
"""
from alembic import op

revision = '037_user_analyses_cascade'
down_revision = '036_hot_column_defaults'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        'genetic_analyses_user_id_fkey', 'genetic_analyses', type_='foreignkey'
    )
    op.create_foreign_key(
        'genetic_analyses_user_id_fkey', 'genetic_analyses', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'genetic_analyses_user_id_fkey', 'genetic_analyses', type_='foreignkey'
    )
    op.create_foreign_key(
        'genetic_analyses_user_id_fkey', 'genetic_analyses', 'users',
        ['user_id'], ['id'],
    )
