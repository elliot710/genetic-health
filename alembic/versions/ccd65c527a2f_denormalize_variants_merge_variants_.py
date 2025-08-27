"""Denormalize variants - merge variants table into analysis_variants

Revision ID: ccd65c527a2f
Revises: e89f30cf7a71
Create Date: 2025-08-26 10:30:48.385598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ccd65c527a2f'
down_revision: Union[str, Sequence[str], None] = 'e89f30cf7a71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Denormalize variants by merging variants table into analysis_variants."""
    
    # Step 1: Add variant identification columns to analysis_variants
    op.add_column('analysis_variants', sa.Column('chromosome', sa.String(), nullable=True))
    op.add_column('analysis_variants', sa.Column('position', sa.Integer(), nullable=True))
    op.add_column('analysis_variants', sa.Column('rsid', sa.String(), nullable=True))
    op.add_column('analysis_variants', sa.Column('ref_allele', sa.String(), nullable=True))
    op.add_column('analysis_variants', sa.Column('alt_allele', sa.String(), nullable=True))
    
    # Step 2: Migrate data from variants table to analysis_variants
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE analysis_variants 
        SET 
            chromosome = v.chromosome,
            position = v.position,
            rsid = v.rsid,
            ref_allele = v.ref_allele,
            alt_allele = v.alt_allele
        FROM variants v
        WHERE analysis_variants.variant_id = v.id
    """))
    
    # Step 3: Make the new columns non-nullable since they should all have data now
    op.alter_column('analysis_variants', 'chromosome', nullable=False)
    op.alter_column('analysis_variants', 'position', nullable=False)
    op.alter_column('analysis_variants', 'ref_allele', nullable=False)
    op.alter_column('analysis_variants', 'alt_allele', nullable=False)
    
    # Step 4: Add indexes for performance
    op.create_index('ix_analysis_variants_rsid', 'analysis_variants', ['rsid'])
    op.create_index('ix_analysis_variants_position', 'analysis_variants', ['chromosome', 'position'])
    
    # Step 5: Drop the foreign key constraint to variants table
    op.drop_constraint('analysis_variants_variant_id_fkey', 'analysis_variants', type_='foreignkey')
    
    # Step 6: Drop the variant_id column since we no longer need it
    op.drop_column('analysis_variants', 'variant_id')
    
    # Step 7: Drop the variants table completely
    op.drop_table('variants')


def downgrade() -> None:
    """Recreate normalized structure with separate variants table."""
    
    # Step 1: Recreate the variants table
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
    op.create_index('ix_variants_unique', 'variants', 
                   ['chromosome', 'position', 'ref_allele', 'alt_allele'], 
                   unique=True)
    
    # Step 2: Add variant_id column back to analysis_variants
    op.add_column('analysis_variants', sa.Column('variant_id', sa.Integer(), nullable=True))
    
    # Step 3: Migrate unique variants back to variants table and update references
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO variants (chromosome, position, rsid, ref_allele, alt_allele)
        SELECT DISTINCT chromosome, position, rsid, ref_allele, alt_allele
        FROM analysis_variants
    """))
    
    connection.execute(sa.text("""
        UPDATE analysis_variants 
        SET variant_id = v.id
        FROM variants v
        WHERE analysis_variants.chromosome = v.chromosome 
          AND analysis_variants.position = v.position
          AND analysis_variants.ref_allele = v.ref_allele
          AND analysis_variants.alt_allele = v.alt_allele
          AND (analysis_variants.rsid = v.rsid OR (analysis_variants.rsid IS NULL AND v.rsid IS NULL))
    """))
    
    # Step 4: Make variant_id non-nullable and add foreign key
    op.alter_column('analysis_variants', 'variant_id', nullable=False)
    op.create_foreign_key('analysis_variants_variant_id_fkey', 'analysis_variants', 'variants', ['variant_id'], ['id'], ondelete='CASCADE')
    
    # Step 5: Drop the denormalized columns from analysis_variants
    op.drop_index('ix_analysis_variants_rsid', 'analysis_variants')
    op.drop_index('ix_analysis_variants_position', 'analysis_variants')
    op.drop_column('analysis_variants', 'chromosome')
    op.drop_column('analysis_variants', 'position')
    op.drop_column('analysis_variants', 'rsid')
    op.drop_column('analysis_variants', 'ref_allele')
    op.drop_column('analysis_variants', 'alt_allele')
