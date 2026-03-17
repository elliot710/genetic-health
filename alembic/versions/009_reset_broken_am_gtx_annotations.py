"""Reset broken alpha_missense and gnomad_tx found:false annotations.

These sources returned {found: false} due to bugs (AlphaMissense used hg38
instead of hg19, gnomAD-tx lacked allele-flip logic). Now that the services
are fixed, NULLing these columns lets the backfill re-query them and find
real data. ClinVar/gnomAD/Ensembl/1000G are NOT reset — their found:false
entries are genuine misses.

Revision ID: 009_reset_broken_am_gtx
Revises: 008_add_source_type
Create Date: 2026-03-18
"""
from alembic import op

revision = "009_reset_broken_am_gtx"
down_revision = "008_add_source_type"
branch_labels = None
depends_on = None


def upgrade():
    # Reset alpha_missense_data where found=false (broken hg38 lookups)
    op.execute("""
        UPDATE shared_variant_annotations
        SET alpha_missense_data = NULL
        WHERE alpha_missense_data->>'found' = 'false'
    """)

    # Reset gnomad_tx_data where found=false (broken no-allele-flip lookups)
    op.execute("""
        UPDATE shared_variant_annotations
        SET gnomad_tx_data = NULL
        WHERE gnomad_tx_data->>'found' = 'false'
    """)


def downgrade():
    # Cannot restore the old {found: false} values — they were incorrect anyway
    pass
