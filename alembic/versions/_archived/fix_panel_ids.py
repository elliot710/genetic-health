"""Fix panel_id names and add rare/uncommon mutation markers

Revision ID: fix_panel_ids
Revises: add_panel_markers
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'fix_panel_ids'
down_revision = 'add_panel_markers'
branch_labels = None
depends_on = None


def upgrade():
    # Fix panel_id naming to match admin panel expectations
    op.execute("UPDATE panel_marker_configs SET panel_id = 'intelligence' WHERE panel_id = 'cognitive'")
    op.execute("UPDATE panel_marker_configs SET panel_id = 'physical_traits' WHERE panel_id = 'physical'")

    # Add rare_mutations markers
    table = sa.table(
        'panel_marker_configs',
        sa.column('panel_id', sa.String),
        sa.column('rsid', sa.String),
        sa.column('gene', sa.String),
        sa.column('description', sa.String),
        sa.column('category', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(table, [
        # Rare Mutations — clinically significant rare variants
        dict(panel_id='rare_mutations', rsid='rs80357906', gene='BRCA1', description='BRCA1 185delAG — Hereditary breast/ovarian cancer (Ashkenazi founder)', category='cancer', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs80358981', gene='BRCA2', description='BRCA2 6174delT — Hereditary breast/ovarian cancer (Ashkenazi founder)', category='cancer', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs121913279', gene='TP53', description='TP53 R175H — Li-Fraumeni syndrome (multi-cancer predisposition)', category='cancer', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs63750447', gene='APP', description='APP A673T — Alzheimer disease protective/risk variant', category='neurological', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs121918506', gene='LMNA', description='LMNA R482W — Familial partial lipodystrophy type 2', category='metabolic', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs104894396', gene='SCN5A', description='SCN5A — Brugada syndrome / Long QT syndrome 3', category='cardiac', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs199473282', gene='KCNQ1', description='KCNQ1 — Long QT syndrome type 1 (cardiac arrhythmia)', category='cardiac', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs121909211', gene='HEXA', description='HEXA — Tay-Sachs disease carrier screening', category='lysosomal', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs76151636', gene='GJB2', description='GJB2 35delG — Nonsyndromic hearing loss (most common variant)', category='sensory', is_active=True),
        dict(panel_id='rare_mutations', rsid='rs28937900', gene='SERPINA1', description='SERPINA1 Z allele — Alpha-1 antitrypsin deficiency', category='lung', is_active=True),

        # Uncommon Mutations — uncommon but clinically annotated variants (freq 1-5%)
        dict(panel_id='uncommon_mutations', rsid='rs1800562', gene='HFE', description='C282Y — Hereditary hemochromatosis (iron overload)', category='metabolic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs1799945', gene='HFE', description='H63D — Hereditary hemochromatosis modifier', category='metabolic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs6025', gene='F5', description='Factor V Leiden — Thrombophilia (venous thrombosis risk)', category='hematologic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs1799963', gene='F2', description='Prothrombin G20210A — Increased clotting risk', category='hematologic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs1801131', gene='MTHFR', description='A1298C — Reduced folate metabolism (homocysteine)', category='metabolic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs1801133', gene='MTHFR', description='C677T — Reduced folate metabolism (cardiovascular risk)', category='metabolic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs4880', gene='SOD2', description='A16V — Mitochondrial antioxidant defense variant', category='oxidative_stress', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs1695', gene='GSTP1', description='I105V — Glutathione conjugation (detox capacity)', category='detox', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs4149056', gene='SLCO1B1', description='SLCO1B1*5 — Statin-induced myopathy risk', category='pharmacogenomic', is_active=True),
        dict(panel_id='uncommon_mutations', rsid='rs12248560', gene='CYP2C19', description='CYP2C19*17 — Ultra-rapid metabolizer (clopidogrel)', category='pharmacogenomic', is_active=True),
    ])


def downgrade():
    op.execute("UPDATE panel_marker_configs SET panel_id = 'cognitive' WHERE panel_id = 'intelligence'")
    op.execute("UPDATE panel_marker_configs SET panel_id = 'physical' WHERE panel_id = 'physical_traits'")
    op.execute("DELETE FROM panel_marker_configs WHERE panel_id IN ('rare_mutations', 'uncommon_mutations')")
