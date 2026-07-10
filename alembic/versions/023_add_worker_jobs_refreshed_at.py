"""Add refreshed_at to worker_jobs

Revision ID: 023_add_worker_jobs_refreshed_at
Revises: 022_add_google_oauth_fields
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023_add_worker_jobs_refreshed_at"
down_revision: Union[str, Sequence[str], None] = "022_add_google_oauth_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "worker_jobs",
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("worker_jobs", "refreshed_at")
