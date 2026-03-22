"""Optimize variant storage - separate variants from user-specific data

Revision ID: optimize_variant_storage
Revises: 
Create Date: 2025-08-26 07:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'optimize_variant_storage'
down_revision = 'e19067c6122a'  # The latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Create the optimized Variant table for unique variant definitions
    op.create_table('variants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chromosome', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('rsid', sa.String(), nullable=True),
        sa.Column('ref_allele', sa.String(), nullable=False),
        sa.Column('alt_allele', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_variants_rsid', 'variants', ['rsid'])
    op.create_index('ix_variants_position', 'variants', ['chromosome', 'position'])
    
    # Create unique constraint for variants to prevent duplicates
    op.create_index('ix_variants_unique', 'variants', 
                   ['chromosome', 'position', 'ref_allele', 'alt_allele'], 
                   unique=True)
    
    # Create the AnalysisVariant junction table for user-specific variant data
    op.create_table('analysis_variants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('analysis_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('genotype', sa.String(), nullable=True),
        sa.Column('quality', sa.String(), nullable=True),
        sa.Column('filter_status', sa.String(), nullable=True),
        sa.Column('info', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['analysis_id'], ['genetic_analyses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analysis_variants_analysis_id', 'analysis_variants', ['analysis_id'])
    op.create_index('ix_analysis_variants_variant_id', 'analysis_variants', ['variant_id'])
    
    # Create unique constraint to prevent duplicate variant-analysis pairs
    op.create_index('ix_analysis_variants_unique', 'analysis_variants', 
                   ['analysis_id', 'variant_id'], unique=True)


def downgrade():
    # Drop the new tables
    op.drop_table('analysis_variants')
    op.drop_table('variants')