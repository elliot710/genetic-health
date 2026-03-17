"""Merge heads + add gnomad_tx_data column to shared_variant_annotations.

Merges the two parallel heads (006_add_large_table_indexes and cf76f2735c9e)
and adds the gnomad_tx_data JSON column for storing gnomAD transcript
annotations with GTEx tissue expression data.

Revision ID: 007_merge_add_gnomad_tx
Revises: 006_add_large_table_indexes, cf76f2735c9e
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = "007_merge_add_gnomad_tx"
down_revision = ("006_add_large_table_indexes", "cf76f2735c9e")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shared_variant_annotations",
        sa.Column("gnomad_tx_data", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shared_variant_annotations", "gnomad_tx_data")
