"""Seed CategoryRule table + autism variant_mappings (OMIM 209850)

This is the canonical seed migration for the category_rules table.
DEFAULT_CATEGORY_RULES has been removed from auto_categorizer.py;
all rule data now lives here so rules can be managed without code deploys.

CategoryRule rows seeded:
  - Base routing rules (clinvar_significance, gene_list, clinvar_condition_keyword,
    gnomad_rare_variant, gnomad_constrained_gene) for all 12 panels
  - Health gene list (BRCA1/2, TP53, APC, MLH1, MSH2, etc.)
  - Carrier gene list (CFTR, HBB, HEXA, SMN1)
  - Autism susceptibility gene lists — cognitive + carrier (OMIM 209850):
    Autosomal: SHANK2/3, CHD8, CNTNAP2, NRXN1-3, SCN2A, DYRK1A, TBR1,
               PTEN, GRIN2B, UBE3A, SLC9A9, SYNGAP1, ADNP, ANKRD11, ARID1B,
               FOXP1, MED13L, SETD5, CHD7, KATNAL2, CNTN4, MECP2
    X-linked:  NLGN3, NLGN4X, PTCHD1, RPL10, TMLHE
  - lifestyle_exclude_keyword rules (severe-condition filter for lifestyle panels)
  - Additional clinvar_condition_keyword rules (metabolizer, albinism, gluten, etc.)

variant_mappings rows seeded:
  - Per-gene autism cognitive data (suggestions, domain) from OMIM 209850
  - Per-gene carrier/susceptibility data for high-penetrance autism genes

Revision ID: 029
Revises: 028
"""
import json
from alembic import op
from sqlalchemy.sql import text

revision = "029_add_autism_gene_mappings"
down_revision = "028_add_gene_to_carrier_status"
branch_labels = None
depends_on = None

# ===========================================================================
# CategoryRule seed data — canonical source of truth after this migration
# (previously lived in DEFAULT_CATEGORY_RULES in auto_categorizer.py)
# ===========================================================================

_dm = lambda **kw: kw  # noqa: E731 — compact inline data dict builder

