"""Add structured ancestry data columns

Revision ID: add_ancestry_columns_001
Revises: add_1kg_tables_001
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_ancestry_columns_001'
down_revision = 'add_1kg_tables_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ancestry_results',
                  sa.Column('composition', sa.JSON(), nullable=True))
    op.add_column('ancestry_results',
                  sa.Column('maternal_haplogroup', sa.JSON(), nullable=True))
    op.add_column('ancestry_results',
                  sa.Column('paternal_haplogroup', sa.JSON(), nullable=True))
    op.add_column('ancestry_results',
                  sa.Column('neanderthal_variants', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('ancestry_results', 'neanderthal_variants')
    op.drop_column('ancestry_results', 'paternal_haplogroup')
    op.drop_column('ancestry_results', 'maternal_haplogroup')
    op.drop_column('ancestry_results', 'composition')
