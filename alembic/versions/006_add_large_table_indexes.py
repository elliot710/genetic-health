"""Add indexes on large reference tables for analysis performance.

thousand_genomes_variants (112M rows) had no rsid index — all rsid lookups
were sequential scans.  gnomad_variants (105M rows) had an rsid index but
no composite index on (chrom, pos, ref, alt) for position-based fallback
lookups.

Revision ID: 006_add_large_table_indexes
Revises: 005
Create Date: 2026-03-17
"""
from alembic import op

revision = "006_add_large_table_indexes"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_thousand_genomes_variants_rsid",
        "thousand_genomes_variants",
        ["rsid"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_gnomad_variants_chrom_pos_ref_alt",
        "gnomad_variants",
        ["chrom", "pos", "ref", "alt"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_gnomad_variants_chrom_pos_ref_alt", table_name="gnomad_variants")
    op.drop_index("ix_thousand_genomes_variants_rsid", table_name="thousand_genomes_variants")