_ALL_CATEGORY_RULES = [
    # ===================================================================
    # HEALTH
    # ===================================================================
    {"category": "health", "rule_type": "clinvar_significance", "rule_value": "Pathogenic",
     "priority": 10, "mapping_data_template": _dm(risk_level="high", risk_score="3.0x", risk_multiplier=3.0,
         recommendations=["Consult genetic counselor", "Regular screening recommended"])},
    {"category": "health", "rule_type": "clinvar_significance", "rule_value": "Likely_pathogenic",
     "priority": 20, "mapping_data_template": _dm(risk_level="moderate", risk_score="2.0x", risk_multiplier=2.0,
         recommendations=["Discuss with healthcare provider", "Consider additional testing"])},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "cancer",
     "priority": 30, "mapping_data_template": _dm(risk_level="high", risk_score="2.5x", risk_multiplier=2.5,
         recommendations=["Cancer risk screening", "Genetic counseling recommended"])},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "cardiomyopathy",
     "priority": 30, "mapping_data_template": _dm(risk_level="high", risk_score="2.5x", risk_multiplier=2.5,
         recommendations=["Cardiology evaluation", "Echocardiogram recommended"])},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "diabetes",
     "priority": 40, "mapping_data_template": _dm(risk_level="moderate", risk_score="1.5x", risk_multiplier=1.5,
         recommendations=["Monitor blood glucose", "Healthy diet and exercise"])},
    {"category": "health", "rule_type": "clinvar_condition_keyword", "rule_value": "Alzheimer",
     "priority": 40, "mapping_data_template": _dm(risk_level="moderate", risk_score="2.0x", risk_multiplier=2.0,
         recommendations=["Cognitive health monitoring", "Brain-healthy lifestyle"])},
    # Health gene list — hereditary cancer, cardiac, metabolic, neurodegenerative
    {"category": "health", "rule_type": "gene_list",
     "rule_value": "BRCA1,BRCA2,TP53,APC,MLH1,MSH2,VHL,RB1,LDLR,PCSK9,F5,F2,APOE,TCF7L2,PPARG,PARK2,LRRK2,SNCA,APP,PSEN1,PSEN2,GBA",
     "priority": 15, "mapping_data_template": _dm(risk_level="high", risk_score="2.5x", risk_multiplier=2.5,
         recommendations=["Consult genetic counselor", "Regular clinical surveillance recommended"])},
    # gnomAD-based rules
    {"category": "health", "rule_type": "gnomad_rare_variant", "rule_value": "0.001",
     "priority": 50, "mapping_data_template": _dm(risk_level="review", risk_score="1.5x", risk_multiplier=1.5,
         recommendations=["Rare variant — review clinical significance", "Genetic counseling may be beneficial"])},
    {"category": "health", "rule_type": "gnomad_constrained_gene", "rule_value": "pli:0.9",
     "priority": 45, "mapping_data_template": _dm(risk_level="moderate", risk_score="2.0x", risk_multiplier=2.0,
         recommendations=["Gene highly intolerant to loss-of-function", "Variants in this gene warrant careful evaluation"])},

    # ===================================================================
    # DRUG RESPONSES
    # ===================================================================
    {"category": "drug", "rule_type": "gene_list",
     "rule_value": "CYP2D6,CYP2C19,CYP2C9,CYP3A4,CYP3A5,CYP1A2,CYP2B6,DPYD,TPMT,UGT1A1,NUDT15,SLCO1B1,VKORC1,NAT2,ABCB1,CYP2A6,CYP4F2,G6PD,IFNL3,RYR1",
     "priority": 10, "mapping_data_template": _dm(drugs=[["Substrate medications", "variable", "Pharmacogenomic testing recommended"]])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "drug response",
     "priority": 30, "mapping_data_template": _dm(drugs=["Associated medication"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "pharmacokinetic",
     "priority": 30, "mapping_data_template": _dm(drugs=["Associated medication"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "drug metabolism",
     "priority": 30, "mapping_data_template": _dm(drugs=["Associated medication"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "drug sensitivity",
     "priority": 30, "mapping_data_template": _dm(drugs=["Associated medication"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "warfarin",
     "priority": 20, "mapping_data_template": _dm(drugs=["Warfarin"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "statin",
     "priority": 20, "mapping_data_template": _dm(drugs=["Statins"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "metformin",
     "priority": 20, "mapping_data_template": _dm(drugs=["Metformin"])},
    # Additional drug keywords from _CONDITION_CATEGORY_KW
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "metabolizer",
     "priority": 25, "mapping_data_template": _dm(drugs=["Variable-metabolized medication"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "codeine",
     "priority": 20, "mapping_data_template": _dm(drugs=["Codeine / opioids"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "opioid",
     "priority": 20, "mapping_data_template": _dm(drugs=["Opioid analgesics"])},
    {"category": "drug", "rule_type": "clinvar_condition_keyword", "rule_value": "cytochrome",
     "priority": 25, "mapping_data_template": _dm(drugs=["Cytochrome P450 substrate medications"])},
    {"category": "drug", "rule_type": "gnomad_constrained_gene", "rule_value": "pli:0.9",
     "priority": 40, "mapping_data_template": _dm(drugs=[["Substrate medications", "variable", "Gene is highly constrained — dosing may need adjustment"]])},

    # ===================================================================
    # PHYSICAL TRAITS
    # ===================================================================
    {"category": "physical", "rule_type": "gene_list",
     "rule_value": "MC1R,OCA2,HERC2,IRF4,SLC24A5,SLC45A2,KITLG,TYRP1,TYR,ASIP,BNC2,EDAR",
     "priority": 20, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="high",
         description="Gene associated with physical trait variation")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "hair",
     "priority": 30, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "eye color",
     "priority": 30, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "skin",
     "priority": 30, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "height",
     "priority": 30, "mapping_data_template": _dm(category="anthropometric", result="Variant detected", confidence="moderate")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "pigment",
     "priority": 30, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},
    # Additional physical keywords from _CONDITION_CATEGORY_KW
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "albinism",
     "priority": 30, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="high")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "freckle",
     "priority": 35, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "baldness",
     "priority": 35, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},
    {"category": "physical", "rule_type": "clinvar_condition_keyword", "rule_value": "earlobe",
     "priority": 35, "mapping_data_template": _dm(category="appearance", result="Variant detected", confidence="moderate")},

    # ===================================================================
    # NUTRITION
    # ===================================================================
    {"category": "nutrition", "rule_type": "gene_list",
     "rule_value": "MTHFR,FUT2,LCT,MCM6,FADS1,FADS2,BCMO1,SLC23A1,GC,CYP2R1,VDR,TCN1,TCN2,NBPF3,HFE,TF,TMPRSS6,SLC30A8",
     "priority": 10, "mapping_data_template": _dm(metabolism="variable", recommendations=["Consider testing nutrient levels"],
         sensitivity="moderate")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "lactose",
     "priority": 30, "mapping_data_template": _dm(nutrient="Lactose", metabolism="intolerant",
         recommendations=["Avoid dairy or use lactase supplements"], sensitivity="high")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "celiac",
     "priority": 30, "mapping_data_template": _dm(nutrient="Gluten", metabolism="intolerant",
         recommendations=["Strict gluten-free diet"], sensitivity="high")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "vitamin D",
     "priority": 30, "mapping_data_template": _dm(nutrient="Vitamin D", metabolism="variable",
         recommendations=["Monitor vitamin D levels", "Consider supplementation"], sensitivity="moderate")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "iron",
     "priority": 30, "mapping_data_template": _dm(nutrient="Iron", metabolism="variable",
         recommendations=["Monitor iron levels"], sensitivity="moderate")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "folate",
     "priority": 30, "mapping_data_template": _dm(nutrient="Folate", metabolism="variable",
         recommendations=["Consider methylfolate supplementation"], sensitivity="moderate")},
    # Additional nutrition keywords from _CONDITION_CATEGORY_KW
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "gluten",
     "priority": 30, "mapping_data_template": _dm(nutrient="Gluten", metabolism="variable",
         recommendations=["Consider gluten-free diet trial"], sensitivity="moderate")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "iron overload",
     "priority": 25, "mapping_data_template": _dm(nutrient="Iron", metabolism="elevated absorption",
         recommendations=["Monitor serum ferritin", "Limit heme iron intake"], sensitivity="high")},
    {"category": "nutrition", "rule_type": "clinvar_condition_keyword", "rule_value": "hemochromatosis",
     "priority": 25, "mapping_data_template": _dm(nutrient="Iron", metabolism="elevated absorption",
         recommendations=["Therapeutic phlebotomy may be indicated", "Monitor transferrin saturation"], sensitivity="high")},

    # ===================================================================
    # SPORTS / PERFORMANCE
    # ===================================================================
    {"category": "sports", "rule_type": "gene_list",
     "rule_value": "ACTN3,ACE,PPARGC1A,PPARA,ADRB2,ADRB3,NOS3,VEGFA,HIF1A,EPAS1,AMPD1,CKM,BDNF,IL6,TNF,COL1A1,COL5A1,GDF5,MMP3",
     "priority": 10, "mapping_data_template": _dm(advantage="Genetic variant associated with athletic performance",
         recommendations=["Tailored training program recommended"],
         advice="Consult sports medicine specialist for personalized program")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "muscle",
     "priority": 30, "mapping_data_template": _dm(advantage="Muscle-related genetic variant",
         recommendations=["Strength assessment recommended"], advice="Consider consulting exercise physiologist")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "myopathy",
     "priority": 30, "mapping_data_template": _dm(advantage="Variant affecting muscle function",
         recommendations=["Medical evaluation before intense exercise"],
         advice="Work with a specialist for safe exercise programming")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "exercise intolerance",
     "priority": 30, "mapping_data_template": _dm(advantage="Exercise tolerance variant detected",
         recommendations=["Gradual exercise progression"],
         advice="Medical clearance recommended before starting exercise program")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "rhabdomyolysis",
     "priority": 20, "mapping_data_template": _dm(advantage="Rhabdomyolysis risk variant",
         recommendations=["Avoid extreme exertion", "Stay well-hydrated"],
         advice="Medical supervision recommended for high-intensity training")},
    # Additional sports keywords from _CONDITION_CATEGORY_KW
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "malignant hyperthermia",
     "priority": 20, "mapping_data_template": _dm(advantage="Anesthesia/exercise heat risk",
         recommendations=["Avoid certain anesthetics", "Alert anesthesiologist before surgery"],
         advice="Inform healthcare providers of this genetic risk factor")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "athletic",
     "priority": 35, "mapping_data_template": _dm(advantage="Athletic performance variant",
         recommendations=["Consider sport-specific training optimization"], advice="Personalized program recommended")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "endurance",
     "priority": 35, "mapping_data_template": _dm(advantage="Endurance capacity variant",
         recommendations=["Optimize aerobic training"], advice="VO2 max testing may be informative")},
    {"category": "sports", "rule_type": "clinvar_condition_keyword", "rule_value": "sprint",
     "priority": 35, "mapping_data_template": _dm(advantage="Speed/power variant",
         recommendations=["Consider power-based training"], advice="Assess fast-twitch muscle fiber composition")},

    # ===================================================================
    # COGNITIVE
    # ===================================================================
    {"category": "cognitive", "rule_type": "gene_list",
     "rule_value": "COMT,BDNF,DRD2,DRD4,KIBRA,APOE,CHRNA4,NRXN1,DISC1,NRG1,DTNBP1,AKT1",
     "priority": 10, "mapping_data_template": _dm(score="variable", percentile=50,
         suggestions=["Cognitive enrichment activities", "Brain-healthy lifestyle"])},
    # Autism susceptibility genes — cognitive panel (OMIM 209850)
    {"category": "cognitive", "rule_type": "gene_list",
     "rule_value": (
         "SHANK2,SHANK3,NRXN1,NRXN2,NRXN3,CHD8,CNTNAP2,SLC9A9,DYRK1A,TBR1,"
         "GRIN2B,SYNGAP1,SCN2A,UBE3A,CNTN4,SETD5,ADNP,ARID1B,FOXP1,MED13L,"
         "KATNAL2,CHD7,MECP2,PTEN"
     ),
     "priority": 12, "mapping_data_template": _dm(score="variable", percentile=50,
         suggestions=["Consider neurodevelopmental evaluation",
                      "Consult clinical geneticist for ASD-related gene variant",
                      "Early intervention may be beneficial"])},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "intellectual disability",
     "priority": 30, "mapping_data_template": _dm(score="reduced", percentile=30,
         suggestions=["Professional cognitive assessment recommended"])},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "memory",
     "priority": 30, "mapping_data_template": _dm(score="variable", percentile=50,
         suggestions=["Memory exercises", "Cognitive training programs"])},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "learning disability",
     "priority": 30, "mapping_data_template": _dm(score="variable", percentile=40,
         suggestions=["Educational assessment recommended", "Adaptive learning strategies"])},
    {"category": "cognitive", "rule_type": "clinvar_condition_keyword", "rule_value": "neurodegenerat",
     "priority": 30, "mapping_data_template": _dm(score="variable", percentile=45,
         suggestions=["Cognitive monitoring", "Neuroprotective lifestyle habits"])},

    # ===================================================================
    # PERSONALITY / BEHAVIOR
    # ===================================================================
    {"category": "personality", "rule_type": "gene_list",
     "rule_value": "SLC6A4,DRD4,DRD2,MAOA,COMT,OXTR,AVPR1A,HTR2A,FKBP5,CRHR1,TPH2",
     "priority": 10, "mapping_data_template": _dm(tendency="variable", confidence="moderate",
         insights=["Genetic variation may influence behavioral tendencies"])},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "anxiety",
     "priority": 30, "mapping_data_template": _dm(tendency="variable", confidence="low",
         insights=["Genetic variant associated with anxiety-related traits"])},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "depression",
     "priority": 30, "mapping_data_template": _dm(tendency="variable", confidence="low",
         insights=["Genetic variant associated with mood regulation"])},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "behavior",
     "priority": 30, "mapping_data_template": _dm(tendency="variable", confidence="low",
         insights=["Genetic variant associated with behavioral phenotype"])},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "autism",
     "priority": 30, "mapping_data_template": _dm(tendency="variable", confidence="low",
         insights=["Genetic variant associated with neurodevelopmental traits"])},
    {"category": "personality", "rule_type": "clinvar_condition_keyword", "rule_value": "schizophrenia",
     "priority": 30, "mapping_data_template": _dm(tendency="variable", confidence="low",
         insights=["Genetic variant associated with neuropsychiatric traits"])},

    # ===================================================================
    # CARRIER STATUS
    # ===================================================================
    # Carrier gene list (common recessive disease genes)
    {"category": "carrier", "rule_type": "gene_list",
     "rule_value": "CFTR,HBB,HEXA,SMN1",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    # Autism high-penetrance / X-linked genes — carrier susceptibility
    {"category": "carrier", "rule_type": "gene_list",
     "rule_value": "NLGN3,NLGN4X,MECP2,PTCHD1,RPL10,TMLHE,SHANK3,PTEN,CHD8,DYRK1A,ADNP,SYNGAP1",
     "priority": 12, "mapping_data_template": _dm(status="susceptibility", inheritance_pattern="x_linked_or_autosomal_dominant",
         notes="ASD susceptibility gene — consult genetic counselor for inheritance assessment")},
    # Condition keyword routes to carrier
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "cystic fibrosis",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "sickle cell",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "thalassemia",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Tay-Sachs",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "hemophilia",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="x_linked")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Gaucher",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "phenylketonuria",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Duchenne",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="x_linked")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "Wilson disease",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},
    {"category": "carrier", "rule_type": "clinvar_condition_keyword", "rule_value": "spinal muscular atrophy",
     "priority": 10, "mapping_data_template": _dm(status="carrier", inheritance_pattern="autosomal_recessive")},

    # ===================================================================
    # WELLNESS
    # ===================================================================
    {"category": "wellness", "rule_type": "gene_list",
     "rule_value": "CLOCK,PER2,PER3,CRY1,ADORA2A,ADA,DEC2,BHLHE41,NR1D1,TNF,IL6,IL10,CRP,LEPR,FTO,MC4R",
     "priority": 10, "mapping_data_template": _dm(predisposition="variable", score="50",
         recommendations=["Monitor wellness indicators", "Healthy lifestyle habits"])},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "sleep",
     "priority": 30, "mapping_data_template": _dm(predisposition="variable", score="50",
         recommendations=["Sleep hygiene optimization", "Consider sleep study"])},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "obesity",
     "priority": 30, "mapping_data_template": _dm(predisposition="elevated risk", score="40",
         recommendations=["Regular physical activity", "Balanced nutrition plan"])},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "inflammation",
     "priority": 30, "mapping_data_template": _dm(predisposition="variable", score="50",
         recommendations=["Anti-inflammatory diet", "Monitor inflammatory markers"])},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "circadian",
     "priority": 30, "mapping_data_template": _dm(predisposition="variable", score="50",
         recommendations=["Consistent sleep schedule", "Light exposure management"])},
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "fatigue",
     "priority": 30, "mapping_data_template": _dm(predisposition="variable", score="45",
         recommendations=["Energy management strategies", "Evaluate underlying causes"])},
    # Additional wellness keywords from _CONDITION_CATEGORY_KW
    {"category": "wellness", "rule_type": "clinvar_condition_keyword", "rule_value": "bmi",
     "priority": 35, "mapping_data_template": _dm(predisposition="variable", score="50",
         recommendations=["BMI and metabolic monitoring", "Lifestyle intervention as appropriate"])},

    # ===================================================================
    # METHYLATION
    # ===================================================================
    {"category": "methylation", "rule_type": "gene_list",
     "rule_value": "MTHFR,MTR,MTRR,COMT,CBS,BHMT,MAT1A,AHCY,SHMT1,SHMT2,FOLR1,FOLR2,DHFR,TYMS,TCN2,MTHFD1",
     "priority": 10, "mapping_data_template": _dm(capacity="variable",
         supplements=["Consider methylfolate", "Monitor B12 levels"])},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "methylation",
     "priority": 30, "mapping_data_template": _dm(capacity="reduced",
         supplements=["Methylfolate supplementation", "B12 monitoring"])},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "folate",
     "priority": 30, "mapping_data_template": _dm(capacity="reduced",
         supplements=["Methylfolate", "Folinic acid consideration"])},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "homocysteine",
     "priority": 30, "mapping_data_template": _dm(capacity="reduced",
         supplements=["B6, B12, and folate supplementation", "Homocysteine monitoring"])},
    {"category": "methylation", "rule_type": "clinvar_condition_keyword", "rule_value": "neural tube",
     "priority": 30, "mapping_data_template": _dm(capacity="reduced",
         supplements=["Adequate folate critical", "Prenatal supplementation"])},

    # ===================================================================
    # DETOXIFICATION
    # ===================================================================
    {"category": "detox", "rule_type": "gene_list",
     "rule_value": "CYP1A1,CYP1A2,CYP1B1,CYP2E1,CYP2A6,GSTM1,GSTT1,GSTP1,NAT1,NAT2,NQO1,EPHX1,SOD2,CAT,GPX1,PON1,ALDH2",
     "priority": 10, "mapping_data_template": _dm(phase="variable", capacity="variable",
         sensitivity="moderate", recommendations=["Support detoxification pathways"])},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "glutathione",
     "priority": 30, "mapping_data_template": _dm(phase="phase2", capacity="variable",
         sensitivity="moderate", recommendations=["Support glutathione levels", "Cruciferous vegetables"])},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "oxidative stress",
     "priority": 30, "mapping_data_template": _dm(phase="antioxidant", capacity="variable",
         sensitivity="elevated", recommendations=["Antioxidant-rich diet", "Minimize toxin exposure"])},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "acetylation",
     "priority": 30, "mapping_data_template": _dm(phase="phase2", capacity="variable",
         sensitivity="moderate", recommendations=["Monitor for drug acetylation effects"])},
    {"category": "detox", "rule_type": "clinvar_condition_keyword", "rule_value": "chemical sensitivity",
     "priority": 30, "mapping_data_template": _dm(phase="variable", capacity="reduced",
         sensitivity="elevated", recommendations=["Minimize chemical exposures", "Air purification"])},

    # ===================================================================
    # ANCESTRY
    # ===================================================================
    {"category": "ancestry", "rule_type": "gene_list",
     "rule_value": "SLC24A5,SLC45A2,HERC2,OCA2,MC1R,EDAR,ABCC11,LCT,ALDH2,ADH1B",
     "priority": 30, "mapping_data_template": _dm(population="various", confidence="low")},

    # ===================================================================
    # LIFESTYLE EXCLUSION KEYWORDS
    # Conditions too severe for lifestyle panels (sports, physical, nutrition, etc.)
    # Populated into _SEVERE_EXCLUSION_KW at startup via init_categorizer_data()
    # ===================================================================
    *[
        {"category": "__lifestyle_filter__", "rule_type": "lifestyle_exclude_keyword",
         "rule_value": kw, "priority": 1, "mapping_data_template": None}
        for kw in [
            "cardiomyopathy", "dystrophy", "atrophy", "encephalopathy",
            "tumor", "lymphoma", "leukemia", "carcinoma", "neoplasm",
            "neurodegenerat", "amyotrophic", "huntington", "parkinson",
            "epilepsy", "seizure", "stroke", "aneurysm", "failure",
            "fibrosis", "cirrhosis", "nephropathy", "immunodeficiency",
            "periodic fever", "cryopyrin", "congenital", "lethal", "fatal",
        ]
    ],
]


