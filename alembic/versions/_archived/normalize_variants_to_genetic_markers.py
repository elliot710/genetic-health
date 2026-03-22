"""normalize_variants_to_genetic_markers

Populates the genetic_markers catalog from existing analysis_variants data,
adds marker_id FK to analysis_variants and shared_variant_annotations,
and drops denormalized columns from analysis_variants.

Revision ID: normalize_markers_001
Revises: shared_annotations_001
Create Date: 2025-08-27 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'normalize_markers_001'
down_revision = ('shared_annotations_001', 'f1a2b3c4d5e6')
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ── Step 1: Populate genetic_markers from existing analysis_variants ──
    conn.execute(sa.text("""
        INSERT INTO genetic_markers (rsid, chromosome, position, ref_allele, alt_alleles, upload_count)
        SELECT
            rsid,
            MIN(chromosome)  AS chromosome,
            MIN(position)    AS position,
            MIN(ref_allele)  AS ref_allele,
            MIN(alt_allele)  AS alt_alleles,
            COUNT(*)         AS upload_count
        FROM analysis_variants
        WHERE rsid IS NOT NULL
        GROUP BY rsid
        ON CONFLICT (rsid) DO UPDATE
            SET upload_count = genetic_markers.upload_count + EXCLUDED.upload_count
    """))

    # ── Step 2: Add marker_id column to analysis_variants (nullable first) ──
    op.add_column('analysis_variants',
        sa.Column('marker_id', sa.Integer(), nullable=True)
    )

    # ── Step 3: Populate marker_id from genetic_markers via rsid join ──
    conn.execute(sa.text("""
        UPDATE analysis_variants av
        SET marker_id = gm.id
        FROM genetic_markers gm
        WHERE av.rsid = gm.rsid
    """))

    # For rows without an rsid, create a synthetic marker using chr:pos
    conn.execute(sa.text("""
        INSERT INTO genetic_markers (rsid, chromosome, position, ref_allele, alt_alleles, upload_count)
        SELECT
            'chr' || chromosome || ':' || position AS rsid,
            chromosome,
            position,
            COALESCE(ref_allele, '.'),
            COALESCE(alt_allele, '.'),
            COUNT(*)
        FROM analysis_variants
        WHERE marker_id IS NULL AND chromosome IS NOT NULL
        GROUP BY chromosome, position, ref_allele, alt_allele
        ON CONFLICT (rsid) DO UPDATE
            SET upload_count = genetic_markers.upload_count + EXCLUDED.upload_count
    """))

    # Update remaining NULL marker_ids
    conn.execute(sa.text("""
        UPDATE analysis_variants av
        SET marker_id = gm.id
        FROM genetic_markers gm
        WHERE av.marker_id IS NULL
          AND gm.rsid = 'chr' || av.chromosome || ':' || av.position
    """))

    # Make marker_id NOT NULL and add FK
    op.alter_column('analysis_variants', 'marker_id', nullable=False)
    op.create_foreign_key(
        'fk_analysis_variants_marker_id',
        'analysis_variants', 'genetic_markers',
        ['marker_id'], ['id']
    )
    op.create_index('ix_analysis_variants_analysis_marker', 'analysis_variants', ['analysis_id', 'marker_id'])

    # ── Step 4: Drop old denormalized columns from analysis_variants ──
    op.drop_column('analysis_variants', 'rsid')
    op.drop_column('analysis_variants', 'chromosome')
    op.drop_column('analysis_variants', 'position')
    op.drop_column('analysis_variants', 'ref_allele')
    op.drop_column('analysis_variants', 'alt_allele')

    # ── Step 5: Add marker_id to shared_variant_annotations ──
    op.add_column('shared_variant_annotations',
        sa.Column('marker_id', sa.Integer(), nullable=True)
    )

    # Populate marker_id from genetic_markers via rsid join
    conn.execute(sa.text("""
        UPDATE shared_variant_annotations sva
        SET marker_id = gm.id
        FROM genetic_markers gm
        WHERE sva.rsid = gm.rsid
    """))

    # Make NOT NULL only if there are matching markers; otherwise leave nullable
    # for annotations that reference markers not yet in the catalog
    op.create_foreign_key(
        'fk_shared_variant_annotations_marker_id',
        'shared_variant_annotations', 'genetic_markers',
        ['marker_id'], ['id']
    )
    op.create_index('ix_shared_variant_annotations_marker_id', 'shared_variant_annotations', ['marker_id'], unique=True)


def downgrade():
    # ── Reverse Step 5 ──
    op.drop_index('ix_shared_variant_annotations_marker_id', table_name='shared_variant_annotations')
    op.drop_constraint('fk_shared_variant_annotations_marker_id', 'shared_variant_annotations', type_='foreignkey')
    op.drop_column('shared_variant_annotations', 'marker_id')

    # ── Reverse Step 4: Re-add columns to analysis_variants ──
    op.add_column('analysis_variants', sa.Column('rsid', sa.String(), nullable=True))
    op.add_column('analysis_variants', sa.Column('chromosome', sa.String(), nullable=True))
    op.add_column('analysis_variants', sa.Column('position', sa.Integer(), nullable=True))
    op.add_column('analysis_variants', sa.Column('ref_allele', sa.String(), nullable=True))
    op.add_column('analysis_variants', sa.Column('alt_allele', sa.String(), nullable=True))

    # Re-populate from genetic_markers
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE analysis_variants av
        SET rsid = gm.rsid,
            chromosome = gm.chromosome,
            position = gm.position,
            ref_allele = gm.ref_allele,
            alt_allele = gm.alt_alleles
        FROM genetic_markers gm
        WHERE av.marker_id = gm.id
    """))

    # ── Reverse Steps 2-3 ──
    op.drop_index('ix_analysis_variants_analysis_marker', table_name='analysis_variants')
    op.drop_constraint('fk_analysis_variants_marker_id', 'analysis_variants', type_='foreignkey')
    op.drop_column('analysis_variants', 'marker_id')
