"""Add variants from GenVue Discovery report

Revision ID: add_genvue_variants
Revises: add_variant_mappings
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = 'add_genvue_variants'
down_revision = 'add_variant_mappings'
branch_labels = None
depends_on = None


def _seed_variant_mappings():
    """New variant_mappings from the GenVue Discovery HTML report."""
    rows = []

    def add(category, map_type, key, data):
        rows.append(dict(category=category, map_type=map_type, key=key, data=data, is_active=True))

    # =============================================
    # DRUG RESPONSE — 17 new rsIDs from report
    # =============================================
    for rsid, d in {
        'rs2108622':  {'gene': 'CYP4F2',  'drugs': ['warfarin', 'acenocoumarol', 'phenprocoumon']},
        'rs2359612':  {'gene': 'VKORC1',  'drugs': ['warfarin']},
        'rs2884737':  {'gene': 'VKORC1',  'drugs': ['warfarin']},
        'rs8050894':  {'gene': 'VKORC1',  'drugs': ['warfarin']},
        'rs11676382': {'gene': 'GGCX',    'drugs': ['warfarin']},
        'rs20455':    {'gene': 'KIF6',    'drugs': ['atorvastatin', 'pravastatin']},
        'rs7997012':  {'gene': 'HTR2A',   'drugs': ['citalopram', 'SSRIs', 'antidepressants']},
        'rs12979860': {'gene': 'IFNL3',   'drugs': ['boceprevir', 'peginterferon alfa-2a', 'peginterferon alfa-2b', 'ribavirin']},
        'rs11881222': {'gene': 'IFNL3',   'drugs': ['peginterferon alfa-2a', 'peginterferon alfa-2b', 'ribavirin']},
        'rs1902023':  {'gene': 'UGT2B15', 'drugs': ['lorazepam', 'oxazepam']},
        'rs1751034':  {'gene': 'ABCC4',   'drugs': ['tenofovir']},
        'rs2298383':  {'gene': 'ADORA2A', 'drugs': ['caffeine']},
        'rs5443':     {'gene': 'GNB3',    'drugs': ['sildenafil']},
        'rs11615':    {'gene': 'ERCC1',   'drugs': ['carboplatin', 'cisplatin', 'oxaliplatin']},
        'rs924607':   {'gene': 'LOC100996325', 'drugs': ['vincristine']},
        'rs1517114':  {'gene': 'C8orf34', 'drugs': ['irinotecan']},
        'rs2232228':  {'gene': 'HAS3',    'drugs': ['anthracyclines']},
    }.items():
        add('drug', 'rsid', rsid, d)

    # New drug gene mappings (genes not already in drug category)
    for gene, d in {
        'CYP4F2':  {'gene': 'CYP4F2',  'drugs': [['warfarin', 'intermediate', 'CYP4F2 metabolizes vitamin K1 — may require warfarin dose adjustment'], ['acenocoumarol', 'intermediate', 'Dose adjustment may be needed'], ['phenprocoumon', 'intermediate', 'Monitor INR closely']]},
        'VKORC1':  {'gene': 'VKORC1',  'drugs': [['warfarin', 'intermediate', 'VKORC1 is the primary target of warfarin — variants significantly affect dose requirements']]},
        'GGCX':    {'gene': 'GGCX',    'drugs': [['warfarin', 'intermediate', 'GGCX gamma-carboxylates vitamin K-dependent clotting factors — variants affect warfarin sensitivity']]},
        'KIF6':    {'gene': 'KIF6',    'drugs': [['atorvastatin', 'normal', 'KIF6 Trp719Arg carriers may benefit more from statin therapy'], ['pravastatin', 'normal', 'Enhanced cardiovascular benefit in carriers']]},
        'HTR2A':   {'gene': 'HTR2A',   'drugs': [['citalopram', 'intermediate', 'HTR2A serotonin receptor variants affect SSRI antidepressant response'], ['SSRIs', 'intermediate', 'May require dose or drug class adjustment']]},
        'IFNL3':   {'gene': 'IFNL3',   'drugs': [['peginterferon alfa-2a', 'intermediate', 'IFNL3/IL28B genotype predicts interferon treatment response for hepatitis C'], ['ribavirin', 'intermediate', 'Combined with interferon, genotype affects sustained virologic response']]},
        'UGT2B15': {'gene': 'UGT2B15', 'drugs': [['lorazepam', 'intermediate', 'UGT2B15 glucuronidates benzodiazepines — poor metabolizers may need dose reduction'], ['oxazepam', 'intermediate', 'Reduced clearance in poor metabolizers']]},
        'ABCC4':   {'gene': 'ABCC4',   'drugs': [['tenofovir', 'intermediate', 'ABCC4/MRP4 transporter affects tenofovir renal elimination — monitor kidney function']]},
        'ADORA2A': {'gene': 'ADORA2A', 'drugs': [['caffeine', 'intermediate', 'ADORA2A adenosine receptor variant affects caffeine sensitivity and anxiety response']]},
        'ERCC1':   {'gene': 'ERCC1',   'drugs': [['carboplatin', 'intermediate', 'ERCC1 DNA repair gene — variants affect platinum chemotherapy response and toxicity'], ['cisplatin', 'intermediate', 'Reduced DNA repair may increase platinum sensitivity'], ['oxaliplatin', 'intermediate', 'Monitor for increased toxicity']]},
        'HAS3':    {'gene': 'HAS3',    'drugs': [['anthracyclines', 'intermediate', 'HAS3 hyaluronan synthase variant associated with anthracycline cardiotoxicity risk']]},
    }.items():
        add('drug', 'gene', gene, d)

    # =============================================
    # HEALTH RISKS — pathogenic/likely pathogenic variants from report
    # =============================================
    for rsid, d in {
        'rs1024611':  {'condition': 'Coronary Artery Disease', 'risk_multiplier': 1.4},
        'rs10509305': {'condition': 'Preeclampsia Risk', 'risk_multiplier': 1.3},
        'rs11085825': {'condition': 'Glutaric Acidemia', 'risk_multiplier': 1.2},
        'rs1801274':  {'condition': 'Autoimmune Susceptibility', 'risk_multiplier': 1.1},
        'rs3729856':  {'condition': 'Cardiovascular Phenotype', 'risk_multiplier': 1.0},
    }.items():
        add('health', 'rsid', rsid, d)

    for gene, d in {
        'CCL2':   {'condition': 'Coronary Artery Disease', 'risk_level': 'moderate', 'risk_score': '1.4x', 'recommendations': ['CCL2 monocyte chemoattractant promotes arterial inflammation', 'Regular cardiovascular screening', 'Anti-inflammatory diet rich in omega-3']},
        'STOX1':  {'condition': 'Preeclampsia Risk', 'risk_level': 'moderate', 'risk_score': '1.3x', 'recommendations': ['STOX1 pathogenic variant linked to preeclampsia susceptibility', 'Blood pressure monitoring during pregnancy', 'Consult OB-GYN for risk management']},
        'GCDH':   {'condition': 'Glutaric Acidemia', 'risk_level': 'low', 'risk_score': '1.2x', 'recommendations': ['GCDH encodes glutaryl-CoA dehydrogenase', 'Carrier status — standard screening for offspring', 'Protein intake monitoring if symptomatic']},
        'GATA4':  {'condition': 'Congenital Heart Defects', 'risk_level': 'low', 'risk_score': '1.0x', 'recommendations': ['GATA4 transcription factor for cardiac development', 'Benign variant — routine cardiac screening sufficient', 'Echocardiogram if family history']},
        'FCGR2A': {'condition': 'Autoimmune Susceptibility', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['FCGR2A receptor affects immune complex clearance', 'Monitor for autoimmune symptoms', 'Regular immune panel if indicated']},
    }.items():
        add('health', 'gene', gene, d)

    # =============================================
    # CARRIER STATUS — rare disease variants (heterozygous carriers)
    # =============================================
    for rsid, d in {
        'rs41280110':  {'condition': 'Hyperkalemic Periodic Paralysis / Congenital Myasthenic Syndrome', 'status': 'carrier'},
        'rs140673211': {'condition': 'Intellectual Disability (NSUN2-related)', 'status': 'carrier'},
        'rs112951498': {'condition': 'Intellectual Disability (NSUN2-related)', 'status': 'carrier'},
        'rs34099410':  {'condition': 'Arrhythmogenic Right Ventricular Cardiomyopathy (TMEM43)', 'status': 'carrier'},
        'rs41282936':  {'condition': 'Nonsyndromic Hearing Loss (USH1C)', 'status': 'carrier'},
        'rs72647851':  {'condition': 'Dilated Cardiomyopathy (TTN)', 'status': 'carrier'},
        'rs45585535':  {'condition': 'Multiminicore Disease / Neuromuscular Disease (RYR1)', 'status': 'carrier'},
        'rs5027':      {'condition': 'Distal Renal Tubular Acidosis / Spherocytosis (SLC4A1)', 'status': 'carrier'},
    }.items():
        add('carrier', 'rsid', rsid, d)

    return rows


def _seed_panel_markers():
    """New panel_marker_configs from the GenVue Discovery report."""
    rows = []

    def add(panel_id, rsid, gene, description, category):
        rows.append(dict(panel_id=panel_id, rsid=rsid, gene=gene, description=description, category=category, is_active=True))

    # Anticoagulant panel — warfarin pharmacogenomics
    add('detox', 'rs2108622',  'CYP4F2',  'CYP4F2 V433M — Vitamin K1 oxidase affecting warfarin dose',  'anticoagulants')
    add('detox', 'rs2359612',  'VKORC1',  'VKORC1 — Warfarin target enzyme variant',                    'anticoagulants')
    add('detox', 'rs2884737',  'VKORC1',  'VKORC1 — Warfarin dose sensitivity variant',                 'anticoagulants')
    add('detox', 'rs8050894',  'VKORC1',  'VKORC1 — Warfarin dose sensitivity variant',                 'anticoagulants')
    add('detox', 'rs11676382', 'GGCX',    'GGCX — Gamma-carboxylase affecting warfarin sensitivity',    'anticoagulants')

    # Statin panel
    add('detox', 'rs20455',    'KIF6',    'KIF6 Trp719Arg — Statin efficacy modifier',                  'statins')

    # Phase 2 metabolism
    add('detox', 'rs1902023',  'UGT2B15', 'UGT2B15 — Benzodiazepine glucuronidation (lorazepam/oxazepam)', 'phase2')

    # Phase 3 transport
    add('detox', 'rs1751034',  'ABCC4',   'ABCC4/MRP4 — Drug efflux transporter (tenofovir)',           'phase3')

    return rows


def upgrade():
    # Insert new variant_mappings
    vm_table = sa.table(
        'variant_mappings',
        sa.column('category', sa.String),
        sa.column('map_type', sa.String),
        sa.column('key', sa.String),
        sa.column('data', JSON),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(vm_table, _seed_variant_mappings())

    # Insert new panel_marker_configs
    pm_table = sa.table(
        'panel_marker_configs',
        sa.column('panel_id', sa.String),
        sa.column('rsid', sa.String),
        sa.column('gene', sa.String),
        sa.column('description', sa.String),
        sa.column('category', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(pm_table, _seed_panel_markers())


def downgrade():
    # Remove the inserted variant_mappings
    op.execute("""
        DELETE FROM variant_mappings WHERE key IN (
            'rs2108622','rs2359612','rs2884737','rs8050894','rs11676382',
            'rs20455','rs7997012','rs12979860','rs11881222','rs1902023',
            'rs1751034','rs2298383','rs5443','rs11615','rs924607',
            'rs1517114','rs2232228',
            'rs1024611','rs10509305','rs11085825','rs1801274','rs3729856',
            'rs41280110','rs140673211','rs112951498','rs34099410','rs41282936',
            'rs72647851','rs45585535','rs5027'
        )
    """)
    op.execute("""
        DELETE FROM variant_mappings WHERE key IN (
            'CYP4F2','VKORC1','GGCX','KIF6','HTR2A','IFNL3',
            'UGT2B15','ABCC4','ADORA2A','ERCC1','HAS3',
            'CCL2','STOX1','GCDH','GATA4','FCGR2A'
        )
    """)
    # Remove the inserted panel_marker_configs
    op.execute("""
        DELETE FROM panel_marker_configs WHERE rsid IN (
            'rs2108622','rs2359612','rs2884737','rs8050894','rs11676382',
            'rs20455','rs1902023','rs1751034'
        )
    """)