# ---------------------------------------------------------------------------
# Autism susceptibility genes — cognitive category (neurodevelopmental risk)
# ---------------------------------------------------------------------------
# All well-established ASD susceptibility genes from OMIM 209850 and related
# entries. These are gene-level mappings: any moderate/high-impact variant in
# these genes will generate a cognitive insight about neurodevelopmental risk.

_COGNITIVE_AUTISM_GENES = [
    # Synaptic scaffolding / cell adhesion
    {
        "gene": "SHANK3",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "Consider neurodevelopmental assessment",
            "Early speech and behavioral intervention may be beneficial",
            "Consult pediatric neurologist or clinical geneticist",
            "22q13.3 deletion / Phelan-McDermid syndrome risk locus",
        ],
    },
    {
        "gene": "SHANK2",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "Consider neurodevelopmental assessment",
            "Variants in SHANK2 (AUTS17) associated with ASD and intellectual disability",
            "Consult clinical geneticist",
        ],
    },
    {
        "gene": "NRXN1",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "NRXN1 deletions are among the most common genetic risk factors for ASD",
            "Consider neurodevelopmental evaluation",
            "May also be associated with schizophrenia susceptibility",
            "Consult clinical geneticist",
        ],
    },
    {
        "gene": "NRXN2",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "NRXN2 loss-of-function variants associated with ASD",
            "Consider neurodevelopmental evaluation and genetic counseling",
        ],
    },
    {
        "gene": "NRXN3",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "Rare NRXN3 deletions reported in ASD spectrum (Vaags et al., 2012)",
            "Consider neurodevelopmental evaluation and genetic counseling",
        ],
    },
    {
        "gene": "CNTNAP2",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "CNTNAP2 (AUTS15) on 7q35-q36 associated with ASD susceptibility",
            "Also associated with cortical dysplasia and focal epilepsy",
            "Consider neurodevelopmental and neurological evaluation",
        ],
    },
    # Chromatin remodeling / transcription
    {
        "gene": "CHD8",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "CHD8 (AUTS18) is one of the most consistently replicated ASD risk genes",
            "Associated with macrocephaly, GI problems, and characteristic facial features",
            "Consider neurodevelopmental assessment and head circumference measurement",
            "Consult clinical geneticist",
        ],
    },
    {
        "gene": "DYRK1A",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "DYRK1A haploinsufficiency associated with ASD and microcephaly",
            "Truncating mutations are among the most recurrent in sporadic ASD",
            "Consider neurodevelopmental evaluation including head circumference",
        ],
    },
    {
        "gene": "TBR1",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "TBR1 is a transcription factor critical for cortical neuron development",
            "De novo truncating mutations strongly associated with sporadic ASD",
            "Consider neurodevelopmental evaluation",
        ],
    },
    {
        "gene": "SETD5",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "SETD5 loss-of-function variants associated with ASD and intellectual disability",
            "Consider neurodevelopmental evaluation and genetic counseling",
        ],
    },
    {
        "gene": "ADNP",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "ADNP syndrome (Helsmoortel-Van der Aa syndrome) caused by de novo ADNP mutations",
            "One of the most frequent single-gene causes of ASD",
            "Consider clinical genetics consultation",
        ],
    },
    {
        "gene": "ARID1B",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "ARID1B (Coffin-Siris syndrome) — de novo mutations associated with ASD and ID",
            "Consider neurodevelopmental evaluation",
        ],
    },
    # Synaptic signaling
    {
        "gene": "SYNGAP1",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "SYNGAP1 haploinsufficiency is a common cause of non-syndromic intellectual disability with ASD features",
            "Consider neurological and neurodevelopmental evaluation",
        ],
    },
    {
        "gene": "SCN2A",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "SCN2A gain/loss-of-function variants associated with ASD and epileptic encephalopathy",
            "Consider neurological evaluation including EEG",
            "Associated with early-onset seizures in some cases",
        ],
    },
    {
        "gene": "GRIN2B",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "GRIN2B (NMDA receptor subunit) variants associated with ASD and intellectual disability",
            "Consider neurodevelopmental evaluation",
        ],
    },
    # Tumor suppressor / PI3K pathway
    {
        "gene": "PTEN",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "PTEN mutations associated with macrocephalic autism spectrum disorder",
            "Also associated with Cowden syndrome and elevated cancer risk",
            "If head circumference is significantly elevated (≥2.5 SD), consider PTEN testing",
            "Consult clinical geneticist — multi-system cancer surveillance may be warranted",
        ],
    },
    # Ubiquitin pathway
    {
        "gene": "UBE3A",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "UBE3A (Angelman syndrome / dup15q ASD) — copy number and expression changes associated with ASD",
            "Consider imprinting analysis and neurodevelopmental evaluation",
        ],
    },
    # Ion channels / transporters
    {
        "gene": "SLC9A9",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "SLC9A9 (AUTS16) on 3q24 associated with ASD susceptibility",
            "Consider neurodevelopmental evaluation",
        ],
    },
    # Contact proteins
    {
        "gene": "CNTN4",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "CNTN4 CNVs reported in ASD (Roohi et al., 2009)",
            "Consider neurodevelopmental evaluation and genetic counseling",
        ],
    },
    # X-linked ASD genes (cognitive)
    {
        "gene": "NLGN3",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "NLGN3 (AUTSX1) on Xq13 — neuroligin-3 mutations associated with X-linked ASD",
            "R451C missense linked to increased inhibitory synaptic transmission in mouse models",
            "Consider genetic counseling given X-linked inheritance",
        ],
    },
    {
        "gene": "NLGN4X",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "NLGN4X (AUTSX2) on Xp22.32 — neuroligin-4 mutations associated with X-linked ASD",
            "Consider genetic counseling given X-linked inheritance",
        ],
    },
    {
        "gene": "PTCHD1",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "PTCHD1 (AUTSX4) region Xp22.11 — deletions associated with ASD and intellectual disability",
            "Consider X-linked inheritance counseling",
        ],
    },
    {
        "gene": "TMLHE",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "TMLHE (AUTSX6) deletion associated with ASD — involved in carnitine biosynthesis",
            "Consider carnitine supplementation discussion with physician",
            "Consider X-linked inheritance counseling",
        ],
    },
    # Additional high-confidence ASD genes from large exome studies
    {
        "gene": "KATNAL2",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "KATNAL2 recurrent disruptive mutations found in sporadic ASD cohorts",
            "Consider neurodevelopmental evaluation",
        ],
    },
    {
        "gene": "CHD7",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "CHD7 (CHARGE syndrome) — rare mutations associated with ASD features",
            "Consider clinical genetics evaluation for CHARGE syndrome features",
        ],
    },
    {
        "gene": "FOXP1",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "FOXP1 haploinsufficiency associated with ASD, intellectual disability, and language disorder",
            "Consider speech-language therapy evaluation",
        ],
    },
    {
        "gene": "MED13L",
        "domain": "neurodevelopmental_function",
        "score": "variable",
        "percentile": 50,
        "suggestions": [
            "MED13L syndrome — intellectual disability, ASD features, speech and motor delay",
            "Consider neurodevelopmental evaluation and speech therapy",
        ],
    },
]

