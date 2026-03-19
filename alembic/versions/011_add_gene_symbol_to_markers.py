"""Add gene_symbol column to genetic_markers for PERF-04 caching.

Caching gene_symbol on the marker row eliminates the need to rebuild
the rsid→gene map from scratch on every analysis run.  build_rsid_gene_map()
writes back gene_symbol after the first run; subsequent analyses read
it with a single JOIN instead of two multi-second batch queries.

Revision ID: 011_add_gene_symbol_to_markers
Revises: 010_ancestry_aims
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa

revision = "011_add_gene_symbol_to_markers"
down_revision = "010_ancestry_aims"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "genetic_markers",
        sa.Column("gene_symbol", sa.String(50), nullable=True),
    )
    op.create_index(
        "ix_genetic_markers_gene_symbol",
        "genetic_markers",
        ["gene_symbol"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_genetic_markers_gene_symbol", table_name="genetic_markers")
    op.drop_column("genetic_markers", "gene_symbol")
