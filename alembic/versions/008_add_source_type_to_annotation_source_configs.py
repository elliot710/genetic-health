"""Add source_type to annotation_source_configs

Revision ID: 008_add_source_type
Revises: 007_merge_add_gnomad_tx
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = "008_add_source_type"
down_revision = "007_merge_add_gnomad_tx"
branch_labels = None
depends_on = None

# Map every known source_name → source_type.
# 'hybrid' = raw files exist in data_sources/ AND data is also ETL-imported into PostgreSQL.
_SOURCE_TYPES = {
    # Third-party HTTP APIs
    "ensembl": "api",
    "clinvar": "api",
    "clinpgx": "api",
    "snpedia": "api",
    # Local files only (tabix / SQLite cache in data_sources/)
    "alpha_missense": "file",
    "ensembl_vep": "file",
    "gnomad_tx": "file",
    # File + PostgreSQL hybrid (raw files in data_sources/ + ETL-imported into PG)
    "gnomad": "hybrid",          # data_sources/gnomad/ (SQLite/tabix primary) + optional PG import
    "clinvar_local": "hybrid",   # data_sources/clinvar/ (VCF/TSV) → imported into PG clinvar_variants
    "thousand_genomes": "hybrid", # data_sources/ensembl/.../1000GENOMES-phase_3.vcf.gz → PG import
    # Google BigQuery
    "chembl": "bigquery",
    "fda_drug": "bigquery",
    "alphafold": "bigquery",
}


def upgrade() -> None:
    op.add_column(
        "annotation_source_configs",
        sa.Column("source_type", sa.String(), nullable=True),
    )

    conn = op.get_bind()

    # Backfill / update source_type for all known sources
    for source_name, source_type in _SOURCE_TYPES.items():
        conn.execute(
            sa.text(
                "UPDATE annotation_source_configs "
                "SET source_type = :st "
                "WHERE source_name = :sn"
            ),
            {"st": source_type, "sn": source_name},
        )

    # Default any remaining unknown rows to 'api'
    conn.execute(
        sa.text(
            "UPDATE annotation_source_configs SET source_type = 'api' WHERE source_type IS NULL"
        )
    )

    # Insert gnomad_tx if it doesn't exist yet
    conn.execute(
        sa.text("""
            INSERT INTO annotation_source_configs
                (source_name, display_name, is_enabled, source_type, description, rate_limit, priority)
            VALUES (
                'gnomad_tx',
                'gnomAD tx-annotated',
                true,
                'file',
                'gnomAD transcript annotation + GTEx tissue expression — data_sources/gnomad/all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz',
                NULL,
                8
            )
            ON CONFLICT (source_name) DO UPDATE
                SET source_type = 'file',
                    display_name = EXCLUDED.display_name,
                    description  = EXCLUDED.description
        """)
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM annotation_source_configs WHERE source_name = 'gnomad_tx'")
    )
    op.drop_column("annotation_source_configs", "source_type")
