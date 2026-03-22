"""Drop panel_marker_configs table — redundant with variant_mappings.

Revision ID: 014_drop_pmc
Revises: 013_saved_variants
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "014_drop_pmc"
down_revision = "013_saved_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_panel_marker_panel_rsid", table_name="panel_marker_configs")
    op.drop_index("ix_panel_marker_configs_panel_id", table_name="panel_marker_configs")
    op.drop_table("panel_marker_configs")


def downgrade() -> None:
    op.create_table(
        "panel_marker_configs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("panel_id", sa.String, nullable=False, index=True),
        sa.Column("rsid", sa.String, nullable=False),
        sa.Column("gene", sa.String),
        sa.Column("description", sa.String),
        sa.Column("category", sa.String),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_auto_discovered", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_panel_marker_configs_panel_id", "panel_marker_configs", ["panel_id"])
    op.create_index("ix_panel_marker_panel_rsid", "panel_marker_configs", ["panel_id", "rsid"], unique=True)
