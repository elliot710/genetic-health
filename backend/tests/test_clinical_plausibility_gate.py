"""Biological plausibility gating for rare-mutation clinical claims.

Defence in depth over allele-carriage verification. The gate tests only
condition severity and ClinVar review status, never carriage, so a regression
in carriage verification cannot also disable it.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.services.insight_generators.base import (
    is_severe_early_onset, has_strong_review, requires_corroboration,
    is_corroborated,
)

STRONG = ["criteria provided, multiple submitters, no conflicts"]
EXPERT = ["reviewed by expert panel"]
WEAK = ["criteria provided, single submitter"]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestSeverityClassification:
    def test_rett_syndrome_is_severe(self):
        assert is_severe_early_onset("Rett syndrome") is True

    def test_matching_is_case_and_punctuation_tolerant(self):
        assert is_severe_early_onset("RETT SYNDROME, congenital variant") is True

    def test_duchenne_is_severe(self):
        assert is_severe_early_onset("Duchenne muscular dystrophy") is True

    def test_ordinary_adult_condition_is_not_severe(self):
        assert is_severe_early_onset("Hereditary breast and ovarian cancer") is False

    def test_empty_condition_is_not_severe(self):
        assert is_severe_early_onset("") is False


class TestReviewStrength:
    def test_multiple_submitters_is_strong(self):
        assert has_strong_review(STRONG) is True

    def test_expert_panel_is_strong(self):
        assert has_strong_review(EXPERT) is True

    def test_single_submitter_is_not_strong(self):
        assert has_strong_review(WEAK) is False

    def test_empty_review_statuses_are_treated_as_weak(self):
        assert has_strong_review([]) is False

    def test_missing_review_statuses_are_treated_as_weak(self):
        assert has_strong_review(None) is False


class TestCorroborationTriggers:
    def test_curated_severe_condition_triggers(self):
        assert requires_corroboration("Rett syndrome", is_hemizygous_claim=False) is True

    def test_hemizygous_claim_triggers_even_when_condition_is_unlisted(self):
        """An unlisted severe condition must not sail through the way MECP2
        did. The hemizygous shape is its own independent trigger."""
        assert requires_corroboration("Some newly described syndrome",
                                      is_hemizygous_claim=True) is True

    def test_ordinary_autosomal_finding_does_not_trigger(self):
        assert requires_corroboration("Hereditary breast and ovarian cancer",
                                      is_hemizygous_claim=False) is False


# ---------------------------------------------------------------------------
# Gate behaviour inside the generator
# ---------------------------------------------------------------------------

def _make_variant(rsid, chromosome, genotype):
    v = SimpleNamespace()
    v.rsid, v.chromosome, v.genotype = rsid, chromosome, genotype
    return v


def _make_annotation(rsid, gene, condition, review_statuses, cv_ref="C", cv_alt="T"):
    ann = MagicMock()
    ann.rsid = rsid
    ann.annotation_data = {
        "annotations": {
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "conditions": [condition],
                "genes": [gene],
                "ref_allele": cv_ref,
                "alt_allele": cv_alt,
                "review_statuses": review_statuses,
            },
            "ensembl": {},
        }
    }
    return ann


def _make_profile(rsid, genotype, gene, annotation, chromosome):
    from backend.services.insight_generators.base import VariantProfile
    return VariantProfile(
        rsid=rsid, genotype=genotype, effective_ref=None, gene=gene,
        consequence="frameshift_variant", impact="HIGH", chromosome=chromosome,
        population_frequency=1.2e-5, clinical_significance="pathogenic",
        is_benign=False, is_hom_ref=False, is_het=False, is_no_call=False,
        composite_score=0.95, pathogenicity_score=None,
        annotation_result=annotation, variant=None,
    )


def _emit(rsid, gene, condition, review_statuses, chromosome="X",
          genotype="TT", inferred_sex="male"):
    from backend.services.insight_generators.base import GeneratorContext
    from backend.services.insight_generators.rare_mutations import generate_rare_mutations

    variant = _make_variant(rsid, chromosome, genotype)
    annotation = _make_annotation(rsid, gene, condition, review_statuses)
    profile = _make_profile(rsid, genotype, gene, annotation, chromosome)

    session = AsyncMock()
    added = []
    session.add = MagicMock(side_effect=lambda obj: added.append(obj))
    ctx = GeneratorContext(
        analysis_id=99, variants=[variant], annotation_results={rsid: annotation},
        session=session, rsid_gene_map={}, registry={},
        variant_profiles={rsid: profile}, inferred_sex=inferred_sex,
    )
    asyncio.new_event_loop().run_until_complete(generate_rare_mutations(ctx))
    return added


class TestGateInGenerator:
    def test_severe_condition_with_expert_panel_stays_clinically_significant(self):
        added = _emit("rs1", "MECP2", "Rett syndrome", EXPERT)
        assert added[0].clinical_significance == "pathogenic"

    def test_severe_condition_with_single_submitter_is_downgraded(self):
        added = _emit("rs2", "MECP2", "Rett syndrome", WEAK)
        assert added[0].clinical_significance == "uncertain"

    def test_downgrade_clears_the_urgent_clinical_flags(self):
        added = _emit("rs3", "DMD", "Duchenne muscular dystrophy", WEAK)
        assert added[0].genetic_counseling_urgent is False

    def test_downgrade_clears_specialist_referral(self):
        added = _emit("rs4", "DMD", "Duchenne muscular dystrophy", WEAK)
        assert added[0].specialist_referral is False

    def test_unlisted_condition_on_hemizygous_claim_is_still_gated(self):
        """The curated list is not the only gate — an unlisted severe condition
        presented as a hemizygous male claim is corroboration-gated too."""
        added = _emit("rs5", "ATP6AP2", "Some newly described syndrome", WEAK)
        assert added[0].clinical_significance == "uncertain"

    def test_ordinary_autosomal_finding_is_untouched_by_the_gate(self):
        added = _emit("rs6", "BRCA2", "Hereditary breast and ovarian cancer",
                      WEAK, chromosome="13", inferred_sex="female")
        assert added[0].clinical_significance == "pathogenic"


class TestGateIsIndependentOfCarriageVerification:
    def test_gate_still_fires_when_carriage_verification_is_stubbed_out(self, monkeypatch):
        """The whole point of the gate is to survive a carriage regression.
        Force carriage to always pass, then confirm the downgrade still happens."""
        import backend.services.insight_generators.rare_mutations as rm
        monkeypatch.setattr(rm, "_carries_clinvar_indel", lambda *a, **k: True)

        added = _emit("rs7", "MECP2", "Rett syndrome", WEAK, genotype="II")
        assert added[0].clinical_significance == "uncertain"


class TestCorroborationMustBeAboutCarriage:
    """Review status corroborates the VARIANT; the doubt is about the PERSON."""

    def test_strong_review_cannot_rescue_a_severe_claim_from_an_indel_code(self):
        assert is_corroborated("Duchenne muscular dystrophy", STRONG,
                               is_low_confidence_call=True) is False

    def test_strong_review_still_corroborates_a_severe_claim_from_a_clean_call(self):
        assert is_corroborated("Duchenne muscular dystrophy", STRONG,
                               is_low_confidence_call=False) is True

    def test_an_indel_code_is_fine_for_a_condition_an_adult_can_have(self):
        assert is_corroborated("Thrombophilia X-linked, factor 8 defect", STRONG,
                               is_low_confidence_call=True) is True

    def test_weak_review_is_still_uncorroborated_on_a_clean_call(self):
        assert is_corroborated("Duchenne muscular dystrophy", WEAK,
                               is_low_confidence_call=False) is False
