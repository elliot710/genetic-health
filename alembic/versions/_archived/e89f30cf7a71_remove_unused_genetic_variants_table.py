"""Remove unused genetic_variants table

Revision ID: e89f30cf7a71
Revises: 1bb46f0c26f8
Create Date: 2025-08-26 12:31:51.687322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e89f30cf7a71'
down_revision: Union[str, Sequence[str], None] = '1bb46f0c26f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the unused genetic_variants table."""
    # Check if table exists before trying to drop it
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_name = 'genetic_variants'
        );
    """))
    table_exists = result.scalar()
    
    if table_exists:
        op.drop_table('genetic_variants')


def downgrade() -> None:
    """Recreate the genetic_variants table if needed."""
    # Recreate the table structure in case we need to rollback
    op.create_table('genetic_variants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('analysis_id', sa.Integer(), nullable=False),
        sa.Column('chromosome', sa.String(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('rsid', sa.String(), nullable=True),
        sa.Column('ref_allele', sa.String(), nullable=True),
        sa.Column('alt_allele', sa.String(), nullable=True),
        sa.Column('genotype', sa.String(), nullable=True),
        sa.Column('quality', sa.String(), nullable=True),
        sa.Column('filter_status', sa.String(), nullable=True),
        sa.Column('info', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['analysis_id'], ['genetic_analyses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
