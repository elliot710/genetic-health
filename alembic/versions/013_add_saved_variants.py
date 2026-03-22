"""Add saved_variants table for user-bookmarked variants.

Revision ID: 013_saved_variants
Revises: 012_health_risks_gene_rev
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = "013_saved_variants"
down_revision = "012_health_risks_gene_rev"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rsid", sa.String(), nullable=False),
        sa.Column("gene", sa.String(), nullable=True),
        sa.Column("most_severe_consequence", sa.String(), nullable=True),
        sa.Column("clinical_significance", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "rsid", name="uq_saved_variant_user_rsid"),
        sa.Index("ix_saved_variants_user_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("saved_variants")
