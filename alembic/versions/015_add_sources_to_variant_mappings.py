"""Add sources column to variant_mappings for multi-source tracking.

Revision ID: 015_sources_vm
Revises: 014_drop_pmc
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = "015_sources_vm"
down_revision = "014_drop_pmc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JSON array tracking which data sources contributed to this mapping
    # e.g. ["clinvar_local", "ensembl_vep", "alpha_missense", "gnomad"]
    op.add_column("variant_mappings", sa.Column("sources", sa.JSON, nullable=True))
    # Confidence score (0.0-1.0) based on source agreement
    op.add_column("variant_mappings", sa.Column("confidence", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("variant_mappings", "confidence")
    op.drop_column("variant_mappings", "sources")
