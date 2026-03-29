"""add gene column to carrier_status

Revision ID: 028
Revises: 027
"""
from alembic import op
import sqlalchemy as sa

revision = "028_add_gene_to_carrier_status"
down_revision = "027_create_gnomad_v2_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("carrier_status", sa.Column("gene", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("carrier_status", "gene")
