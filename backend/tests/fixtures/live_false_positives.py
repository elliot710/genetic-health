"""The eight severe findings observed live on the owner's dashboard, 2026-09-16.

Each was displayed as "Clinically Significant" with "Genetic counseling
recommended" for a living adult male. Allele and review data below are the real
ClinVar records for these rsids, read from the local ClinVar cache — not
invented — so this fixture reproduces the actual production inputs.

Every one shares the same shape: a consumer-array indel code (I/D) on
chromosome X in a male, which the pipeline read as hemizygous-affected.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

# (condition, gene, rsid, genotype, clinvar_ref, clinvar_alt, review_status)
LIVE_FALSE_POSITIVES = [
    ("Rett syndrome", "MECP2", "rs61749708", "II", "T", "TC",
     "criteria provided, single submitter"),
    ("Duchenne muscular dystrophy", "DMD", "rs398124078", "II", "G", "GGA",
     "criteria provided, multiple submitters, no conflicts"),
    ("Severe X-linked myotubular myopathy", "MTM1", "rs587783865", "II", "T", "TA",
     "criteria provided, multiple submitters, no conflicts"),
    ("Adrenoleukodystrophy", "ABCD1", "rs713993050", "II", "TC", "T",
     "criteria provided, multiple submitters, no conflicts"),
    ("Renpenning syndrome", "PQBP1", "rs606231193", "DD", "CAG", "C",
     "criteria provided, multiple submitters, no conflicts"),
    ("Orofaciodigital syndrome I", "OFD1", "rs312262845", "DD", "C", "CA",
     "criteria provided, multiple submitters, no conflicts"),
    ("Developmental and epileptic encephalopathy 1", "ARX", "rs797045292", "DD", "AG", "A",
     "criteria provided, multiple submitters, no conflicts"),
    ("Thrombophilia X-linked, factor 8 defect", "F8", "rs387906460", "II", "C", "CT",
     "criteria provided, multiple submitters, no conflicts"),
]


def build_annotation(rsid, gene, condition, ref, alt, review_status):
    annotation = MagicMock()
    annotation.rsid = rsid
    annotation.annotation_data = {
        "annotations": {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": [condition],
                "genes": [gene],
                "ref_allele": ref,
                "alt_allele": alt,
                "review_statuses": [review_status],
            },
            "ensembl": {},
        }
    }
    return annotation


def build_context(condition, gene, rsid, genotype, ref, alt, review_status):
    """A male user carrying the live genotype at this X-linked site."""
    from backend.services.insight_generators.base import GeneratorContext, VariantProfile

    annotation = build_annotation(rsid, gene, condition, ref, alt, review_status)
    variant = SimpleNamespace(rsid=rsid, chromosome="X", genotype=genotype)
    profile = VariantProfile(
        rsid=rsid, genotype=genotype, effective_ref=ref, gene=gene,
        consequence="frameshift_variant", impact="HIGH", chromosome="X",
        population_frequency=1.2e-5, clinical_significance="pathogenic",
        is_benign=False, is_hom_ref=False, is_het=False, is_no_call=False,
        composite_score=0.95, pathogenicity_score=None,
        annotation_result=annotation, variant=None,
    )
    emitted = []
    session = MagicMock()
    session.add = MagicMock(side_effect=lambda obj: emitted.append(obj))
    ctx = GeneratorContext(
        analysis_id=1, variants=[variant], annotation_results={rsid: annotation},
        session=session, rsid_gene_map={}, registry={},
        variant_profiles={rsid: profile}, inferred_sex="male",
    )
    return ctx, emitted


def build_carrier_context(condition, gene, rsid, genotype, ref, alt, review_status):
    """Same live finding, routed through the carrier generator.

    The carrier panel reports the identical variant, so it must hold an
    'affected' claim to the same bar as rare mutations.
    """
    from backend.services.insight_generators.base import GeneratorContext

    annotation = build_annotation(rsid, gene, condition, ref, alt, review_status)
    annotation.annotation_data["annotations"]["clinvar_local"]["gene_conditions"] = [
        {"gene": gene, "disease": condition}
    ]
    annotation.annotation_data["annotations"]["ensembl"] = {
        "data": [{"allele_string": f"{ref}/{alt}"}]
    }
    variant = MagicMock()
    variant.rsid, variant.genotype, variant.chromosome = rsid, genotype, "X"
    variant.marker = MagicMock()
    variant.marker.ref_allele, variant.marker.alt_alleles = ref, alt

    emitted = []
    session = MagicMock()
    session.add = MagicMock(side_effect=lambda obj: emitted.append(obj))
    ctx = MagicMock(spec=GeneratorContext)
    ctx.analysis_id, ctx.variants = 1, [variant]
    ctx.annotation_results = {rsid: annotation}
    ctx.rsid_gene_map, ctx.variant_profiles = {}, {}
    ctx.inferred_sex, ctx.session = "male", session
    ctx.get_maps = MagicMock(return_value=({}, {}))
    return ctx, emitted
