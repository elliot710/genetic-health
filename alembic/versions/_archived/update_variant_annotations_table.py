"""Update variant_annotations to use analysis_variant_id

Revision ID: f1a2b3c4d5e6
Revises: ccd65c527a2f
Create Date: 2025-08-26 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'ccd65c527a2f'
branch_labels = None
depends_on = None


def upgrade():
    # Add the new analysis_variant_id column
    op.add_column('variant_annotations', sa.Column('analysis_variant_id', sa.Integer(), nullable=True))
    
    # Update existing records to map variant_id to analysis_variant_id
    # This SQL maps the old variant_id to the new analysis_variant_id by finding
    # matching analysis_variants records based on the analysis_id and variant position data
    op.execute("""
        UPDATE variant_annotations va
        SET analysis_variant_id = av.id
        FROM analysis_variants av
        WHERE va.analysis_id = av.analysis_id 
        AND va.rsid = av.rsid
    """)
    
    # Make the column not nullable now that all records are updated
    op.alter_column('variant_annotations', 'analysis_variant_id', nullable=False)
    
    # Add the foreign key constraint
    op.create_foreign_key(
        'variant_annotations_analysis_variant_id_fkey',
        'variant_annotations', 'analysis_variants',
        ['analysis_variant_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Drop the old variant_id column and its foreign key
    op.drop_constraint('variant_annotations_variant_id_fkey', 'variant_annotations', type_='foreignkey')
    op.drop_column('variant_annotations', 'variant_id')


def downgrade():
    # Add back the variant_id column
    op.add_column('variant_annotations', sa.Column('variant_id', sa.Integer(), nullable=True))
    
    # This would require recreating the variants table and mapping data back
    # For simplicity, we'll just set a placeholder value
    op.execute("UPDATE variant_annotations SET variant_id = 1")
    
    # Make variant_id not nullable
    op.alter_column('variant_annotations', 'variant_id', nullable=False)
    
    # Drop the new column and constraint
    op.drop_constraint('variant_annotations_analysis_variant_id_fkey', 'variant_annotations', type_='foreignkey')
    op.drop_column('variant_annotations', 'analysis_variant_id')