"""backfill nulls and enforce defaults on hot generator columns

Revision ID: 036_hot_column_defaults
Revises: 035_add_open_targets_cache
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = '036_hot_column_defaults'
down_revision = '035_add_open_targets_cache'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill existing NULLs before enforcing NOT NULL (see 025_risk_score_float
    # for the same backfill-then-alter pattern).
    op.execute("UPDATE analysis_variants SET genotype = './.' WHERE genotype IS NULL")
    op.execute("UPDATE analysis_variants SET info = '{}' WHERE info IS NULL")
    op.execute("UPDATE genetic_markers SET alt_alleles = '' WHERE alt_alleles IS NULL")

    op.alter_column(
        'analysis_variants', 'genotype',
        nullable=False, server_default=sa.text("'./.'"),
    )
    op.alter_column(
        'analysis_variants', 'info',
        nullable=False, server_default=sa.text("'{}'"),
    )
    op.alter_column(
        'genetic_markers', 'alt_alleles',
        nullable=False, server_default=sa.text("''"),
    )


def downgrade() -> None:
    op.alter_column('genetic_markers', 'alt_alleles', nullable=True, server_default=None)
    op.alter_column('analysis_variants', 'info', nullable=True, server_default=None)
    op.alter_column('analysis_variants', 'genotype', nullable=True, server_default=None)
