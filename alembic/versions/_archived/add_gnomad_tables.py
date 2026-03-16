"""Add gnomAD variant tables and gnomad_data column

Revision ID: gnomad_tables_001
Revises: f7e8d9c0b1a2
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'gnomad_tables_001'
down_revision = 'f7e8d9c0b1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add gnomad_data column to shared_variant_annotations
    op.add_column('shared_variant_annotations',
                  sa.Column('gnomad_data', sa.JSON(), nullable=True))

    # Create gnomad_variants table
    op.create_table(
        'gnomad_variants',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('chrom', sa.String(), nullable=False),
        sa.Column('pos', sa.Integer(), nullable=False),
        sa.Column('ref', sa.String(), nullable=False),
        sa.Column('alt', sa.String(), nullable=False),
        sa.Column('rsid', sa.String()),
        sa.Column('variant_id', sa.String()),
        sa.Column('variant_type', sa.String()),
        sa.Column('filter_status', sa.String()),
        sa.Column('af', sa.Float()),
        sa.Column('ac', sa.Integer()),
        sa.Column('an', sa.Integer()),
        sa.Column('nhomalt', sa.Integer()),
        sa.Column('af_afr', sa.Float()),
        sa.Column('af_ami', sa.Float()),
        sa.Column('af_amr', sa.Float()),
        sa.Column('af_asj', sa.Float()),
        sa.Column('af_eas', sa.Float()),
        sa.Column('af_fin', sa.Float()),
        sa.Column('af_mid', sa.Float()),
        sa.Column('af_nfe', sa.Float()),
        sa.Column('af_sas', sa.Float()),
        sa.Column('af_remaining', sa.Float()),
        sa.Column('cadd_raw', sa.Float()),
        sa.Column('cadd_phred', sa.Float()),
        sa.Column('sift_cat', sa.String()),
        sa.Column('sift_val', sa.Float()),
        sa.Column('polyphen_cat', sa.String()),
        sa.Column('polyphen_val', sa.Float()),
        sa.Column('phylop_primate', sa.Float()),
        sa.Column('phylop_mammal', sa.Float()),
        sa.Column('phylop_vertebrate', sa.Float()),
        sa.Column('splice_ai_acc_gain', sa.Float()),
        sa.Column('splice_ai_acc_loss', sa.Float()),
        sa.Column('splice_ai_don_gain', sa.Float()),
        sa.Column('splice_ai_don_loss', sa.Float()),
        sa.Column('gene', sa.String()),
        sa.Column('consequence', sa.String()),
        sa.Column('impact', sa.String()),
        sa.Column('hgvsc', sa.String()),
        sa.Column('hgvsp', sa.String()),
        sa.Column('annotations', sa.JSON()),
        sa.Column('data_source', sa.String(), server_default='tsv'),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_gnomad_variants_rsid', 'gnomad_variants', ['rsid'])
    op.create_index('ix_gnomad_variants_chrom_pos', 'gnomad_variants', ['chrom', 'pos'])
    op.create_index('ix_gnomad_variants_chrom_pos_ref_alt', 'gnomad_variants',
                    ['chrom', 'pos', 'ref', 'alt'], unique=True)
    op.create_index('ix_gnomad_variants_gene', 'gnomad_variants', ['gene'])
    op.create_index('ix_gnomad_variants_variant_id', 'gnomad_variants', ['variant_id'])

    # Create gnomad_gene_constraints table
    op.create_table(
        'gnomad_gene_constraints',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('gene', sa.String(), nullable=False, unique=True),
        sa.Column('transcript', sa.String()),
        sa.Column('pli', sa.Float()),
        sa.Column('loeuf', sa.Float()),
        sa.Column('mis_z', sa.Float()),
        sa.Column('syn_z', sa.Float()),
        sa.Column('obs_lof', sa.Integer()),
        sa.Column('exp_lof', sa.Float()),
        sa.Column('obs_mis', sa.Integer()),
        sa.Column('exp_mis', sa.Float()),
        sa.Column('obs_syn', sa.Integer()),
        sa.Column('exp_syn', sa.Float()),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_gnomad_gene_constraints_gene', 'gnomad_gene_constraints', ['gene'])


def downgrade() -> None:
    op.drop_table('gnomad_gene_constraints')
    op.drop_table('gnomad_variants')
    op.drop_column('shared_variant_annotations', 'gnomad_data')
