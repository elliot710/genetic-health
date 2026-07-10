"""add gwas_catalog and clingen columns + ETL tables

Revision ID: 032_add_gwas_clingen_sources
Revises: 031_add_job_logs_to_worker_jobs
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '032_add_gwas_clingen_sources'
down_revision = '031_add_job_logs_to_worker_jobs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'shared_variant_annotations',
        sa.Column('gwas_catalog_data', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'shared_variant_annotations',
        sa.Column('clingen_data', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'shared_variant_annotations',
        sa.Column('open_targets_data', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )

    op.create_table(
        'gwas_catalog_associations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('rsid', sa.String(32), nullable=True, index=True),
        sa.Column('pubmed_id', sa.String(20), nullable=True),
        sa.Column('study_accession', sa.String(20), nullable=True),
        sa.Column('trait', sa.Text(), nullable=True),
        sa.Column('mapped_trait', sa.Text(), nullable=True),
        sa.Column('mapped_trait_uri', sa.Text(), nullable=True),
        sa.Column('reported_genes', sa.Text(), nullable=True),
        sa.Column('mapped_genes', sa.Text(), nullable=True),
        sa.Column('p_value', sa.Float(), nullable=True),
        sa.Column('p_value_mlog', sa.Float(), nullable=True),
        sa.Column('or_beta', sa.Float(), nullable=True),
        sa.Column('ci_text', sa.Text(), nullable=True),
        sa.Column('risk_allele_frequency', sa.Float(), nullable=True),
        sa.Column('strongest_snp_risk_allele', sa.Text(), nullable=True),
        sa.Column('chromosome', sa.String(5), nullable=True),
        sa.Column('chromosome_position', sa.Integer(), nullable=True),
        sa.Column('context', sa.Text(), nullable=True),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_gwas_catalog_rsid', 'gwas_catalog_associations', ['rsid'])

    op.create_table(
        'clingen_gene_validity',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('gene_symbol', sa.String(64), nullable=False, index=True),
        sa.Column('gene_hgnc_id', sa.String(32), nullable=True),
        sa.Column('disease_label', sa.Text(), nullable=True),
        sa.Column('disease_mondo_id', sa.String(32), nullable=True),
        sa.Column('moi', sa.String(64), nullable=True),
        sa.Column('classification', sa.String(64), nullable=True),
        sa.Column('classification_date', sa.String(32), nullable=True),
        sa.Column('gcep', sa.Text(), nullable=True),
        sa.Column('report_url', sa.Text(), nullable=True),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_clingen_gene_symbol', 'clingen_gene_validity', ['gene_symbol'])


def downgrade() -> None:
    op.drop_column('shared_variant_annotations', 'gwas_catalog_data')
    op.drop_column('shared_variant_annotations', 'clingen_data')
    op.drop_column('shared_variant_annotations', 'open_targets_data')
    op.drop_index('ix_gwas_catalog_rsid', 'gwas_catalog_associations')
    op.drop_table('gwas_catalog_associations')
    op.drop_index('ix_clingen_gene_symbol', 'clingen_gene_validity')
    op.drop_table('clingen_gene_validity')
