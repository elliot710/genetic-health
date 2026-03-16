"""Standardize analysis statuses: cancelled->stopped, clean stale processing

Revision ID: standardize_statuses_001
Revises: normalize_markers_001
Create Date: 2026-03-12

Migrates 'cancelled' status to 'stopped' for consistency.
Marks stale 'processing' records (no active background task) as 'stopped'.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'standardize_statuses_001'
down_revision = 'normalize_markers_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename cancelled -> stopped
    op.execute(
        "UPDATE genetic_analyses SET analysis_status = 'stopped', "
        "current_step = 'stopped (migrated from cancelled)' "
        "WHERE analysis_status = 'cancelled'"
    )

    # 2. Mark stale processing records as stopped
    #    (On startup, no background tasks survive — anything stuck in 'processing' is stale)
    op.execute(
        "UPDATE genetic_analyses SET analysis_status = 'stopped', "
        "current_step = 'stopped (stale processing cleared)' "
        "WHERE analysis_status = 'processing'"
    )


def downgrade() -> None:
    # Best-effort reverse: convert back stopped rows that were originally cancelled
    op.execute(
        "UPDATE genetic_analyses SET analysis_status = 'cancelled' "
        "WHERE analysis_status = 'stopped' "
        "AND current_step = 'stopped (migrated from cancelled)'"
    )
    # Cannot reliably restore stale processing records
