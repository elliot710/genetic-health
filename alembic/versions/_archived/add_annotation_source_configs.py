"""add annotation_source_configs table

Revision ID: add_annotation_source_configs
Revises: None
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_annotation_source_configs'
down_revision = None  # Set appropriately
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'annotation_source_configs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source_name', sa.String(), nullable=False, unique=True),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('rate_limit', sa.Float(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_annotation_source_configs_source_name', 'annotation_source_configs', ['source_name'], unique=True)

    # Seed default sources
    op.execute("""
        INSERT INTO annotation_source_configs (source_name, display_name, is_enabled, description, rate_limit, priority) VALUES
        ('ensembl', 'Ensembl VEP', true, 'Variant Effect Predictor — gene consequences, transcript impact, regulatory annotations', 15.0, 1),
        ('clinvar', 'ClinVar (NCBI)', true, 'Clinical significance classifications, disease associations, review status', 10.0, 2),
        ('clinpgx', 'ClinPGx', true, 'Pharmacogenomic annotations — drug-gene interactions and dosing guidelines', 1.0, 3),
        ('snpedia', 'SNPedia', true, 'Community-curated variant wiki — genotype-phenotype associations and research summaries', 2.0, 4)
    """)


def downgrade() -> None:
    op.drop_index('ix_annotation_source_configs_source_name', table_name='annotation_source_configs')
    op.drop_table('annotation_source_configs')
