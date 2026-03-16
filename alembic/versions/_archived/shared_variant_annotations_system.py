"""create_shared_variant_annotations_system

Revision ID: shared_annotations_001
Revises: e89f30cf7a71
Create Date: 2025-08-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'shared_annotations_001'
down_revision = 'ccd65c527a2f'
branch_labels = None
depends_on = None


def upgrade():
    # Create shared_variant_annotations table
    op.create_table('shared_variant_annotations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rsid', sa.String(), nullable=False),
        sa.Column('ensembl_data', sa.JSON(), nullable=True),
        sa.Column('clinvar_data', sa.JSON(), nullable=True),
        sa.Column('pharmgkb_data', sa.JSON(), nullable=True),
        sa.Column('snpedia_data', sa.JSON(), nullable=True),
        sa.Column('litvar_data', sa.JSON(), nullable=True),
        sa.Column('first_annotated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('annotation_status', sa.String(), nullable=True),
        sa.Column('total_api_calls', sa.Integer(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_shared_variant_annotations_id', 'shared_variant_annotations', ['id'], unique=False)
    op.create_index('ix_shared_variant_annotations_rsid', 'shared_variant_annotations', ['rsid'], unique=True)
    
    # Migrate existing annotation data to shared table
    # Get unique annotations from the existing variant_annotations table
    connection = op.get_bind()
    
    # First, populate shared_variant_annotations with unique annotations
    # Take the first annotation for each unique RSID
    migrate_shared_annotations = """
    INSERT INTO shared_variant_annotations (
        rsid, ensembl_data, clinvar_data, pharmgkb_data, snpedia_data, litvar_data,
        first_annotated_at, annotation_status, total_api_calls, usage_count
    )
    SELECT DISTINCT ON (rsid)
        rsid,
        ensembl_data,
        clinvar_data,
        pharmgkb_data,
        snpedia_data,
        litvar_data,
        annotated_at as first_annotated_at,
        'completed' as annotation_status,
        COALESCE(api_calls_made, 0) as total_api_calls,
        1 as usage_count
    FROM variant_annotations
    WHERE rsid IS NOT NULL
    ORDER BY rsid, annotated_at DESC
    """
    
    connection.execute(sa.text(migrate_shared_annotations))
    
    # Add new column to variant_annotations table
    op.add_column('variant_annotations', sa.Column('shared_annotation_id', sa.Integer(), nullable=True))
    op.add_column('variant_annotations', sa.Column('user_notes', sa.Text(), nullable=True))
    op.add_column('variant_annotations', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    
    # Create foreign key to shared_variant_annotations
    op.create_foreign_key('fk_variant_annotations_shared', 'variant_annotations', 'shared_variant_annotations', ['shared_annotation_id'], ['id'])
    
    # Update variant_annotations to reference shared annotations
    update_references = """
    UPDATE variant_annotations 
    SET shared_annotation_id = (
        SELECT id FROM shared_variant_annotations 
        WHERE shared_variant_annotations.rsid = variant_annotations.rsid
        LIMIT 1
    )
    WHERE rsid IS NOT NULL
    """
    
    connection.execute(sa.text(update_references))
    
    # Remove redundant columns from variant_annotations (but keep them for now for safety)
    # op.drop_column('variant_annotations', 'ensembl_data')
    # op.drop_column('variant_annotations', 'clinvar_data')
    # op.drop_column('variant_annotations', 'pharmgkb_data')
    # op.drop_column('variant_annotations', 'snpedia_data')
    # op.drop_column('variant_annotations', 'litvar_data')
    # op.drop_column('variant_annotations', 'annotated_at')
    # op.drop_column('variant_annotations', 'api_calls_made')


def downgrade():
    # Restore the original variant_annotations structure
    op.drop_constraint('fk_variant_annotations_shared', 'variant_annotations', type_='foreignkey')
    op.drop_column('variant_annotations', 'shared_annotation_id')
    op.drop_column('variant_annotations', 'user_notes')
    op.drop_column('variant_annotations', 'created_at')
    
    # Drop shared_variant_annotations table
    op.drop_index('ix_shared_variant_annotations_rsid', table_name='shared_variant_annotations')
    op.drop_index('ix_shared_variant_annotations_id', table_name='shared_variant_annotations')
    op.drop_table('shared_variant_annotations')