"""add_clinvar_local_data_column

Revision ID: 862d84435bc1
Revises: 6b1ba56eb35a
Create Date: 2026-03-14 08:19:10.815209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '862d84435bc1'
down_revision: Union[str, Sequence[str], None] = '6b1ba56eb35a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('shared_variant_annotations', sa.Column('clinvar_local_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('shared_variant_annotations', 'clinvar_local_data')
