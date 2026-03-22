"""add variant lookup cache table

Revision ID: a1b2c3d4e5f6
Revises: e19067c6122a
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = None  # Will be set after checking current head
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'variant_lookup_cache',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('variant_id', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('found', sa.Boolean(), default=False),
        sa.Column('response_data', postgresql.JSON()),
        sa.Column('raw_annotations', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('lookup_count', sa.Integer(), default=1),
    )


def downgrade() -> None:
    op.drop_table('variant_lookup_cache')
