"""Add missing analysis_id indexes on insight tables and remove duplicate index.

All 14 insight tables have a FK on analysis_id but no index.
The dashboard-data endpoint queries each of these with WHERE analysis_id = ?,
causing sequential scans. Adding these indexes turns those into index lookups.

Also removes the duplicate ix_ensembl_genes_symbol (same column as
ix_ensembl_genes_gene_symbol which is auto-created by index=True on the column).

Revision ID: 002_add_insight_indexes
Revises: 001_baseline
Create Date: 2026-03-16
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "002_add_insight_indexes"
down_revision = "001_baseline"
branch_labels = None
depends_on = None

# Insight tables that need analysis_id indexes
INSIGHT_TABLES = [
    "health_risks",
    "drug_responses",
    "physical_traits",
    "nutrition_traits",
    "sports_performance",
    "cognitive_profiles",
    "personality_traits",
    "ancestry_results",
    "carrier_status",
    "wellness_metrics",
    "methylation_profiles",
    "detoxification_profiles",
    "rare_mutations",
    "uncommon_mutations",
]


def upgrade() -> None:
    # Add analysis_id indexes on all insight tables
    for table in INSIGHT_TABLES:
        op.create_index(
            f"ix_{table}_analysis_id",
            table,
            ["analysis_id"],
            if_not_exists=True,
        )

    # Remove duplicate ensembl_genes index (ix_ensembl_genes_symbol duplicates
    # ix_ensembl_genes_gene_symbol, both index gene_symbol)
    op.drop_index("ix_ensembl_genes_symbol", table_name="ensembl_genes", if_exists=True)


def downgrade() -> None:
    op.create_index("ix_ensembl_genes_symbol", "ensembl_genes", ["gene_symbol"])
    for table in INSIGHT_TABLES:
        op.drop_index(f"ix_{table}_analysis_id", table_name=table, if_exists=True)
