"""add_avatar_url_to_users

Revision ID: d56b755ef88c
Revises: add_alpha_missense_data
Create Date: 2026-03-13 21:09:08.227039

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd56b755ef88c'
down_revision: Union[str, Sequence[str], None] = 'add_alpha_missense_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('avatar_url', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'avatar_url')