# ---------------------------------------------------------------------------
# Carrier / susceptibility mappings for Mendelian / X-linked autism genes
# ---------------------------------------------------------------------------
_CARRIER_AUTISM_GENES = [
    {
        "gene": "NLGN3",
        "condition": "X-linked autism susceptibility 1 (AUTSX1)",
        "status": "susceptibility",
        "inheritance_pattern": "x_linked_dominant",
    },
    {
        "gene": "NLGN4X",
        "condition": "X-linked autism susceptibility 2 (AUTSX2)",
        "status": "susceptibility",
        "inheritance_pattern": "x_linked_dominant",
    },
    {
        "gene": "PTCHD1",
        "condition": "X-linked autism susceptibility 4 (AUTSX4)",
        "status": "susceptibility",
        "inheritance_pattern": "x_linked_dominant",
    },
    {
        "gene": "RPL10",
        "condition": "X-linked autism susceptibility 5 (AUTSX5)",
        "status": "susceptibility",
        "inheritance_pattern": "x_linked_recessive",
    },
    {
        "gene": "TMLHE",
        "condition": "X-linked autism susceptibility 6 (AUTSX6) / TMLHE deficiency",
        "status": "susceptibility",
        "inheritance_pattern": "x_linked_recessive",
    },
    {
        "gene": "SHANK3",
        "condition": "Phelan-McDermid syndrome / SHANK3-related autism",
        "status": "susceptibility",
        "inheritance_pattern": "autosomal_dominant",
    },
    {
        "gene": "PTEN",
        "condition": "PTEN hamartoma tumor syndrome / macrocephalic autism",
        "status": "susceptibility",
        "inheritance_pattern": "autosomal_dominant",
    },
    {
        "gene": "CHD8",
        "condition": "CHD8-related autism spectrum disorder (AUTS18)",
        "status": "susceptibility",
        "inheritance_pattern": "autosomal_dominant",
    },
    {
        "gene": "DYRK1A",
        "condition": "DYRK1A syndrome (intellectual disability and microcephalic autism)",
        "status": "susceptibility",
        "inheritance_pattern": "autosomal_dominant",
    },
    {
        "gene": "ADNP",
        "condition": "Helsmoortel-Van der Aa syndrome (ADNP-related ASD)",
        "status": "susceptibility",
        "inheritance_pattern": "autosomal_dominant",
    },
    {
        "gene": "SYNGAP1",
        "condition": "SYNGAP1 intellectual disability with autism features",
        "status": "susceptibility",
        "inheritance_pattern": "autosomal_dominant",
    },
]


