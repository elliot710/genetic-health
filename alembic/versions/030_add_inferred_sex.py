"""Add inferred_sex column to genetic_analyses

Revision ID: 030
Revises: 029
"""
from alembic import op
import sqlalchemy as sa

revision = '030_add_inferred_sex'
down_revision = '029_add_autism_gene_mappings'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'genetic_analyses',
        sa.Column('inferred_sex', sa.String(10), nullable=True),
    )


def downgrade():
    op.drop_column('genetic_analyses', 'inferred_sex')
