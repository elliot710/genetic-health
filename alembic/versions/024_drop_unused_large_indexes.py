"""drop unused large indexes

These 6 indexes had 0 scans since last server restart and consumed 17.4 GB
of disk space, causing excessive OS page cache pressure (reported as high
container memory usage in cAdvisor).

The active lookup pattern uses:
  - ix_1kg_rsid (609k scans) — kept
  - ix_1kg_chrom_pos (167 scans) — kept
  - gnomad chrom_pos_ref_alt / rsid — kept

Revision ID: 024
Revises: 023
Create Date: 2026-03-27
"""

from alembic import op

revision = '024'
down_revision = '023_add_worker_jobs_refreshed_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1000G indexes — 0 scans, 9.7 GB combined
    op.drop_index('ix_thousand_genomes_variants_rsid', table_name='thousand_genomes_variants', if_exists=True, postgresql_concurrently=True)
    op.drop_index('ix_1kg_chrom_pos_ref_alt', table_name='thousand_genomes_variants', if_exists=True, postgresql_concurrently=True)
    op.drop_index('ix_1kg_maf', table_name='thousand_genomes_variants', if_exists=True, postgresql_concurrently=True)

    # gnomAD indexes — 0 scans, 7.4 GB combined
    op.drop_index('ix_gnomad_variants_variant_id', table_name='gnomad_variants', if_exists=True, postgresql_concurrently=True)
    op.drop_index('ix_gnomad_variants_cadd_phred', table_name='gnomad_variants', if_exists=True, postgresql_concurrently=True)
    op.drop_index('ix_gnomad_variants_gene', table_name='gnomad_variants', if_exists=True, postgresql_concurrently=True)


def downgrade() -> None:
    # Recreate if needed — these are large so downgrade is intentionally slow
    op.create_index('ix_1kg_maf', 'thousand_genomes_variants', ['maf'], postgresql_concurrently=True)
    op.create_index('ix_1kg_chrom_pos_ref_alt', 'thousand_genomes_variants', ['chrom', 'pos', 'ref', 'alt'], postgresql_concurrently=True)
    op.create_index('ix_thousand_genomes_variants_rsid', 'thousand_genomes_variants', ['rsid'], postgresql_concurrently=True)
    op.create_index('ix_gnomad_variants_gene', 'gnomad_variants', ['gene'], postgresql_concurrently=True)
    op.create_index('ix_gnomad_variants_cadd_phred', 'gnomad_variants', ['cadd_phred'], postgresql_concurrently=True)
    op.create_index('ix_gnomad_variants_variant_id', 'gnomad_variants', ['variant_id'], postgresql_concurrently=True)