_INSERT_RULE_SQL = text("""
    INSERT INTO category_rules
        (category, rule_type, rule_value, priority, mapping_data_template, is_active)
    SELECT :category, :rule_type, :rule_value, :priority,
           CASE WHEN :template IS NULL THEN NULL ELSE cast(:template AS jsonb) END,
           true
    WHERE NOT EXISTS (
        SELECT 1 FROM category_rules
        WHERE category = :category
          AND rule_type = :rule_type
          AND rule_value = :rule_value
    )
""")

_DELETE_RULE_SQL = text("""
    DELETE FROM category_rules
    WHERE category = :category AND rule_type = :rule_type AND rule_value = :rule_value
""")


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Seed all CategoryRule rows
    # ------------------------------------------------------------------
    for rule in _ALL_CATEGORY_RULES:
        tpl = rule.get("mapping_data_template")
        conn.execute(_INSERT_RULE_SQL, {
            "category": rule["category"],
            "rule_type": rule["rule_type"],
            "rule_value": rule["rule_value"],
            "priority": rule.get("priority", 50),
            "template": json.dumps(tpl) if tpl is not None else None,
        })

    # ------------------------------------------------------------------
    # 2. Insert cognitive (neurodevelopmental) per-gene variant_mappings
    # ------------------------------------------------------------------
    for g in _COGNITIVE_AUTISM_GENES:
        data = {
            "domain": g["domain"],
            "score": g["score"],
            "percentile": g["percentile"],
            "suggestions": g["suggestions"],
            "gene": g["gene"],
            "source": "omim_209850",
        }
        conn.execute(
            text(
                """
                INSERT INTO variant_mappings
                    (category, map_type, key, data, is_active, is_auto_discovered)
                VALUES
                    (:category, :map_type, :key, cast(:data as json), true, false)
                ON CONFLICT (category, map_type, key) DO NOTHING
                """
            ),
            {
                "category": "cognitive",
                "map_type": "gene",
                "key": g["gene"],
                "data": json.dumps(data),
            },
        )

    # Insert carrier / susceptibility mappings
    for g in _CARRIER_AUTISM_GENES:
        data = {
            "condition": g["condition"],
            "status": g["status"],
            "inheritance_pattern": g["inheritance_pattern"],
            "gene": g["gene"],
            "source": "omim_209850",
        }
        conn.execute(
            text(
                """
                INSERT INTO variant_mappings
                    (category, map_type, key, data, is_active, is_auto_discovered)
                VALUES
                    (:category, :map_type, :key, cast(:data as json), true, false)
                ON CONFLICT (category, map_type, key) DO NOTHING
                """
            ),
            {
                "category": "carrier",
                "map_type": "gene",
                "key": g["gene"],
                "data": json.dumps(data),
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Remove per-gene autism variant_mappings
    all_genes = [g["gene"] for g in _COGNITIVE_AUTISM_GENES]
    for gene in all_genes:
        conn.execute(
            text(
                "DELETE FROM variant_mappings WHERE category = 'cognitive' AND map_type = 'gene' "
                "AND key = :key AND data::jsonb->>'source' = 'omim_209850'"
            ),
            {"key": gene},
        )
    carrier_genes = [g["gene"] for g in _CARRIER_AUTISM_GENES]
    for gene in carrier_genes:
        conn.execute(
            text(
                "DELETE FROM variant_mappings WHERE category = 'carrier' AND map_type = 'gene' "
                "AND key = :key AND data::jsonb->>'source' = 'omim_209850'"
            ),
            {"key": gene},
        )

    # Remove all CategoryRule rows seeded by this migration
    for rule in _ALL_CATEGORY_RULES:
        conn.execute(_DELETE_RULE_SQL, {
            "category": rule["category"],
            "rule_type": rule["rule_type"],
            "rule_value": rule["rule_value"],
        })
