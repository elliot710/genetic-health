"""merge_multiple_heads

Revision ID: 42f7292e2562
Revises: add_pending_discoveries, a1b2c3d4e5f6, fix_panel_ids
Create Date: 2026-03-13 15:37:45.646194

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42f7292e2562'
down_revision: Union[str, Sequence[str], None] = ('add_pending_discoveries', 'a1b2c3d4e5f6', 'fix_panel_ids')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
