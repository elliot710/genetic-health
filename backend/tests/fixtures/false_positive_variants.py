"""Curated false-positive variant class for the rarity regression lock (U12).

Common alleles carrying a ClinVar 'Pathogenic' label. None of these should
produce a clinical (health) finding — a Mendelian pathogenic allele is rare, so
carrying a common allele means carrying the normal/major allele. rs397518480 is
the reported seed (synonymous, ~79% AF, X-linked parkinsonism-spasticity).
"""
from unittest.mock import MagicMock

FALSE_POSITIVE_SPECS = [
    {"rsid": "rs397518480", "af": 0.79, "desc": "synonymous common allele (seed)"},
    {"rsid": "rs_common_missense", "af": 0.60, "desc": "common missense allele"},
    {"rsid": "rs_just_over_hard_cap", "af": 0.11, "desc": "allele just over the hard cap"},
]

TRUE_POSITIVE_SPEC = {"rsid": "rs_rare_pathogenic", "af": 0.0003, "desc": "genuine rare pathogenic"}


def build_health_ctx(rsid: str, af: float):
    """A GeneratorContext-shaped mock carrying one hom-alt ClinVar-pathogenic
    variant at the given population frequency, wired for generate_health_risks."""
    variant = MagicMock()
    variant.rsid = rsid
    variant.genotype = "T/T"
    variant.chromosome = "1"
    variant.marker = MagicMock()

    annotation = MagicMock()
    annotation.annotation_data = {"annotations": {
        "clinvar_local": {
            "found": True,
            "clinical_significances": ["Pathogenic"],
            "ref_allele": "C", "alt_allele": "T",
        },
    }}

    profile = MagicMock()
    profile.population_frequency = af

    ctx = MagicMock()
    ctx.variants = [variant]
    ctx.annotation_results = {rsid: annotation}
    ctx.variant_profiles = {rsid: profile}
    ctx.inferred_sex = "male"
    ctx.analysis_id = 1
    ctx.rsid_gene_map = {}
    ctx.session = MagicMock()
    ctx.session.add = MagicMock()
    ctx.get_maps = MagicMock(return_value=(
        {rsid: {
            "condition": "Test clinical condition", "risk_multiplier": 2.3,
            "gene": "GENE", "clinical_significance": "pathogenic",
        }},
        {},
    ))
    return ctx
