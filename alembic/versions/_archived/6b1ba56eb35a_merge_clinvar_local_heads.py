"""merge_clinvar_local_heads

Revision ID: 6b1ba56eb35a
Revises: add_annotation_source_configs, d56b755ef88c
Create Date: 2026-03-14 08:18:45.895584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b1ba56eb35a'
down_revision: Union[str, Sequence[str], None] = ('add_annotation_source_configs', 'd56b755ef88c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
