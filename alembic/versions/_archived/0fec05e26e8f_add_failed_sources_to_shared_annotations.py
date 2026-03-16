"""add_failed_sources_to_shared_annotations

Revision ID: 0fec05e26e8f
Revises: 42f7292e2562
Create Date: 2026-03-13 15:38:27.458670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0fec05e26e8f'
down_revision: Union[str, Sequence[str], None] = '42f7292e2562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('shared_variant_annotations', sa.Column('failed_sources', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('shared_variant_annotations', 'failed_sources')
    op.add_column('variant_annotations', sa.Column('ensembl_data', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.alter_column('shared_variant_annotations', 'marker_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_column('shared_variant_annotations', 'failed_sources')
    op.drop_index(op.f('ix_analysis_variants_id'), table_name='analysis_variants')
    op.create_index(op.f('ix_analysis_variants_analysis_id'), 'analysis_variants', ['analysis_id'], unique=False)
    # ### end Alembic commands ###
