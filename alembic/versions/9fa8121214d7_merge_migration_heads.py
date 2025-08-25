"""Merge migration heads

Revision ID: 9fa8121214d7
Revises: 13f1f6623d1c, add_progress_tracking
Create Date: 2025-08-25 14:33:53.397417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fa8121214d7'
down_revision: Union[str, Sequence[str], None] = ('13f1f6623d1c', 'add_progress_tracking')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
