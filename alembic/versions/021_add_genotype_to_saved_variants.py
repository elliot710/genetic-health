"""Add genotype column to saved_variants table.

Revision ID: 021_add_genotype_to_saved_variants
Revises: 020_add_sharing_and_notif_prefs
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021_add_genotype_to_saved_variants"
down_revision: Union[str, Sequence[str], None] = "020_add_sharing_and_notif_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "saved_variants",
        sa.Column("genotype", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("saved_variants", "genotype")
