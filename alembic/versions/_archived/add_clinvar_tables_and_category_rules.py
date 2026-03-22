"""Add ClinVar PostgreSQL tables and category rules engine

Revision ID: f7e8d9c0b1a2
Revises: 862d84435bc1
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7e8d9c0b1a2'
down_revision = '862d84435bc1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- ClinVar variants (main lookup table) ---
    op.create_table(
        'clinvar_variants',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('rsid', sa.String(), nullable=False),
        sa.Column('allele_id', sa.String()),
        sa.Column('variation_id', sa.String()),
        sa.Column('clinical_significance', sa.String()),
        sa.Column('review_status', sa.String()),
        sa.Column('conditions', sa.String()),
        sa.Column('origin', sa.String()),
        sa.Column('variation_type', sa.String()),
        sa.Column('gene', sa.String()),
        sa.Column('gene_id', sa.String()),
        sa.Column('chromosome', sa.String()),
        sa.Column('start_pos', sa.Integer()),
        sa.Column('stop_pos', sa.Integer()),
        sa.Column('assembly', sa.String()),
        sa.Column('rcv_accession', sa.String()),
        sa.Column('phenotype_ids', sa.String()),
        sa.Column('hgvs_nucleotide', sa.String()),
        sa.Column('hgvs_protein', sa.String()),
        sa.Column('molecular_consequence', sa.String()),
        sa.Column('af_exac', sa.Float()),
        sa.Column('af_tgp', sa.Float()),
        sa.Column('af_esp', sa.Float()),
        sa.Column('oncogenicity', sa.String()),
        sa.Column('somatic_clinical_impact', sa.String()),
        sa.Column('conflicting_classifications', sa.Text()),
        sa.Column('data_source', sa.String(), server_default='tsv'),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_clinvar_variants_rsid', 'clinvar_variants', ['rsid'])
    op.create_index('ix_clinvar_variants_gene', 'clinvar_variants', ['gene'])
    op.create_index('ix_clinvar_variants_significance', 'clinvar_variants', ['clinical_significance'])
    op.create_index('ix_clinvar_variants_rsid_allele', 'clinvar_variants', ['rsid', 'allele_id'])

    # --- ClinVar gene conditions ---
    op.create_table(
        'clinvar_gene_conditions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('gene', sa.String(), nullable=False),
        sa.Column('disease_name', sa.String(), nullable=False),
        sa.Column('source_name', sa.String()),
        sa.Column('source_id', sa.String()),
        sa.Column('disease_mim', sa.String()),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_clinvar_gene_conditions_gene', 'clinvar_gene_conditions', ['gene'])

    # --- ClinVar gene stats ---
    op.create_table(
        'clinvar_gene_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('gene', sa.String(), nullable=False, unique=True),
        sa.Column('gene_id', sa.String()),
        sa.Column('total_submissions', sa.Integer(), server_default='0'),
        sa.Column('total_alleles', sa.Integer(), server_default='0'),
        sa.Column('pathogenic_likely_pathogenic', sa.Integer(), server_default='0'),
        sa.Column('uncertain_significance', sa.Integer(), server_default='0'),
        sa.Column('with_conflicts', sa.Integer(), server_default='0'),
        sa.Column('gene_mim', sa.String()),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_clinvar_gene_stats_gene', 'clinvar_gene_stats', ['gene'], unique=True)

    # --- Category rules ---
    op.create_table(
        'category_rules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('rule_type', sa.String(), nullable=False),
        sa.Column('rule_value', sa.Text(), nullable=False),
        sa.Column('priority', sa.Integer(), server_default='50'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('mapping_data_template', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_category_rules_cat_type', 'category_rules', ['category', 'rule_type'])


def downgrade() -> None:
    op.drop_table('category_rules')
    op.drop_table('clinvar_gene_stats')
    op.drop_table('clinvar_gene_conditions')
    op.drop_table('clinvar_variants')
