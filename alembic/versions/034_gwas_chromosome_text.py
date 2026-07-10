"""widen gwas_catalog_associations.chromosome to TEXT

Revision ID: 034_gwas_chromosome_text
Revises: 033_gwas_rsid_text
Create Date: 2026-04-06
"""
from alembic import op

revision = '034_gwas_chromosome_text'
down_revision = '033_gwas_rsid_text'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN chromosome TYPE TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE gwas_catalog_associations ALTER COLUMN chromosome TYPE VARCHAR(5)")
