"""Indel allele-carriage verification in the rare mutations generator.

Characterization of the live 2026-09-16 defect: the production app reported the
account owner as hemizygous-affected for Rett syndrome, Duchenne muscular
dystrophy and six other severe X-linked conditions. Every one of those findings
had a consumer-array indel genotype (II/DD) on chromosome X.

rare_mutations.py gated its ClinVar allele-carriage check on
``not is_indel_genotype(user_gt)``, so for II/DD the check never ran and nothing
established that the user carried the specific reported indel. The X-linked
branch then promoted "not heterozygous" into "hemizygous affected".
"""
import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers — mirror test_rare_mutations_sex_filter.py conventions
# ---------------------------------------------------------------------------

def _make_variant(rsid: str, chromosome: str, genotype: str):
    v = SimpleNamespace()
    v.rsid = rsid
    v.chromosome = chromosome
    v.genotype = genotype
    return v


def _make_annotation(
    rsid: str,
    gene: str = "MECP2",
    clin_sigs: list = None,
    cv_ref: str = None,
    cv_alt: str = None,
    conditions: list = None,
    review_statuses: list = None,
    ensembl_allele_string: str = None,
    clinvar_local_found: bool = True,
    clinvar_api_found: bool = False,
):
    clin_sigs = clin_sigs or ["Pathogenic"]
    conditions = conditions or ["Rett syndrome"]
    if review_statuses is None:
        review_statuses = ["criteria provided, multiple submitters, no conflicts"]

    cv_local = {
        "found": clinvar_local_found,
        "clinical_significances": clin_sigs,
        "conditions": conditions,
        "genes": [gene],
        "review_statuses": review_statuses,
    }
    if cv_alt is not None:
        cv_local["alt_allele"] = cv_alt
    if cv_ref is not None:
        cv_local["ref_allele"] = cv_ref

    ensembl = {}
    if ensembl_allele_string:
        ensembl = {"data": [{"allele_string": ensembl_allele_string}]}

    ann = MagicMock()
    ann.rsid = rsid
    ann.annotation_data = {
        "annotations": {
            "clinvar_local": cv_local,
            "clinvar": {
                "found": clinvar_api_found,
                "clinical_significances": clin_sigs,
                "conditions": conditions,
            },
            "ensembl": ensembl,
        }
    }
    return ann


def _make_profile(rsid, genotype, gene, is_het, freq, annotation_result, chromosome):
    from backend.services.insight_generators.base import VariantProfile
    return VariantProfile(
        rsid=rsid,
        genotype=genotype,
        effective_ref=None,
        gene=gene,
        consequence="frameshift_variant",
        impact="HIGH",
        chromosome=chromosome,
        population_frequency=freq,
        clinical_significance="pathogenic",
        is_benign=False,
        is_hom_ref=False,
        is_het=is_het,
        is_no_call=False,
        composite_score=0.95,
        pathogenicity_score=None,
        annotation_result=annotation_result,
        variant=None,
    )


def _make_ctx(variants, profiles=None, annotation_results=None, inferred_sex="male"):
    from backend.services.insight_generators.base import GeneratorContext

    session = AsyncMock()
    added = []
    session.add = MagicMock(side_effect=lambda obj: added.append(obj))

    ctx = GeneratorContext(
        analysis_id=99,
        variants=variants,
        annotation_results=annotation_results or {},
        session=session,
        rsid_gene_map={},
        registry={},
        variant_profiles=profiles or {},
        inferred_sex=inferred_sex,
    )
    ctx._added = added
    return ctx


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _generate(variant, annotation, genotype, freq=1.2e-5, is_het=False,
              inferred_sex="male", chromosome="X"):
    from backend.services.insight_generators.rare_mutations import generate_rare_mutations
    profile = _make_profile(
        variant.rsid, genotype, "MECP2", is_het, freq, annotation, chromosome
    )
    ctx = _make_ctx(
        [variant],
        profiles={variant.rsid: profile},
        annotation_results={variant.rsid: annotation},
        inferred_sex=inferred_sex,
    )
    _run(generate_rare_mutations(ctx))
    return ctx._added


# ---------------------------------------------------------------------------
# The live defect
# ---------------------------------------------------------------------------

# Real values observed in production on 2026-09-16.
# rs61749708 = NM_001110792.2(MECP2):c.802dup (p.Arg202fs), gnomAD AF 1.2e-5.
# The variant dialog reported "Alleles (Ref/Alt): CC/C, CCC" — a multi-allelic
# site — against a user genotype of "II".
LIVE_RSID = "rs61749708"
LIVE_REF = "CC"
LIVE_ALT_MULTI = "C,CCC"


