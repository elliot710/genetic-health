"""widen gwas_catalog_associations string columns to TEXT

Revision ID: 033_gwas_rsid_text
Revises: 032_add_gwas_clingen_sources
Create Date: 2026-04-06
"""
from alembic import op

revision = '033_gwas_rsid_text'
down_revision = '032_add_gwas_clingen_sources'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN rsid TYPE TEXT")
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN pubmed_id TYPE TEXT")
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN study_accession TYPE TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN rsid TYPE VARCHAR(32)")
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN pubmed_id TYPE VARCHAR(20)")
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN study_accession TYPE VARCHAR(20)")
