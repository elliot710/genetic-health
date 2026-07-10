"""Add google_id and auth_provider to users, make hashed_password nullable

Revision ID: 022_add_google_oauth_fields
Revises: 021_add_genotype_to_saved_variants
Create Date: 2026-03-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022_add_google_oauth_fields"
down_revision: Union[str, Sequence[str], None] = "021_add_genotype_to_saved_variants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("auth_provider", sa.String(20), nullable=False, server_default="local"))
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    # Make hashed_password nullable so Google OAuth users don't need a password
    op.alter_column("users", "hashed_password", nullable=True)


def downgrade() -> None:
    op.alter_column("users", "hashed_password", nullable=False)
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "google_id")
