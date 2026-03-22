"""Add dashboard_shares table and notification_preferences column to users.

Revision ID: 020_add_sharing_and_notif_prefs
Revises: 019_add_notifications
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "020_add_sharing_and_notif_prefs"
down_revision: Union[str, Sequence[str], None] = "019_add_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notification_preferences JSON column to users
    op.add_column(
        "users",
        sa.Column("notification_preferences", sa.JSON(), nullable=True),
    )

    # Create dashboard_shares table
    op.create_table(
        "dashboard_shares",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("owner_id", "recipient_id", name="uq_dashboard_share"),
    )
    op.create_index("ix_dashboard_shares_owner", "dashboard_shares", ["owner_id"])
    op.create_index("ix_dashboard_shares_recipient", "dashboard_shares", ["recipient_id"])


def downgrade() -> None:
    op.drop_index("ix_dashboard_shares_recipient", table_name="dashboard_shares")
    op.drop_index("ix_dashboard_shares_owner", table_name="dashboard_shares")
    op.drop_table("dashboard_shares")
    op.drop_column("users", "notification_preferences")