class TestLiveMecp2FalsePositive:
    def test_multiallelic_indel_is_not_reported_as_a_clinical_finding(self):
        """The exact production finding must not be emitted.

        ClinVar classified the CCC duplication as pathogenic, but the site also
        carries a C deletion allele. A genotype of "II" cannot be attributed to
        one specific alt at a multi-allelic site, so no clinical claim is
        supportable.
        """
        variant = _make_variant(LIVE_RSID, "X", "II")
        annotation = _make_annotation(
            LIVE_RSID, cv_ref=LIVE_REF, cv_alt=LIVE_ALT_MULTI,
            clin_sigs=["Pathogenic"], conditions=["Rett syndrome"],
        )
        assert _generate(variant, annotation, "II") == []


class TestIndelCarriageVerification:
    def test_user_not_carrying_the_pathogenic_allele_is_dropped(self):
        """Deletion variant (ref longer than alt): I is the reference allele,
        so "II" means the user carries no copy of the pathogenic allele."""
        variant = _make_variant("rs111", "X", "II")
        annotation = _make_annotation("rs111", cv_ref="CTT", cv_alt="C")
        assert _generate(variant, annotation, "II") == []

    def test_user_carrying_the_pathogenic_allele_is_still_reported(self):
        """Insertion variant (ref shorter than alt): I is the alternate allele,
        so "II" does carry it. Guards against over-correction."""
        variant = _make_variant("rs222", "X", "II")
        annotation = _make_annotation("rs222", cv_ref="C", cv_alt="CTT")
        assert len(_generate(variant, annotation, "II")) == 1

    def test_equal_length_alleles_are_unresolvable_and_dropped(self):
        variant = _make_variant("rs333", "X", "DD")
        annotation = _make_annotation("rs333", cv_ref="CT", cv_alt="GA")
        assert _generate(variant, annotation, "DD") == []

    def test_missing_clinvar_alt_allele_is_dropped_without_raising(self):
        variant = _make_variant("rs444", "X", "II")
        annotation = _make_annotation("rs444", cv_ref="C", cv_alt=None)
        assert _generate(variant, annotation, "II") == []

    def test_missing_clinvar_ref_allele_is_dropped_without_raising(self):
        variant = _make_variant("rs555", "X", "DD")
        annotation = _make_annotation("rs555", cv_ref=None, cv_alt="CTT")
        assert _generate(variant, annotation, "DD") == []

    def test_heterozygous_indel_code_is_not_claimed_as_homozygous(self):
        """DI/ID carries one copy. On an X-linked locus in a male this is a
        genotyping artifact and must not survive as an affected claim."""
        variant = _make_variant("rs666", "X", "DI")
        annotation = _make_annotation("rs666", cv_ref="C", cv_alt="CTT")
        assert _generate(variant, annotation, "DI", is_het=True) == []


class TestClinVarIsTheAlleleAuthority:
    def test_clinvar_alleles_win_over_ensembl_allele_string(self):
        """get_annotation_allele_parts() prefers Ensembl's allele_string, but
        the claim being adjudicated is a ClinVar claim. Ensembl here would
        resolve direction the opposite way and wrongly keep the finding."""
        variant = _make_variant("rs777", "X", "II")
        annotation = _make_annotation(
            "rs777", cv_ref="CTT", cv_alt="C",          # deletion → II = ref
            ensembl_allele_string="C/CTT",               # insertion → II = alt
        )
        assert _generate(variant, annotation, "II") == []


class TestClinVarApiOnlyFindings:
    def test_clinvar_api_only_match_is_not_emitted_as_a_clinical_claim(self):
        """Carriage is verified against clinvar_local only. A clinvar_api-only
        match would otherwise reach the X-linked branch unverified."""
        variant = _make_variant("rs888", "X", "II")
        annotation = _make_annotation(
            "rs888", clinvar_local_found=False, clinvar_api_found=True,
            cv_ref="C", cv_alt="CTT",
        )
        assert _generate(variant, annotation, "II") == []


class TestSnvPathUnchanged:
    def test_snv_carrying_the_alt_allele_is_still_reported(self):
        variant = _make_variant("rs999", "X", "TT")
        annotation = _make_annotation("rs999", cv_ref="C", cv_alt="T")
        assert len(_generate(variant, annotation, "TT")) == 1

    def test_snv_not_carrying_the_alt_allele_is_dropped(self):
        variant = _make_variant("rs1010", "X", "CC")
        annotation = _make_annotation("rs1010", cv_ref="C", cv_alt="T")
        assert _generate(variant, annotation, "CC") == []
