"""Add subpop_freqs JSON column to ancestry_aims_panel.

Stores per-sub-population allele frequencies (e.g. 1000G CEU/FIN/GBR/IBS/TSI
or gnomAD NFE sub-populations) as a JSON dict.  Used by the Phase 2 European
sub-population ancestry model.

Revision ID: 024_ancestry_subpop
Revises: 023_worker_jobs_refreshed
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = "024_ancestry_subpop"
down_revision = "023_add_worker_jobs_refreshed_at"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ancestry_aims_panel",
        sa.Column("subpop_freqs", sa.JSON, nullable=True),
    )


def downgrade():
    op.drop_column("ancestry_aims_panel", "subpop_freqs")
