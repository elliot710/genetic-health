"""add alpha_missense_data column

Revision ID: add_alpha_missense_data
Revises: add_variant_mappings_table
Create Date: 2026-03-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_alpha_missense_data'
down_revision: str = '0fec05e26e8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'shared_variant_annotations',
        sa.Column('alpha_missense_data', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('shared_variant_annotations', 'alpha_missense_data')
