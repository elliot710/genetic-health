"""add provenance column to health_risks

Revision ID: 040_health_risk_provenance
Revises: 039_insight_status
Create Date: 2026-09-19

Separates a risk assessed from the user's own genotype ('variant') from a
condition merely associated with the gene ('gene'). Both are worth showing;
presenting the second as the first is what named a gene's worst known disease
as the user's finding.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '040_health_risk_provenance'
down_revision: Union[str, Sequence[str], None] = '039_insight_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'health_risks',
        sa.Column('provenance', sa.String(length=10), nullable=False,
                  server_default='variant'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('health_risks', 'provenance')
