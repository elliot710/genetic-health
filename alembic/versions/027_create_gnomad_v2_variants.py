"""create gnomad_v2_variants table

gnomAD v2.1.1 exome population AFs (GRCh37) — loaded from per-chromosome
bgz VCF files. Used for fast PG batch lookup instead of 609k tabix queries.

Revision ID: 027_create_gnomad_v2_variants
Revises: 026_drop_unused_large_indexes
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = '027_create_gnomad_v2_variants'
down_revision = '026_drop_unused_large_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gnomad_v2_variants',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('chrom', sa.String, nullable=False),
        sa.Column('pos', sa.Integer, nullable=False),
        sa.Column('ref', sa.String, nullable=False),
        sa.Column('alt', sa.String, nullable=False),
        sa.Column('rsid', sa.String),
        sa.Column('af', sa.Float),
        sa.Column('af_afr', sa.Float),
        sa.Column('af_amr', sa.Float),
        sa.Column('af_eas', sa.Float),
        sa.Column('af_nfe', sa.Float),
        sa.Column('af_sas', sa.Float),
        sa.Column('af_fin', sa.Float),
        sa.Column('af_asj', sa.Float),
        sa.Column('ac', sa.Integer),
        sa.Column('an', sa.Integer),
        sa.Column('data_source', sa.String, default='gnomad_v2_vcf'),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_gnomad_v2_rsid', 'gnomad_v2_variants', ['rsid'])
    op.create_index('ix_gnomad_v2_chrom_pos', 'gnomad_v2_variants', ['chrom', 'pos'])


def downgrade() -> None:
    op.drop_index('ix_gnomad_v2_chrom_pos', table_name='gnomad_v2_variants')
    op.drop_index('ix_gnomad_v2_rsid', table_name='gnomad_v2_variants')
    op.drop_table('gnomad_v2_variants')
