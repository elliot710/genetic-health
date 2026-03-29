"""
Multi-source variant categorizer
=================================
Evaluates annotation data from ALL available sources (ClinVar local,
Ensembl VEP, gnomAD, AlphaMissense, SNPedia, 1000 Genomes, etc.) to
produce high-confidence category assignments with source attribution.

Used by:
  - auto_categorizer.py (batch annotation-based pass)
  - variant_routes.py   (real-time categorization on lookup)
  - analysis_service.py (per-user-variant enrichment)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Gene → category maps ────────────────────────────────────────────
GENE_CATEGORY_MAP: Dict[str, List[str]] = {
    # Pharmacogenomics / drug metabolism
    "CYP2D6": ["drug"], "CYP2C19": ["drug"], "CYP2C9": ["drug"],
    "CYP3A4": ["drug"], "CYP3A5": ["drug"], "CYP1A2": ["drug"],
    "CYP2B6": ["drug"], "CYP2A6": ["drug"], "CYP4F2": ["drug"],
    "DPYD": ["drug"], "TPMT": ["drug"], "UGT1A1": ["drug"],
    "NUDT15": ["drug"], "SLCO1B1": ["drug"], "VKORC1": ["drug"],
    "NAT2": ["drug", "detox"], "ABCB1": ["drug"], "G6PD": ["drug"],
    "IFNL3": ["drug"], "RYR1": ["drug"],
    # Health / disease
    "BRCA1": ["health"], "BRCA2": ["health"], "TP53": ["health"],
    "APC": ["health"], "MLH1": ["health"], "MSH2": ["health"],
    "PTEN": ["health"], "VHL": ["health"], "RB1": ["health"],
    "LDLR": ["health"], "PCSK9": ["health"], "F5": ["health"],
    "F2": ["health"], "APOE": ["health", "cognitive"],
    "TCF7L2": ["health"], "PPARG": ["health"],
    "PARK2": ["health"], "LRRK2": ["health"], "SNCA": ["health"],
    "APP": ["health"], "PSEN1": ["health"], "PSEN2": ["health"],
    "GBA": ["health"],
    # Physical traits
    "MC1R": ["physical"], "OCA2": ["physical"], "HERC2": ["physical"],
    "IRF4": ["physical"], "SLC24A5": ["physical", "ancestry"],
    "SLC45A2": ["physical", "ancestry"], "KITLG": ["physical"],
    "TYRP1": ["physical"], "TYR": ["physical"], "ASIP": ["physical"],
    "BNC2": ["physical"], "EDAR": ["physical", "ancestry"],
    # Sports / fitness
    "ACTN3": ["sports"], "ACE": ["sports"], "PPARGC1A": ["sports"],
    "PPARA": ["sports"], "ADRB2": ["sports"], "ADRB3": ["sports"],
    "NOS3": ["sports"], "VEGFA": ["sports"], "HIF1A": ["sports"],
    "EPAS1": ["sports"], "AMPD1": ["sports"], "CKM": ["sports"],
    "COL1A1": ["sports"], "COL5A1": ["sports"], "GDF5": ["sports"],
    "MMP3": ["sports"],
    # Nutrition
    "LCT": ["nutrition"], "MCM6": ["nutrition"], "FADS1": ["nutrition"],
    "FADS2": ["nutrition"], "BCMO1": ["nutrition"], "SLC23A1": ["nutrition"],
    "GC": ["nutrition"], "CYP2R1": ["nutrition"], "VDR": ["nutrition"],
    "TCN1": ["nutrition"], "TCN2": ["nutrition", "methylation"],
    "HFE": ["nutrition"], "TF": ["nutrition"], "TMPRSS6": ["nutrition"],
    "SLC30A8": ["nutrition"], "FUT2": ["nutrition"],
    # Carrier panel
    "CFTR": ["carrier"], "HBB": ["carrier"], "HEXA": ["carrier"],
    "SMN1": ["carrier"],
    # Cognitive
    "COMT": ["cognitive", "methylation"], "BDNF": ["cognitive", "sports"],
    "DRD2": ["cognitive", "personality"], "DRD4": ["cognitive", "personality"],
    "KIBRA": ["cognitive"], "CHRNA4": ["cognitive"],
    "NRXN1": ["cognitive"], "DISC1": ["cognitive"],
    # Personality
    "SLC6A4": ["personality"], "MAOA": ["personality"],
    "OXTR": ["personality"], "AVPR1A": ["personality"],
    "HTR2A": ["personality"], "FKBP5": ["personality"],
    "CRHR1": ["personality"], "TPH2": ["personality"],
    # Wellness
    "CLOCK": ["wellness"], "PER2": ["wellness"], "PER3": ["wellness"],
    "CRY1": ["wellness"], "ADORA2A": ["wellness"], "ADA": ["wellness"],
    "FTO": ["wellness", "nutrition"], "MC4R": ["wellness"],
    "LEPR": ["wellness"], "TNF": ["wellness"], "IL6": ["wellness"],
    "IL10": ["wellness"], "CRP": ["wellness"],
    # Methylation
    "MTHFR": ["methylation", "nutrition"], "MTR": ["methylation"],
    "MTRR": ["methylation"], "CBS": ["methylation"],
    "BHMT": ["methylation"], "MAT1A": ["methylation"],
    "AHCY": ["methylation"], "SHMT1": ["methylation"],
    "SHMT2": ["methylation"], "DHFR": ["methylation"],
    "TYMS": ["methylation"], "MTHFD1": ["methylation"],
    # Detox
    "CYP1A1": ["detox"], "CYP1B1": ["detox"], "CYP2E1": ["detox"],
    "GSTM1": ["detox"], "GSTT1": ["detox"], "GSTP1": ["detox"],
    "NAT1": ["detox"], "NQO1": ["detox"], "EPHX1": ["detox"],
    "SOD2": ["detox"], "CAT": ["detox"], "GPX1": ["detox"],
    "PON1": ["detox"], "ALDH2": ["detox", "ancestry"],
    # Ancestry
    "ABCC11": ["ancestry"],
    "ADH1B": ["ancestry"],
}

# ── Severe condition keywords for lifestyle panels ──────────────────
_SEVERE_EXCLUSION_KW = frozenset([
    "cardiomyopathy", "dystrophy", "atrophy", "encephalopathy",
    "cancer", "tumor", "lymphoma", "leukemia", "carcinoma", "neoplasm",
    "neurodegenerat", "amyotrophic", "huntington", "parkinson",
    "epilepsy", "seizure", "stroke", "aneurysm",
    "failure", "fibrosis", "cirrhosis", "nephropathy",
    "immunodeficiency", "periodic fever", "cryopyrin",
    "congenital", "lethal", "fatal", "death",
    "syndrome", "aplastic", "retinitis", "blindness",
    "deafness", "hearing loss", "spasticity",
])

_LIFESTYLE_CATEGORIES = frozenset([
    "sports", "physical", "personality", "nutrition", "wellness",
    "methylation", "detox", "cognitive", "ancestry",
])

# ClinVar significances considered clinically meaningful
_PATHOGENIC_SIGS = {"pathogenic", "likely pathogenic", "likely_pathogenic",
                    "pathogenic/likely_pathogenic", "pathogenic/likely pathogenic"}
_RISK_SIGS = {"risk_factor", "risk factor", "association", "protective"}
_DRUG_SIGS = {"drug_response", "drug response"}
_BENIGN_SIGS = {"benign", "likely benign", "likely_benign",
                "benign/likely_benign", "benign/likely benign"}

# ── Category-specific condition keywords ────────────────────────────
_CONDITION_CATEGORY_KW: Dict[str, List[str]] = {
    "drug": ["drug response", "pharmacokin", "metabolism", "metabolizer",
             "statin", "warfarin", "metformin", "codeine", "opioid", "cytochrome"],
    "carrier": ["cystic fibrosis", "thalassemia", "sickle cell", "tay-sachs",
                "gaucher", "phenylketonuria", "duchenne", "hemophilia",
                "wilson disease", "spinal muscular atrophy"],
    "physical": ["hair color", "eye color", "pigment", "albinism", "freckle",
                 "baldness", "earlobe"],
    "nutrition": ["lactose", "celiac", "gluten", "vitamin d", "folate",
                  "iron overload", "hemochromatosis"],
    "wellness": ["circadian", "sleep", "obesity", "bmi", "fatigue"],
    "sports": ["exercise intolerance", "rhabdomyolysis", "malignant hyperthermia",
               "athletic", "endurance", "sprint"],
    "methylation": ["methylation", "homocysteine", "folate", "neural tube"],
    "detox": ["glutathione", "oxidative stress", "acetylation", "chemical sensitivity"],
    "cognitive": ["memory", "learning disability"],
}


# ── Primary dedup field per category ────────────────────────────────
_PRIMARY_FIELD = {
    "health": "condition", "carrier": "condition",
    "drug": "drug", "nutrition": "nutrient",
    "sports": "category", "wellness": "metric",
    "cognitive": "domain", "personality": "trait",
    "physical": "trait", "methylation": "gene",
    "detox": "gene", "rare": "condition", "uncommon": "condition",
}


def _conf_to_level(conf: float) -> str:
    """Convert a 0.0-1.0 confidence float to a string severity level."""
    if conf >= 0.7:
        return "high"
    if conf >= 0.4:
        return "moderate"
    return "low"


# ── Category-aware label helpers ────────────────────────────────────

# Maps category → semantic suffix for non-primary fields when we only
# have a gene name (i.e. no ClinVar condition).  These produce labels
# like "CYP2D6 metabolism" instead of "CYP2D6 variant" as a nutrient.
_CATEGORY_FIELD_SUFFIX: Dict[str, Dict[str, str]] = {
    "nutrition":    {"nutrient": "{gene} metabolism",     "trait": "{gene}-related nutrition"},
    "sports":       {"category": "{gene}-related fitness",  "trait": "{gene} performance factor"},
    "wellness":     {"metric": "{gene} wellness factor",    "trait": "{gene}-related wellness"},
    "cognitive":    {"domain": "{gene}-related cognition",  "trait": "{gene} cognitive factor"},
    "personality":  {"trait": "{gene} behavioral factor",   "domain": "{gene}-related behavior"},
    "physical":     {"trait": "{gene}-related trait",       "domain": "{gene} physical factor"},
    "methylation":  {"nutrient": "{gene} methylation",      "trait": "{gene} methylation capacity"},
    "detox":        {"nutrient": "{gene} detoxification",   "trait": "{gene} detox capacity"},
    "drug":         {"drug": "{gene}-related drug response"},
    "health":       {},
    "carrier":      {},
    "rare":         {},
    "uncommon":     {},
}


def _category_aware_label(gene: str, category: str, field_name: str) -> str:
    """Produce a semantically appropriate label for a non-primary field.

    Instead of using "{gene} variant" for every field (which produces
    nonsensical results like nutrient="MTHFR variant"), this picks a
    label that makes sense for the field's category context.
    """
    templates = _CATEGORY_FIELD_SUFFIX.get(category, {})
    template = templates.get(field_name)
    if template:
        return template.format(gene=gene)
    return f"{gene} variant"


def _category_extra_fields(category: str, data: Dict[str, Any], conf: float) -> Dict[str, Any]:
    """Return category-specific fields that insight generators expect.

    Each generator accesses specific keys from the mapping data dict.
    This function ensures enrichment-generated mappings contain those keys
    with sensible defaults derived from the available evidence.
    """
    level = _conf_to_level(conf)
    gene = data.get("gene", "")
    condition = data.get("condition", "Unknown variant")

    if category == "drug":
        drug_name = data.get("drug", condition)
        return {
            "drugs": [drug_name],  # rsid-map format: list of drug name strings
        }
    if category == "physical":
        return {
            "result": "Variant detected",
            "confidence": level,
            "description": f"Genetic variant in {gene} linked to {data.get('trait', 'physical trait')}",
        }
    if category == "nutrition":
        nutrient = data.get("nutrient", "nutrient metabolism")
        # Avoid echoing "XXX variant" in recommendations
        rec_subject = data.get("gene", nutrient) if nutrient.endswith("variant") else nutrient
        return {
            "sensitivity": level,
            "metabolism": "variable",
            "recommendations": f"Consult a nutritionist regarding {rec_subject} nutrient metabolism",
        }
    if category == "sports":
        return {
            "advantage": level,
            "recommendations": f"Genetic factor in {data.get('category', 'athletic performance')}",
            "advice": "Consider personalized training approaches based on genetic profile",
        }
    if category == "cognitive":
        return {
            "score": str(round(conf * 100)),
            "percentile": min(99, max(1, int(conf * 80 + 10))),
            "suggestions": f"Variant associated with {data.get('domain', 'cognitive function')}",
        }
    if category == "personality":
        return {
            "tendency": level,
            "confidence": level,
            "insights": f"Genetic association with {data.get('trait', 'behavioral trait')}",
        }
    if category == "wellness":
        return {
            "predisposition": level,
            "score": str(round(conf * 100)),
            "recommendations": f"Monitor and optimize {data.get('metric', 'health metric')}",
        }
    if category == "methylation":
        return {
            "capacity": level,
            "supplements": f"Consider supporting {gene or 'methylation'} pathway",
        }
    if category == "detox":
        return {
            "phase": "Phase I/II",
            "capacity": level,
            "sensitivity": level,
            "recommendations": f"Support {gene or 'detoxification'} function",
        }
    return {}


@dataclass
class SourceEvidence:
    """Evidence collected from a single annotation source."""
    source_name: str
    gene: Optional[str] = None
    conditions: List[str] = field(default_factory=list)
    clinical_significances: List[str] = field(default_factory=list)
    consequence: Optional[str] = None
    pathogenicity_score: Optional[float] = None  # 0.0-1.0
    sift_score: Optional[float] = None
    polyphen_score: Optional[float] = None
    allele_frequency: Optional[float] = None
    review_status: Optional[str] = None
    impact: Optional[str] = None  # HIGH, MODERATE, LOW, MODIFIER
    gene_description: Optional[str] = None  # From ensembl_genes or similar


@dataclass
class CategorySuggestion:
    """A suggested category assignment with confidence and sources."""
    category: str
    confidence: float  # 0.0-1.0
    sources: List[str]
    condition: str
    gene: Optional[str]
    risk_multiplier: float
    clinical_significance: Optional[str]
    data: Dict[str, Any]  # Full mapping data dict


def extract_evidence(annotations: Dict[str, Any]) -> List[SourceEvidence]:
    """Extract standardized evidence from all annotation sources.

    `annotations` is the dict stored in shared_variant_annotations columns
    or the response_data from variant lookup — each key is a source name
    mapping to its JSON payload.
    """
    evidence: List[SourceEvidence] = []

    # ── ClinVar local ───────────────────────────────────────────────
    cv_local = annotations.get("clinvar_local_data") or annotations.get("clinvar_local") or {}
    if isinstance(cv_local, dict) and cv_local.get("found"):
        sigs = cv_local.get("clinical_significances", [])
        conds = cv_local.get("conditions", [])
        genes = cv_local.get("genes", [])
        reviews = cv_local.get("review_statuses", [])
        # Filter noise conditions
        clean_conds = [c for c in conds
                       if c.lower().strip() not in ("not provided", "not specified", "see cases", "")]
        ev = SourceEvidence(
            source_name="clinvar_local",
            gene=genes[0] if genes else None,
            conditions=clean_conds,
            clinical_significances=[s.lower() for s in sigs],
            review_status=reviews[0] if reviews else None,
        )
        # Derive pathogenicity score from significance
        sig_lower = " ".join(s.lower() for s in sigs)
        if any(k in sig_lower for k in ("pathogenic",)):
            ev.pathogenicity_score = 0.9 if "likely" not in sig_lower else 0.75
        elif "risk" in sig_lower or "association" in sig_lower:
            ev.pathogenicity_score = 0.5
        elif any(k in sig_lower for k in ("benign",)):
            ev.pathogenicity_score = 0.1 if "likely" not in sig_lower else 0.15
        else:
            ev.pathogenicity_score = 0.4  # VUS
        evidence.append(ev)

    # ── ClinVar API ─────────────────────────────────────────────────
    cv_api = annotations.get("clinvar_data") or annotations.get("clinvar") or {}
    if isinstance(cv_api, dict) and cv_api.get("found"):
        entries = cv_api.get("entries", [])
        sigs = []
        conds = []
        for entry in entries:
            sigs.extend(entry.get("clinical_significance", []))
            conds.extend(entry.get("conditions", []))
        clean_conds = [c for c in conds
                       if c.lower().strip() not in ("not provided", "not specified", "see cases", "")]
        if sigs or clean_conds:
            ev = SourceEvidence(
                source_name="clinvar_api",
                conditions=clean_conds,
                clinical_significances=[s.lower() for s in sigs],
            )
            sig_lower = " ".join(s.lower() for s in sigs)
            if "pathogenic" in sig_lower:
                ev.pathogenicity_score = 0.85
            elif "benign" in sig_lower:
                ev.pathogenicity_score = 0.1
            evidence.append(ev)

    # ── Ensembl VEP ─────────────────────────────────────────────────
    ensembl = annotations.get("ensembl_data") or annotations.get("ensembl") or {}
    if isinstance(ensembl, dict) and ensembl.get("found"):
        data_list = ensembl.get("data", [])
        entry = data_list[0] if isinstance(data_list, list) and data_list else (
            data_list if isinstance(data_list, dict) else None
        )
        if entry:
            tc = entry.get("transcript_consequences", [])
            gene = tc[0].get("gene_symbol") if tc else None
            consequence = entry.get("most_severe_consequence", "")
            # Get best SIFT/PolyPhen from transcript consequences
            best_sift = None
            best_polyphen = None
            for t in tc:
                s = t.get("sift_score")
                p = t.get("polyphen_score")
                if s is not None and (best_sift is None or s < best_sift):
                    best_sift = s
                if p is not None and (best_polyphen is None or p > best_polyphen):
                    best_polyphen = p
            # Map consequence to impact
            _IMPACT = {
                "transcript_ablation": "HIGH", "splice_acceptor_variant": "HIGH",
                "splice_donor_variant": "HIGH", "stop_gained": "HIGH",
                "frameshift_variant": "HIGH", "stop_lost": "HIGH",
                "start_lost": "HIGH",
                "missense_variant": "MODERATE", "inframe_insertion": "MODERATE",
                "inframe_deletion": "MODERATE", "protein_altering_variant": "MODERATE",
                "splice_region_variant": "MODERATE",
                "synonymous_variant": "LOW", "stop_retained_variant": "LOW",
                "intron_variant": "MODIFIER", "upstream_gene_variant": "MODIFIER",
                "downstream_gene_variant": "MODIFIER",
            }
            impact = _IMPACT.get(consequence, "MODIFIER")
            # Pathogenicity from VEP predictors
            path_score = None
            if best_polyphen is not None:
                path_score = best_polyphen  # PolyPhen: 0=benign, 1=damaging
            elif best_sift is not None:
                path_score = 1.0 - best_sift  # SIFT: 0=damaging, 1=tolerated → invert
            elif impact == "HIGH":
                path_score = 0.8
            elif impact == "MODERATE":
                path_score = 0.5

            ev = SourceEvidence(
                source_name="ensembl_vep",
                gene=gene,
                consequence=consequence,
                sift_score=best_sift,
                polyphen_score=best_polyphen,
                pathogenicity_score=path_score,
                impact=impact,
            )
            evidence.append(ev)

    # ── AlphaMissense ───────────────────────────────────────────────
    am = annotations.get("alpha_missense_data") or annotations.get("alpha_missense") or {}
    if isinstance(am, dict) and am.get("found"):
        am_score = am.get("am_pathogenicity")
        if am_score is not None:
            evidence.append(SourceEvidence(
                source_name="alpha_missense",
                pathogenicity_score=float(am_score),
            ))

    # ── gnomAD ──────────────────────────────────────────────────────
    gnomad = annotations.get("gnomad_data") or annotations.get("gnomad_local") or {}
    if isinstance(gnomad, dict) and gnomad.get("found"):
        gene = gnomad.get("gene")
        af = gnomad.get("af") or gnomad.get("allele_frequency")
        consequence = gnomad.get("consequence")
        impact = gnomad.get("impact")
        cadd = gnomad.get("cadd", {})
        cadd_phred = cadd.get("phred") if isinstance(cadd, dict) else None
        # CADD ≥ 20 → top 1% most deleterious, ≥ 30 → top 0.1%
        path_from_cadd = None
        if cadd_phred is not None:
            if cadd_phred >= 30:
                path_from_cadd = 0.9
            elif cadd_phred >= 20:
                path_from_cadd = 0.7
            elif cadd_phred >= 15:
                path_from_cadd = 0.5
        evidence.append(SourceEvidence(
            source_name="gnomad",
            gene=gene,
            consequence=consequence,
            impact=impact,
            allele_frequency=float(af) if af else None,
            pathogenicity_score=path_from_cadd,
        ))

    # ── SNPedia ─────────────────────────────────────────────────────
    snpedia = annotations.get("snpedia_data") or annotations.get("snpedia") or {}
    if isinstance(snpedia, dict) and snpedia.get("found"):
        evidence.append(SourceEvidence(source_name="snpedia"))

    # ── 1000 Genomes ────────────────────────────────────────────────
    tg = annotations.get("thousand_genomes_data") or annotations.get("thousand_genomes") or {}
    if isinstance(tg, dict) and tg.get("found"):
        af = tg.get("global_af") or tg.get("allele_frequency")
        evidence.append(SourceEvidence(
            source_name="1000genomes",
            allele_frequency=float(af) if af else None,
        ))

    # ── gnomAD gene constraint ──────────────────────────────────────
    gnomad_tx = annotations.get("gnomad_tx_data") or {}
    if isinstance(gnomad_tx, dict) and gnomad_tx.get("found"):
        evidence.append(SourceEvidence(source_name="gnomad_tx"))

    return evidence


def _is_severe(condition: str) -> bool:
    """Return True if condition describes a severe medical condition."""
    lower = condition.lower()
    return any(kw in lower for kw in _SEVERE_EXCLUSION_KW)


def _risk_from_evidence(evidence_list: List[SourceEvidence]) -> float:
    """Compute risk_multiplier from multi-source evidence."""
    path_scores = [e.pathogenicity_score for e in evidence_list
                   if e.pathogenicity_score is not None]
    if not path_scores:
        return 1.1

    avg_path = sum(path_scores) / len(path_scores)
    # Scale: 0.0-0.3 → 1.0, 0.3-0.5 → 1.1, 0.5-0.7 → 1.2, 0.7-0.85 → 1.5, 0.85-1.0 → 2.0
    if avg_path >= 0.85:
        base = 2.0
    elif avg_path >= 0.7:
        base = 1.5
    elif avg_path >= 0.5:
        base = 1.2
    elif avg_path >= 0.3:
        base = 1.1
    else:
        base = 1.0

    # Bonus for multi-source confirmation (up to +0.5)
    n_confirming = len([s for s in path_scores if s >= 0.5])
    bonus = min(n_confirming * 0.15, 0.5)
    return round(min(base + bonus, 3.0), 2)


def _compute_confidence(evidence_list: List[SourceEvidence], category: str) -> float:
    """Compute confidence score (0.0-1.0) based on number & agreement of sources."""
    if not evidence_list:
        return 0.0

    source_count = len(evidence_list)
    # Base confidence from source count: 1 source=0.3, 2=0.5, 3=0.65, 4+=0.75
    base = min(0.15 + source_count * 0.15, 0.75)

    # Bonus from pathogenicity agreement
    path_scores = [e.pathogenicity_score for e in evidence_list
                   if e.pathogenicity_score is not None]
    if len(path_scores) >= 2:
        # All agree on direction?
        all_high = all(s >= 0.5 for s in path_scores)
        all_low = all(s < 0.3 for s in path_scores)
        if all_high or all_low:
            base += 0.15  # Strong agreement bonus

    # Bonus for gene-category match
    genes = [e.gene for e in evidence_list if e.gene]
    if genes:
        gene = genes[0].upper()
        if gene in GENE_CATEGORY_MAP and category in GENE_CATEGORY_MAP[gene]:
            base += 0.1

    return round(min(base, 1.0), 2)


def categorize_variant(
    rsid: str,
    annotations: Dict[str, Any],
    gene_hint: Optional[str] = None,
    condition_hints: Optional[Dict[str, Any]] = None,
) -> List[CategorySuggestion]:
    """Analyze annotation data and return category suggestions.

    Args:
        rsid: Variant rsid.
        annotations: Merged annotation dict from all sources.
        gene_hint: Optional gene symbol from rsid→gene map.
        condition_hints: Optional pre-loaded enrichment data with keys:
            - gene_conditions: Dict[str, List[str]] — gene → disease names
              from clinvar_gene_conditions table
            - gene_descriptions: Dict[str, str] — gene → Ensembl description

    Returns a list of CategorySuggestion objects sorted by confidence,
    one per applicable category.
    """
    evidence_list = extract_evidence(annotations)
    if not evidence_list:
        return []

    # Collect gene from any source
    gene = gene_hint
    for ev in evidence_list:
        if ev.gene and not gene:
            gene = ev.gene
            break

    # Collect all conditions
    all_conditions: List[str] = []
    for ev in evidence_list:
        all_conditions.extend(ev.conditions)
    # Deduplicate preserving order
    seen: Set[str] = set()
    conditions: List[str] = []
    for c in all_conditions:
        cl = c.lower().strip()
        if cl and cl not in seen:
            seen.add(cl)
            conditions.append(c)

    # Collect all clinical significances
    all_sigs: List[str] = []
    for ev in evidence_list:
        all_sigs.extend(ev.clinical_significances)
    sig_set = set(s.lower() for s in all_sigs)

    # Get consequence from Ensembl VEP
    consequence = None
    impact = None
    for ev in evidence_list:
        if ev.consequence:
            consequence = ev.consequence
            impact = ev.impact
            break

    # Source names
    source_names = [ev.source_name for ev in evidence_list]

    suggestions: List[CategorySuggestion] = []

    # ── Determine applicable categories ─────────────────────────────

    applicable_categories: Set[str] = set()

    # 1. Gene-based assignment (highest specificity)
    if gene and gene.upper() in GENE_CATEGORY_MAP:
        applicable_categories.update(GENE_CATEGORY_MAP[gene.upper()])

    # 2. ClinVar significance-based
    has_pathogenic = bool(sig_set & _PATHOGENIC_SIGS)
    has_drug_response = bool(sig_set & _DRUG_SIGS)
    has_benign = bool(sig_set & _BENIGN_SIGS) and not has_pathogenic
    has_risk = bool(sig_set & _RISK_SIGS)

    if has_pathogenic or has_risk:
        applicable_categories.add("health")
    if has_drug_response:
        applicable_categories.add("drug")

    # 3. Condition keyword-based
    for cat, keywords in _CONDITION_CATEGORY_KW.items():
        for cond in conditions:
            cond_lower = cond.lower()
            if any(kw in cond_lower for kw in keywords):
                applicable_categories.add(cat)
                break

    # 4. Rare / uncommon based on allele frequency.
    # Require MODERATE or HIGH VEP impact to exclude MODIFIER intron/intergenic noise.
    # Also require at least one piece of clinical evidence (ClinVar sig OR MODERATE impact)
    # so we don't populate these panels with generic frequency-only entries.
    afs = [ev.allele_frequency for ev in evidence_list if ev.allele_frequency is not None]
    min_af = min(afs) if afs else None
    _MODIFIER_IMPACTS = frozenset(('modifier', 'low'))
    _MODIFIER_CONSEQUENCES = frozenset((
        'intron_variant', 'intergenic_variant', 'upstream_gene_variant',
        'downstream_gene_variant', 'synonymous_variant', '3_prime_utr_variant',
        '5_prime_utr_variant', 'non_coding_transcript_exon_variant',
        'regulatory_region_variant', 'TF_binding_site_variant',
    ))
    _af_impact_ok = (
        impact and impact.upper() not in ('MODIFIER', 'LOW')
        and (not consequence or consequence not in _MODIFIER_CONSEQUENCES)
    )
    # Clinical evidence = ClinVar has any significance OR VEP says MODERATE/HIGH
    _af_has_evidence = bool(sig_set) or (impact and impact.upper() in ('HIGH', 'MODERATE'))
    if min_af is not None and _af_impact_ok and _af_has_evidence:
        if min_af < 0.001:
            applicable_categories.add("rare")
        elif min_af < 0.05:
            applicable_categories.add("uncommon")

    # 5. High-impact variants go to health if not already assigned
    if impact == "HIGH" and "health" not in applicable_categories:
        applicable_categories.add("health")

    # If nothing matched, and we have pathogenicity evidence, default to health.
    # GUARD: only apply for coding variants with MODERATE or HIGH VEP impact AND
    # at least one non-AlphaMissense source. AlphaMissense alone is insufficient
    # because it sometimes assigns high scores to positions that Ensembl VEP
    # classifies as intergenic/MODIFIER (genome build or annotation version
    # mismatch), producing false-positive health flags with no disease name.
    _NON_CODING_IMPACTS = frozenset(('modifier', 'low'))
    _REQUIRES_CLINVAR_SIGS = frozenset(('intergenic_variant', 'upstream_gene_variant',
                                        'downstream_gene_variant', 'non_coding_transcript_exon_variant',
                                        'intron_variant', 'synonymous_variant',
                                        '3_prime_utr_variant', '5_prime_utr_variant'))
    if not applicable_categories:
        path_scores = [ev.pathogenicity_score for ev in evidence_list
                       if ev.pathogenicity_score is not None]
        _impact_ok = impact and impact.lower() not in _NON_CODING_IMPACTS
        _consequence_ok = not consequence or consequence not in _REQUIRES_CLINVAR_SIGS
        _has_clinvar = bool(sig_set)  # any ClinVar significance data
        # Require ClinVar evidence OR HIGH (not just MODERATE) VEP impact.
        # Previously _multi_source (any non-AM source) was accepted — this was too
        # weak because gnomAD is always present, so AM + gnomAD would falsely
        # trigger health categorisation with no disease name.
        _clinvar_or_high_impact = _has_clinvar or impact == "HIGH"
        if path_scores and max(path_scores) >= 0.5 and _impact_ok and _consequence_ok and _clinvar_or_high_impact:
            applicable_categories.add("health")

    # If still nothing, skip
    if not applicable_categories:
        return []

    # Only benign? Skip health but still allow carrier/drug/lifestyle
    if has_benign and not has_pathogenic:
        applicable_categories.discard("health")
        applicable_categories.discard("rare")

    # ── Build suggestions per category ──────────────────────────────
    # Condition label resolution — multi-source fallback chain:
    #   1. ClinVar variant-level conditions (from annotation evidence)
    #   2. clinvar_gene_conditions table (gene↔disease associations)
    #   3. Ensembl gene description (functional description)
    #   4. Fallback: "{gene} variant"
    condition_label = None
    if conditions:
        condition_label = conditions[0]
    if not condition_label and gene and condition_hints:
        # Try gene→condition from clinvar_gene_conditions
        gene_conds = (condition_hints.get("gene_conditions") or {}).get(gene)
        if gene_conds:
            # Pick the shortest non-severe condition for lifestyle; first for health
            condition_label = gene_conds[0]
        # Try Ensembl gene description
        if not condition_label:
            gene_desc = (condition_hints.get("gene_descriptions") or {}).get(gene)
            if gene_desc:
                # Clean up Ensembl description: Title Case, remove "[Source:...]"
                clean_desc = gene_desc.split("[")[0].strip()
                if clean_desc:
                    condition_label = f"{clean_desc.title()} variant"
    if not condition_label:
        condition_label = f"{gene} variant" if gene else "Unknown variant"
    clinical_sig_str = ", ".join(sorted(sig_set)) if sig_set else None

    for category in applicable_categories:
        # Severity filter for lifestyle panels
        if category in _LIFESTYLE_CATEGORIES and _is_severe(condition_label):
            continue

        risk_mult = _risk_from_evidence(evidence_list)
        conf = _compute_confidence(evidence_list, category)

        # Build the data dict for this category
        data: Dict[str, Any] = {
            "condition": condition_label,
            "gene": gene or "",
            "clinical_significance": clinical_sig_str or "",
            "risk_multiplier": risk_mult,
            "source": ", ".join(source_names),
        }

        # Populate category-specific fields
        primary = _PRIMARY_FIELD.get(category, "condition")
        data.setdefault(primary, condition_label)
        for f in ("condition", "trait", "domain", "metric", "nutrient", "category", "drug"):
            if f != primary:
                fallback = _category_aware_label(gene, category, f) if gene else condition_label
                data.setdefault(f, fallback)

        # Add pathogenicity details
        path_scores = [e.pathogenicity_score for e in evidence_list
                       if e.pathogenicity_score is not None]
        if path_scores:
            data["avg_pathogenicity"] = round(sum(path_scores) / len(path_scores), 3)
        if consequence:
            data["consequence"] = consequence
        if impact:
            data["impact"] = impact

        # Add category-specific fields that insight generators require
        extras = _category_extra_fields(category, data, conf)
        for k, v in extras.items():
            data.setdefault(k, v)

        suggestions.append(CategorySuggestion(
            category=category,
            confidence=conf,
            sources=source_names,
            condition=condition_label,
            gene=gene,
            risk_multiplier=risk_mult,
            clinical_significance=clinical_sig_str,
            data=data,
        ))

    # Sort by confidence descending
    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    return suggestions


# ---------------------------------------------------------------------------
# Async helpers for pre-loading condition hints from DB
# ---------------------------------------------------------------------------

async def load_condition_hints(genes: List[str]) -> Dict[str, Any]:
    """Pre-load gene→condition and gene→description mappings from DB.

    Used by callers of categorize_variant() to provide multi-source
    condition naming when ClinVar variant-level conditions are absent.

    Returns:
        Dict with keys:
        - "gene_conditions": Dict[str, List[str]] — gene → disease names
        - "gene_descriptions": Dict[str, str] — gene → Ensembl description
    """
    if not genes:
        return {"gene_conditions": {}, "gene_descriptions": {}}

    from sqlalchemy import select
    from ..db.database import async_session_factory
    from ..db.models import ClinVarGeneCondition, EnsemblGene

    gene_conditions: Dict[str, List[str]] = {}
    gene_descriptions: Dict[str, str] = {}

    _GARBAGE_DISEASES = frozenset({
        "not provided", "not specified", "see cases", "not applicable",
        "none", ".", "-", "",
    })

    async with async_session_factory() as session:
        # 1. ClinVarGeneCondition — gene↔disease associations
        result = await session.execute(
            select(ClinVarGeneCondition.gene, ClinVarGeneCondition.disease_name)
            .where(ClinVarGeneCondition.gene.in_(genes))
        )
        for gene_sym, disease in result.all():
            if not disease or disease.lower().strip() in _GARBAGE_DISEASES:
                continue
            # Prefer shorter, more specific names (sort later)
            gene_conditions.setdefault(gene_sym, []).append(disease.strip())

        # Deduplicate and sort by length (shorter = more specific usually)
        for g in gene_conditions:
            seen: set = set()
            unique = []
            for d in gene_conditions[g]:
                dl = d.lower()
                if dl not in seen:
                    seen.add(dl)
                    unique.append(d)
            gene_conditions[g] = sorted(unique, key=len)

        # 2. EnsemblGene — functional gene descriptions
        result = await session.execute(
            select(EnsemblGene.gene_symbol, EnsemblGene.description)
            .where(EnsemblGene.gene_symbol.in_(genes))
            .distinct()
        )
        for gene_sym, desc in result.all():
            if desc and gene_sym not in gene_descriptions:
                gene_descriptions[gene_sym] = desc

    return {
        "gene_conditions": gene_conditions,
        "gene_descriptions": gene_descriptions,
    }


async def enrich_generic_mappings(
    dry_run: bool = False,
    categories: Optional[List[str]] = None,
    revise_all: bool = False,
) -> Dict[str, Any]:
    """Update existing variant_mappings with proper conditions from all
    available sources.

    Multi-source resolution order:
    1. ClinVar variant-level conditions (clinvar_variants table)
    2. ClinVar gene-level conditions (clinvar_gene_conditions table)
    3. Ensembl gene descriptions (ensembl_genes table)

    By default only updates rows with generic names (ending in ' variant').
    When ``revise_all=True``, re-evaluates **every** active mapping and
    upgrades condition text when a higher-priority source provides a better
    name (ClinVar variant > ClinVar gene > Ensembl gene > current).
    Named conditions are never downgraded to generic ones.

    Args:
        dry_run: If True, return what would be updated without writing.
        categories: Optional list of categories to limit the update to.
        revise_all: If True, check ALL active mappings (not just generic).

    Returns:
        Dict with stats: total_checked, total_updated, by_category, by_source.
    """
    from sqlalchemy import select, update, text
    from ..db.database import async_session_factory
    from ..db.models import VariantMapping, ClinVarVariant, ClinVarGeneCondition, EnsemblGene

    stats = {
        "total_checked": 0,
        "total_updated": 0,
        "by_category": {},
        "by_source": {"clinvar_variant": 0, "clinvar_gene": 0, "ensembl_gene": 0},
        "examples": [],
    }

    _GARBAGE = frozenset({
        "not provided", "not specified", "see cases", "not applicable",
        "none", ".", "-", "", ".|.",
    })

    def _is_generic(condition: str) -> bool:
        return condition.endswith(" variant") or condition == "Unknown variant"

    async with async_session_factory() as session:
        # Load active mappings
        q = select(VariantMapping).where(
            VariantMapping.is_active == True,
            VariantMapping.map_type == "rsid",
        )
        if categories:
            q = q.where(VariantMapping.category.in_(categories))

        result = await session.execute(q)
        mappings = result.scalars().all()

        if revise_all:
            # Check every mapping with a data dict
            target_mappings = [m for m in mappings if isinstance(m.data, dict)]
        else:
            # Only generic-named mappings
            target_mappings = [
                m for m in mappings
                if isinstance(m.data, dict) and _is_generic(m.data.get("condition", ""))
            ]
        stats["total_checked"] = len(target_mappings)

        if not target_mappings:
            return stats

        # Collect all rsids and genes
        rsids = {m.key for m in target_mappings}
        genes = {m.data.get("gene", "") for m in target_mappings if m.data.get("gene")}

        # Helper: batch IN queries to avoid exceeding PG bind param limit
        BATCH = 30000

        # Source 1: ClinVar variant-level conditions
        cv_map: Dict[str, str] = {}
        if rsids:
            rsid_list = list(rsids)
            for i in range(0, len(rsid_list), BATCH):
                batch = rsid_list[i:i + BATCH]
                result = await session.execute(
                    select(ClinVarVariant.rsid, ClinVarVariant.conditions)
                    .where(ClinVarVariant.rsid.in_(batch))
                    .where(ClinVarVariant.conditions.isnot(None))
                )
                for rsid, raw_conds in result.all():
                    if rsid in cv_map:
                        continue
                    if raw_conds:
                        # Clean pipe-separated conditions
                        parts = raw_conds.replace(";", "|").split("|")
                        for part in parts:
                            cleaned = part.strip()
                            if cleaned and cleaned.lower() not in _GARBAGE:
                                cv_map[rsid] = cleaned
                                break

        # Source 2: ClinVar gene-level conditions
        gene_cond_map: Dict[str, str] = {}
        if genes:
            gene_list = list(genes)
            for i in range(0, len(gene_list), BATCH):
                batch = gene_list[i:i + BATCH]
                result = await session.execute(
                    select(ClinVarGeneCondition.gene, ClinVarGeneCondition.disease_name)
                    .where(ClinVarGeneCondition.gene.in_(batch))
                )
                for gene_sym, disease in result.all():
                    if gene_sym in gene_cond_map:
                        continue
                    if disease and disease.lower().strip() not in _GARBAGE:
                        gene_cond_map[gene_sym] = disease.strip()

        # Source 3: Ensembl gene descriptions
        gene_desc_map: Dict[str, str] = {}
        if genes:
            gene_list = list(genes)
            for i in range(0, len(gene_list), BATCH):
                batch = gene_list[i:i + BATCH]
                result = await session.execute(
                    select(EnsemblGene.gene_symbol, EnsemblGene.description)
                    .where(EnsemblGene.gene_symbol.in_(batch))
                    .distinct()
                )
                for gene_sym, desc in result.all():
                    if desc and gene_sym not in gene_desc_map:
                        clean = desc.split("[")[0].strip()
                        if clean:
                            gene_desc_map[gene_sym] = f"{clean.title()} variant"

        # Apply enrichment
        for mapping in target_mappings:
            rsid = mapping.key
            gene = mapping.data.get("gene", "")
            old_condition = mapping.data.get("condition", "")
            new_condition = None
            source_used = None

            # Priority chain
            if rsid in cv_map:
                new_condition = cv_map[rsid]
                source_used = "clinvar_variant"
            elif gene in gene_cond_map:
                new_condition = gene_cond_map[gene]
                source_used = "clinvar_gene"
            elif gene in gene_desc_map:
                new_condition = gene_desc_map[gene]
                source_used = "ensembl_gene"

            if new_condition and new_condition != old_condition:
                # In revise_all mode: never downgrade a named condition to
                # a generic one (e.g. ClinVar disease → Ensembl gene desc).
                if revise_all and not _is_generic(old_condition) and _is_generic(new_condition):
                    continue
                if not dry_run:
                    # Merge: update condition in data dict, preserve everything else
                    updated_data = {**mapping.data, "condition": new_condition}
                    # Also update the primary dedup field if it had the old generic name
                    primary = _PRIMARY_FIELD.get(mapping.category, "condition")
                    if updated_data.get(primary) == old_condition:
                        updated_data[primary] = new_condition
                    mapping.data = updated_data

                stats["total_updated"] += 1
                stats["by_category"][mapping.category] = stats["by_category"].get(mapping.category, 0) + 1
                stats["by_source"][source_used] += 1

                if len(stats["examples"]) < 20:
                    stats["examples"].append({
                        "rsid": rsid, "gene": gene, "category": mapping.category,
                        "old": old_condition, "new": new_condition, "source": source_used,
                    })

        if not dry_run:
            await session.commit()

    return stats
