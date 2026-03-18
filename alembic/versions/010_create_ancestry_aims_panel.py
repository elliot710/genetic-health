"""Create ancestry_aims_panel table for fast ancestry estimation.

Pre-computes Ancestry-Informative Markers (AIMs) from thousand_genomes_variants.
These are variants with high allele-frequency differentiation (FST proxy > 0.40)
across the 5 1000G super-populations (AFR, AMR, EAS, EUR, SAS).

This replaces the previous approach of scanning all 112M 1000G rows at query
time. The AIMs panel is ~200K rows, fits in memory, and makes ancestry
generation instant.

Revision ID: 010_ancestry_aims
Revises: 009_reset_broken_am_gtx
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = "010_ancestry_aims"
down_revision = "009_reset_broken_am_gtx"
branch_labels = None
depends_on = None

# Minimum allele-frequency spread across 5 super-populations to qualify as
# an Ancestry-Informative Marker.  0.40 yields ~200K markers — enough for
# high-confidence estimates while keeping the table small.
FST_THRESHOLD = 0.40


def upgrade():
    op.create_table(
        "ancestry_aims_panel",
        sa.Column("rsid", sa.String, primary_key=True),
        sa.Column("af_afr", sa.Float, nullable=False),
        sa.Column("af_amr", sa.Float, nullable=False),
        sa.Column("af_eas", sa.Float, nullable=False),
        sa.Column("af_eur", sa.Float, nullable=False),
        sa.Column("af_sas", sa.Float, nullable=False),
        sa.Column("fst_delta", sa.Float, nullable=False),
    )

    # Populate from thousand_genomes_variants if it exists and has data.
    # DISTINCT ON (rsid) keeps the row with the highest differentiation
    # when the same rsid appears multiple times (multi-allelic sites).
    op.execute(f"""
        INSERT INTO ancestry_aims_panel (rsid, af_afr, af_amr, af_eas, af_eur, af_sas, fst_delta)
        SELECT DISTINCT ON (rsid)
            rsid, af_afr, af_amr, af_eas, af_eur, af_sas,
            greatest(af_afr, af_amr, af_eas, af_eur, af_sas)
              - least(af_afr, af_amr, af_eas, af_eur, af_sas) AS fst_delta
        FROM thousand_genomes_variants
        WHERE rsid IS NOT NULL
          AND rsid LIKE 'rs%'
          AND af_afr IS NOT NULL
          AND af_amr IS NOT NULL
          AND af_eas IS NOT NULL
          AND af_eur IS NOT NULL
          AND af_sas IS NOT NULL
          AND greatest(af_afr, af_amr, af_eas, af_eur, af_sas)
              - least(af_afr, af_amr, af_eas, af_eur, af_sas) > {FST_THRESHOLD}
        ORDER BY rsid,
                 greatest(af_afr, af_amr, af_eas, af_eur, af_sas)
                   - least(af_afr, af_amr, af_eas, af_eur, af_sas) DESC
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table("ancestry_aims_panel")
