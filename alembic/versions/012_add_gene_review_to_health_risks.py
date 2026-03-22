"""Add gene and review_status columns to health_risks for FE-01/02/03.

gene: stores the gene symbol associated with each health risk insight,
allowing the frontend to display it separately from the rsid.

review_status: stores the ClinVar review status (1–4 star level) so the
frontend can show a confidence badge and filter by evidence quality.

Revision ID: 012_add_gene_review_to_health_risks
Revises: 011_add_gene_symbol_to_markers
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa

revision = "012_health_risks_gene_rev"
down_revision = "011_add_gene_symbol_to_markers"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "health_risks",
        sa.Column("gene", sa.String(100), nullable=True),
    )
    op.add_column(
        "health_risks",
        sa.Column("review_status", sa.String(200), nullable=True),
    )


def downgrade():
    op.drop_column("health_risks", "review_status")
    op.drop_column("health_risks", "gene")
