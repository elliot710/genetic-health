"""merge variant optimization with existing migrations

Revision ID: 1bb46f0c26f8
Revises: ac0a020bc538, optimize_variant_storage
Create Date: 2025-08-26 07:36:47.284826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bb46f0c26f8'
down_revision: Union[str, Sequence[str], None] = ('ac0a020bc538', 'optimize_variant_storage')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
