"""create open_targets_cache table

Revision ID: 035_add_open_targets_cache
Revises: 034_gwas_chromosome_text
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '035_add_open_targets_cache'
down_revision = '034_gwas_chromosome_text'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'open_targets_cache',
        sa.Column('gene_symbol', sa.String(50), primary_key=True),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('open_targets_cache')
