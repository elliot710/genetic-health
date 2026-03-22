"""Add methylation/detox markers from Genetic Genie + common markers for empty panels

Revision ID: add_panel_markers
Revises: add_genvue_variants
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_panel_markers'
down_revision = 'add_genvue_variants'
branch_labels = None
depends_on = None


def _new_markers():
    """Panel marker configs to insert. Returns list of dicts."""
    rows = []

    def add(panel_id, rsid, gene, description, category):
        rows.append(dict(panel_id=panel_id, rsid=rsid, gene=gene,
                         description=description, category=category, is_active=True))

    # =============================================
    # METHYLATION — from Genetic Genie Methylation Profile
    # Already exist: rs4680/COMT, rs1801133/MTHFR, rs1801131/MTHFR,
    #   rs1805087/MTR, rs1801394/MTRR, rs234706/CBS
    # =============================================

    # Folate cycle
    add('methylation', 'rs2066470', 'MTHFR', 'P39P — MTHFR folate processing variant', 'folate_cycle')
    add('methylation', 'rs1979277', 'SHMT1', 'C1420T — Serine hydroxymethyltransferase (folate one-carbon transfer)', 'folate_cycle')

    # Methylation enzymes (COMT, MTRR additional markers)
    add('methylation', 'rs4633',    'COMT',  'H62H — Catechol-O-methyltransferase synonymous variant', 'methylation_enzymes')
    add('methylation', 'rs769224',  'COMT',  'P199P — Catechol-O-methyltransferase synonymous variant', 'methylation_enzymes')
    add('methylation', 'rs10380',   'MTRR',  'H595Y — Methionine synthase reductase variant', 'methylation_enzymes')
    add('methylation', 'rs162036',  'MTRR',  'K350A — Methionine synthase reductase variant', 'methylation_enzymes')
    add('methylation', 'rs2287780', 'MTRR',  'R415T — Methionine synthase reductase variant', 'methylation_enzymes')
    add('methylation', 'rs1802059', 'MTRR',  'A664A — Methionine synthase reductase synonymous variant', 'methylation_enzymes')
    add('methylation', 'rs3741049', 'ACAT1', 'ACAT1-02 — Acetyl-CoA acetyltransferase (lipid methylation support)', 'methylation_enzymes')

    # VDR (vitamin D receptor — affects methylation via calcium/epigenetics)
    add('methylation', 'rs1544410', 'VDR', 'BsmI — Vitamin D receptor affecting calcium and methylation regulation', 'vitamin_d')
    add('methylation', 'rs731236',  'VDR', 'TaqI — Vitamin D receptor variant affecting gene expression', 'vitamin_d')

    # Transsulfuration (BHMT & CBS additions)
    add('methylation', 'rs567754',  'BHMT', 'BHMT-02 — Betaine-homocysteine methyltransferase variant', 'transsulfuration')
    add('methylation', 'rs617219',  'BHMT', 'BHMT-04 — Betaine-homocysteine methyltransferase variant', 'transsulfuration')
    add('methylation', 'rs651852',  'BHMT', 'BHMT-08 — Betaine-homocysteine methyltransferase variant', 'transsulfuration')
    add('methylation', 'rs1801181', 'CBS',  'A360A — Cystathionine beta-synthase synonymous variant', 'transsulfuration')
    add('methylation', 'rs2298758', 'CBS',  'N212N — Cystathionine beta-synthase synonymous variant', 'transsulfuration')

    # Methylation-adjacent (MAO-A, AHCY — listed as "not found" but standard markers)
    add('methylation', 'rs6323',    'MAOA',  'R297R — Monoamine oxidase A (neurotransmitter methylation)', 'neurotransmitter')
    add('methylation', 'rs819147',  'AHCY',  'AHCY-01 — S-adenosylhomocysteine hydrolase (SAH clearance)', 'transsulfuration')
    add('methylation', 'rs819134',  'AHCY',  'AHCY-02 — S-adenosylhomocysteine hydrolase variant', 'transsulfuration')
    add('methylation', 'rs819171',  'AHCY',  'AHCY-19 — S-adenosylhomocysteine hydrolase variant', 'transsulfuration')

    # =============================================
    # DETOX — from Genetic Genie Detox Profile
    # Already exist: rs762551/CYP1A2, rs1799853/CYP2C9, rs2740574/CYP3A4,
    #   rs3892097/CYP2D6, rs1695/GSTP1, rs1799930/NAT2, rs4986782/NAT1
    # =============================================

    # Phase 1 — CYP enzymes
    add('detox', 'rs1048943',  'CYP1A1', 'CYP1A1*2C A4889G — Phase I aromatic hydrocarbon oxidation', 'phase1')
    add('detox', 'rs4986883',  'CYP1A1', 'CYP1A1 m3 T3205C — Phase I oxidation variant', 'phase1')
    add('detox', 'rs1799814',  'CYP1A1', 'CYP1A1 C2453A — Phase I oxidation variant', 'phase1')
    add('detox', 'rs1056836',  'CYP1B1', 'CYP1B1 L432V — Estrogen and xenobiotic metabolism', 'phase1')
    add('detox', 'rs1800440',  'CYP1B1', 'CYP1B1 N453S — Estrogen hydroxylation variant', 'phase1')
    add('detox', 'rs1801272',  'CYP2A6', 'CYP2A6*2 — Nicotine and coumarin metabolism', 'phase1')
    add('detox', 'rs1135840',  'CYP2D6', 'CYP2D6 S486T — Codeine, tamoxifen, and antidepressant metabolism', 'phase1')
    add('detox', 'rs1065852',  'CYP2D6', 'CYP2D6 100C>T — Major drug metabolism enzyme variant', 'phase1')
    add('detox', 'rs2070676',  'CYP2E1', 'CYP2E1*1B 9896C>G — Ethanol and acetaminophen oxidation', 'phase1')
    add('detox', 'rs55897648', 'CYP2E1', 'CYP2E1*1B 10023G>A — Solvent and small molecule metabolism', 'phase1')
    add('detox', 'rs6413419',  'CYP2E1', 'CYP2E1*4 — Reduced ethanol metabolism variant', 'phase1')

    # Phase 2 — conjugation enzymes
    add('detox', 'rs1138272',  'GSTP1', 'GSTP1 A114V — Glutathione S-transferase pi (reduced conjugation)', 'phase2')
    add('detox', 'rs1801280',  'NAT2',  'NAT2 I114T — N-acetyltransferase 2 slow acetylator variant', 'phase2')
    add('detox', 'rs1799931',  'NAT2',  'NAT2 G286E — Slow acetylator haplotype marker', 'phase2')
    add('detox', 'rs1801279',  'NAT2',  'NAT2 R64Q — N-acetyltransferase 2 variant', 'phase2')
    add('detox', 'rs1208',     'NAT2',  'NAT2 K268R — Acetylator status tagging variant', 'phase2')

    # Antioxidant defense
    add('detox', 'rs4880',     'SOD2',  'SOD2 A16V — Superoxide dismutase 2 (mitochondrial antioxidant)', 'antioxidant')

    # Missing from report (standard Genetic Genie detox markers)
    add('detox', 'rs10012',    'CYP1B1', 'CYP1B1 R48G — Phase I estrogen metabolism variant', 'phase1')
    add('detox', 'rs16947',    'CYP2D6', 'CYP2D6 2850C>T — Intermediate metabolizer variant', 'phase1')
    add('detox', 'rs1805158',  'NAT1',   'NAT1 R64W — N-acetyltransferase 1 variant', 'phase2')

    # =============================================
    # NUTRITION — common nutrigenomics markers (panel had NO markers)
    # =============================================
    add('nutrition', 'rs4988235', 'MCM6/LCT', 'Lactase persistence — Dairy tolerance (C/T-13910)', 'lactose')
    add('nutrition', 'rs713598',  'TAS2R38',  'Bitter taste receptor — Cruciferous vegetable preference', 'taste')
    add('nutrition', 'rs1800497', 'DRD2',     'Taq1A — Dopamine reward, sugar/carb cravings', 'appetite')
    add('nutrition', 'rs1801133', 'MTHFR',    'C677T — Folate metabolism (B9 requirements)', 'vitamins')
    add('nutrition', 'rs602662',  'FUT2',     'Fucosyltransferase 2 — Vitamin B12 absorption', 'vitamins')
    add('nutrition', 'rs7041',    'GC',       'Vitamin D binding protein — Vitamin D levels', 'vitamins')
    add('nutrition', 'rs1800588', 'LIPC',     'Hepatic lipase — HDL cholesterol and fat metabolism', 'fat_metabolism')
    add('nutrition', 'rs174547',  'FADS1',    'Fatty acid desaturase 1 — Omega-3/omega-6 conversion', 'fat_metabolism')
    add('nutrition', 'rs1799945', 'HFE',      'H63D — Iron absorption and hemochromatosis risk', 'minerals')
    add('nutrition', 'rs1800562', 'HFE',      'C282Y — Iron overload risk variant', 'minerals')
    add('nutrition', 'rs236918',  'PCSK7',    'Proprotein convertase — Affects lipid metabolism', 'fat_metabolism')

    # =============================================
    # COGNITIVE — common cognitive/neurogenomics markers (panel had NO markers)
    # =============================================
    add('cognitive', 'rs4680',    'COMT',   'Val158Met — Dopamine clearance, working memory and focus', 'memory')
    add('cognitive', 'rs6265',    'BDNF',   'Val66Met — Brain-derived neurotrophic factor (neuroplasticity)', 'neuroplasticity')
    add('cognitive', 'rs53576',   'OXTR',   'Oxytocin receptor — Social cognition and empathy', 'social_cognition')
    add('cognitive', 'rs1800497', 'DRD2',   'Taq1A — Dopamine D2 receptor, learning and reward processing', 'dopamine')
    add('cognitive', 'rs1611115', 'DBH',    'Dopamine beta-hydroxylase — Norepinephrine synthesis, attention', 'attention')
    add('cognitive', 'rs165599',  'COMT',   'COMT 3-UTR — Prefrontal cortex dopamine regulation', 'memory')
    add('cognitive', 'rs4570625', 'TPH2',   'Tryptophan hydroxylase 2 — Serotonin synthesis, mood & cognition', 'serotonin')

    # =============================================
    # PERSONALITY — common behavioral genetics markers (panel had NO markers)
    # =============================================
    add('personality', 'rs4680',    'COMT',   'Val158Met — Warrior vs Worrier (stress response style)', 'temperament')
    add('personality', 'rs53576',   'OXTR',   'Oxytocin receptor — Empathy and social bonding tendency', 'social')
    add('personality', 'rs1800955', 'DRD4',   'Dopamine D4 receptor — Novelty seeking and exploration', 'temperament')
    add('personality', 'rs6265',    'BDNF',   'Val66Met — Resilience, anxiety susceptibility', 'resilience')
    add('personality', 'rs4570625', 'TPH2',   'Tryptophan hydroxylase 2 — Emotional reactivity', 'emotional')
    add('personality', 'rs1800497', 'DRD2',   'Taq1A — Reward sensitivity and impulsivity', 'temperament')

    # =============================================
    # WELLNESS — common wellness/longevity markers (panel had NO markers)
    # =============================================
    add('wellness', 'rs1801133', 'MTHFR',    'C677T — Inflammation and homocysteine levels', 'inflammation')
    add('wellness', 'rs4680',    'COMT',     'Val158Met — Stress response and cortisol regulation', 'stress')
    add('wellness', 'rs1800497', 'DRD2',     'Taq1A — Dopamine reward balance and addictive tendencies', 'mental_health')
    add('wellness', 'rs9939609', 'FTO',      'Fat mass and obesity — Weight management predisposition', 'weight')
    add('wellness', 'rs1042713', 'ADRB2',    'Beta-2 adrenergic receptor — Exercise response and metabolism', 'exercise')
    add('wellness', 'rs4880',    'SOD2',     'A16V — Oxidative stress defense and aging', 'antioxidant')
    add('wellness', 'rs1800795', 'IL6',      'Interleukin-6 — Inflammatory response and recovery', 'inflammation')
    add('wellness', 'rs7903146', 'TCF7L2',   'Transcription factor 7 — Metabolic health and glucose control', 'metabolic')

    # =============================================
    # PHYSICAL — common physical traits markers (panel had NO markers)
    # =============================================
    add('physical', 'rs1815739', 'ACTN3',    'R577X — Fast-twitch muscle fibers (power vs endurance)', 'athletic')
    add('physical', 'rs4988235', 'MCM6/LCT', 'Lactase persistence — Lactose tolerance', 'digestive')
    add('physical', 'rs1800407', 'OCA2',     'OCA2 — Eye color determination (blue/green tendency)', 'appearance')
    add('physical', 'rs12913832','HERC2',    'Iris pigmentation — Major eye color determinant', 'appearance')
    add('physical', 'rs1805007', 'MC1R',     'Red hair and fair skin — Melanocortin 1 receptor', 'appearance')
    add('physical', 'rs713598',  'TAS2R38',  'Bitter taste perception — Sensitivity to PTC/PROP', 'sensory')
    add('physical', 'rs1393350', 'TYR',      'Tyrosinase — Skin and hair pigmentation', 'appearance')
    add('physical', 'rs17822931','ABCC11',   'Ear wax type and body odor — Dry vs wet earwax', 'misc')

    # =============================================
    # CARRIER — common carrier screening markers (panel had NO markers)
    # =============================================
    add('carrier', 'rs334',      'HBB',    'Sickle Cell Disease — Hemoglobin beta chain (HbS)', 'blood_disorders')
    add('carrier', 'rs5030868',  'CFTR',   'Cystic Fibrosis — CFTR chloride channel variant', 'lung_disorders')
    add('carrier', 'rs80338939', 'SMN1',   'Spinal Muscular Atrophy — Survival motor neuron 1', 'neuromuscular')
    add('carrier', 'rs28937900', 'SERPINA1','Alpha-1 Antitrypsin Deficiency — Lung/liver disease risk', 'lung_disorders')
    add('carrier', 'rs1800562',  'HFE',    'C282Y — Hereditary Hemochromatosis (iron overload)', 'metabolic')
    add('carrier', 'rs76151636', 'GJB2',   'Connexin 26 — Nonsyndromic Hearing Loss carrier', 'hearing')
    add('carrier', 'rs1800546',  'G6PD',   'G6PD Deficiency — Glucose-6-phosphate dehydrogenase', 'blood_disorders')

    # =============================================
    # ANCESTRY — population informative markers (panel had NO markers)
    # =============================================
    add('ancestry', 'rs1426654', 'SLC24A5', 'Skin pigmentation — European/South Asian ancestry marker', 'pigmentation')
    add('ancestry', 'rs16891982','SLC45A2', 'Skin lightening variant — European ancestry informative', 'pigmentation')
    add('ancestry', 'rs3827760', 'EDAR',    'Hair thickness and sweat glands — East Asian ancestry marker', 'morphology')
    add('ancestry', 'rs12913832','HERC2',   'Eye color — Northern European ancestry marker', 'pigmentation')
    add('ancestry', 'rs4988235', 'MCM6/LCT','Lactase persistence — European/pastoralist ancestry marker', 'dietary_adaptation')
    add('ancestry', 'rs2814778', 'ACKR1',   'Duffy antigen — Sub-Saharan African ancestry marker', 'blood_type')

    return rows


def upgrade():
    table = sa.table(
        'panel_marker_configs',
        sa.column('panel_id', sa.String),
        sa.column('rsid', sa.String),
        sa.column('gene', sa.String),
        sa.column('description', sa.String),
        sa.column('category', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(table, _new_markers())


def downgrade():
    # Remove all markers added by this migration
    new_rsids = [
        # Methylation
        'rs2066470','rs1979277','rs4633','rs769224','rs10380','rs162036',
        'rs2287780','rs1802059','rs3741049','rs1544410','rs731236',
        'rs567754','rs617219','rs651852','rs1801181','rs2298758',
        'rs6323','rs819147','rs819134','rs819171',
        # Detox
        'rs1048943','rs4986883','rs1799814','rs1056836','rs1800440',
        'rs1801272','rs1135840','rs1065852','rs2070676','rs55897648',
        'rs6413419','rs1138272','rs1801280','rs1799931','rs1801279',
        'rs1208','rs4880','rs10012','rs16947','rs1805158',
        # Nutrition
        'rs602662','rs7041','rs1800588','rs174547','rs1799945',
        'rs1800562','rs236918',
        # Cognitive
        'rs1611115','rs165599','rs4570625',
        # Personality
        'rs4570625',
        # Wellness
        'rs1042713','rs1800795','rs7903146',
        # Physical
        'rs12913832','rs1805007','rs17822931',
        # Carrier
        'rs80338939','rs28937900','rs76151636','rs1800546',
        # Ancestry
        'rs1426654','rs16891982','rs3827760','rs2814778',
    ]
    rsid_list = ",".join(f"'{r}'" for r in set(new_rsids))

    # Delete markers that only exist in new panels (safe — these panels didn't exist before)
    op.execute("DELETE FROM panel_marker_configs WHERE panel_id IN ('nutrition','cognitive','personality','wellness','physical','carrier','ancestry')")

    # Delete specific new rsids from existing panels (methylation, detox)
    op.execute(f"DELETE FROM panel_marker_configs WHERE rsid IN ({rsid_list}) AND panel_id IN ('methylation','detox')")
