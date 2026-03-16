"""Add 1000 Genomes Phase 3 variants table and thousand_genomes_data column

Revision ID: add_1kg_tables_001
Revises: dedup_variant_ann
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_1kg_tables_001'
down_revision = 'dedup_variant_ann'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add thousand_genomes_data column to shared_variant_annotations
    op.add_column('shared_variant_annotations',
                  sa.Column('thousand_genomes_data', sa.JSON(), nullable=True))

    # Create thousand_genomes_variants table
    op.create_table(
        'thousand_genomes_variants',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('chrom', sa.String(), nullable=False),
        sa.Column('pos', sa.Integer(), nullable=False),
        sa.Column('ref', sa.String(), nullable=False),
        sa.Column('alt', sa.String(), nullable=False),
        sa.Column('rsid', sa.String()),
        sa.Column('variant_type', sa.String()),
        sa.Column('minor_allele', sa.String()),
        sa.Column('maf', sa.Float()),
        sa.Column('mac', sa.Integer()),
        sa.Column('ancestral_allele', sa.String()),
        sa.Column('af_afr', sa.Float()),
        sa.Column('af_amr', sa.Float()),
        sa.Column('af_eas', sa.Float()),
        sa.Column('af_eur', sa.Float()),
        sa.Column('af_sas', sa.Float()),
        sa.Column('is_clinvar', sa.Boolean(), server_default='false'),
        sa.Column('is_1000g', sa.Boolean(), server_default='false'),
        sa.Column('data_source', sa.String(), server_default='ensembl_vcf'),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_1kg_rsid', 'thousand_genomes_variants', ['rsid'])
    op.create_index('ix_1kg_chrom_pos', 'thousand_genomes_variants', ['chrom', 'pos'])
    op.create_index('ix_1kg_chrom_pos_ref_alt', 'thousand_genomes_variants',
                    ['chrom', 'pos', 'ref', 'alt'], unique=True)
    op.create_index('ix_1kg_maf', 'thousand_genomes_variants', ['maf'])


def downgrade() -> None:
    op.drop_table('thousand_genomes_variants')
    op.drop_column('shared_variant_annotations', 'thousand_genomes_data')
