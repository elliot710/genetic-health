"""Drop unused indexes on gnomad_variants and thousand_genomes_variants.

These 8 indexes consume ~21 GB combined but have 0 or negligible scans.
The only indexes kept are the rsid lookups (both active at ~609K scans)
and the primary keys.

Savings summary:
  ix_gnomad_variants_variant_id          4.5 GB   0 scans
  ix_gnomad_variants_chrom_pos_ref_alt   3.9 GB   0 scans
  ix_gnomad_variants_cadd_phred          2.3 GB   0 scans
  ix_gnomad_variants_chrom_pos           1.7 GB   0 scans
  ix_gnomad_variants_gene                705 MB   0 scans
  ix_1kg_chrom_pos_ref_alt               3.5 GB   0 scans
  ix_1kg_maf                             2.4 GB   0 scans
  ix_1kg_chrom_pos                       2.2 GB  84 scans
  ──────────────────────────────────────────────
  Total freed:                          ~21 GB

Revision ID: 003_drop_unused_indexes
Revises: 002_add_insight_indexes
Create Date: 2026-03-16
"""
from alembic import op


revision = '003_drop_unused_indexes'
down_revision = '002_add_insight_indexes'
branch_labels = None
depends_on = None

# (index_name, table_name, columns, unique, kwargs)
_INDEXES_TO_DROP = [
    # gnomad_variants — keep only rsid + pkey
    ('ix_gnomad_variants_variant_id',        'gnomad_variants', ['variant_id'], False, {}),
    ('ix_gnomad_variants_chrom_pos_ref_alt',  'gnomad_variants', ['chrom', 'pos', 'ref', 'alt'], True, {}),
    ('ix_gnomad_variants_cadd_phred',         'gnomad_variants', ['cadd_phred'], False, {}),
    ('ix_gnomad_variants_chrom_pos',          'gnomad_variants', ['chrom', 'pos'], False, {}),
    ('ix_gnomad_variants_gene',               'gnomad_variants', ['gene'], False, {}),
    # thousand_genomes_variants — keep only rsid + pkey
    ('ix_1kg_chrom_pos_ref_alt',              'thousand_genomes_variants', ['chrom', 'pos', 'ref', 'alt'], True, {}),
    ('ix_1kg_maf',                            'thousand_genomes_variants', ['maf'], False, {}),
    ('ix_1kg_chrom_pos',                      'thousand_genomes_variants', ['chrom', 'pos'], False, {}),
]


def upgrade():
    for name, table, columns, unique, kwargs in _INDEXES_TO_DROP:
        op.drop_index(name, table_name=table, if_exists=True)


def downgrade():
    for name, table, columns, unique, kwargs in reversed(_INDEXES_TO_DROP):
        op.create_index(name, table, columns, unique=unique, **kwargs)
