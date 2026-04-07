"""Tests for rare_mutations sex-based X-linked filtering."""
import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_variant(rsid: str, chromosome: str, genotype: str):
    v = SimpleNamespace()
    v.rsid = rsid
    v.chromosome = chromosome
    v.genotype = genotype
    return v


def _make_annotation(
    rsid: str,
    chromosome: str = "X",
    gene: str = "MECP2",
    clin_sigs: list = None,
    cv_alt: str = "T",
    conditions: list = None,
    review_statuses: list = None,
):
    """Build a minimal AnnotationResult-like object that mimics the real structure."""
    clin_sigs = clin_sigs or ["Likely_pathogenic"]
    conditions = conditions or ["Rett syndrome"]
    if review_statuses is None:
        review_statuses = ["criteria provided, multiple submitters, no conflicts"]

    cv_local = {
        "found": True,
        "clinical_significances": clin_sigs,
        "conditions": conditions,
        "genes": [gene],
        "alt_allele": cv_alt,
        "review_statuses": review_statuses,
    }

    ann = MagicMock()
    ann.rsid = rsid
    ann.annotation_data = {
        "annotations": {
            "clinvar_local": cv_local,
            "ensembl": {},
        }
    }
    return ann


def _make_profile(
    rsid: str,
    genotype: str,
    gene: str,
    is_het: bool,
    is_hom_ref: bool = False,
    is_no_call: bool = False,
    freq: float = None,
    annotation_result=None,
    variant=None,
    chromosome: str = None,
):
    from backend.services.insight_generators.base import VariantProfile
    return VariantProfile(
        rsid=rsid,
        genotype=genotype,
        effective_ref=None,
        gene=gene,
        consequence="missense_variant",
        impact="MODERATE",
        chromosome=chromosome,
        population_frequency=freq,
        clinical_significance="likely_pathogenic",
        is_benign=False,
        is_hom_ref=is_hom_ref,
        is_het=is_het,
        is_no_call=is_no_call,
        composite_score=0.8,
        pathogenicity_score=None,
        annotation_result=annotation_result,
        variant=variant,
    )


def _make_ctx(
    variants,
    profiles: dict = None,
    annotation_results: dict = None,
    inferred_sex: str = None,
):
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


# ---------------------------------------------------------------------------
# Fixtures: shared variant data
# ---------------------------------------------------------------------------

MECP2_RSID = "rs267608531"
MECP2_HET_GENOTYPE = "DI"   # heterozygous del/ins
MECP2_HOM_GENOTYPE = "DD"   # homozygous deletion


def _mecp2_annotation():
    return _make_annotation(
        rsid=MECP2_RSID,
        chromosome="X",
        gene="MECP2",
        clin_sigs=["Likely_pathogenic"],
        cv_alt="I",          # indel — allele verification skipped
        conditions=["Rett syndrome"],
    )


# ---------------------------------------------------------------------------
# Core sex filter behaviour
# ---------------------------------------------------------------------------

class TestXLinkedConditionNameNotRequired:
    """Variants on chromosome X must trigger the sex filter even when condition
    names like 'Rett syndrome' don't contain the phrase 'x-linked'."""

    def _run_generate(self, variant, profile, annotation, inferred_sex):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        ctx = _make_ctx(
            variants=[variant],
            profiles={MECP2_RSID: profile},
            annotation_results={MECP2_RSID: annotation},
            inferred_sex=inferred_sex,
        )
        _run(generate_rare_mutations(ctx))
        return ctx._added

    def test_het_female_x_variant_filtered_without_xlinked_in_name(self):
        variant = _make_variant(MECP2_RSID, "X", MECP2_HET_GENOTYPE)
        annotation = _mecp2_annotation()
        profile = _make_profile(
            MECP2_RSID, MECP2_HET_GENOTYPE, "MECP2",
            is_het=True, annotation_result=annotation, variant=variant,
        )
        added = self._run_generate(variant, profile, annotation, "female")
        assert len(added) == 0, "Het female should be filtered even when condition isn't named 'x-linked'"

    def test_het_male_x_variant_not_filtered(self):
        variant = _make_variant(MECP2_RSID, "X", MECP2_HOM_GENOTYPE)
        annotation = _mecp2_annotation()
        profile = _make_profile(
            MECP2_RSID, MECP2_HOM_GENOTYPE, "MECP2",
            is_het=False, annotation_result=annotation, variant=variant,
        )
        added = self._run_generate(variant, profile, annotation, "male")
        assert len(added) == 1, "Male with X-linked variant should appear in rare mutations"

    def test_het_female_chromosome_x_filtered(self):
        variant = _make_variant(MECP2_RSID, "X", MECP2_HET_GENOTYPE)
        annotation = _mecp2_annotation()
        profile = _make_profile(
            MECP2_RSID, MECP2_HET_GENOTYPE, "MECP2",
            is_het=True, annotation_result=annotation, variant=variant,
        )
        added = self._run_generate(variant, profile, annotation, "female")
        assert len(added) == 0

    def test_hom_female_chromosome_x_not_filtered(self):
        """Homozygous female with X-linked pathogenic variant IS affected — must appear."""
        variant = _make_variant(MECP2_RSID, "X", MECP2_HOM_GENOTYPE)
        annotation = _mecp2_annotation()
        profile = _make_profile(
            MECP2_RSID, MECP2_HOM_GENOTYPE, "MECP2",
            is_het=False, annotation_result=annotation, variant=variant,
        )
        added = self._run_generate(variant, profile, annotation, "female")
        assert len(added) == 1, "Homozygous female on X is affected, not filtered"

    def test_unknown_sex_passes_through(self):
        variant = _make_variant(MECP2_RSID, "X", MECP2_HET_GENOTYPE)
        annotation = _mecp2_annotation()
        profile = _make_profile(
            MECP2_RSID, MECP2_HET_GENOTYPE, "MECP2",
            is_het=True, annotation_result=annotation, variant=variant,
        )
        added = self._run_generate(variant, profile, annotation, "unknown")
        assert len(added) == 1, "Unknown sex should not be filtered"

    def test_none_sex_passes_through(self):
        variant = _make_variant(MECP2_RSID, "X", MECP2_HET_GENOTYPE)
        annotation = _mecp2_annotation()
        profile = _make_profile(
            MECP2_RSID, MECP2_HET_GENOTYPE, "MECP2",
            is_het=True, annotation_result=annotation, variant=variant,
        )
        added = self._run_generate(variant, profile, annotation, None)
        assert len(added) == 1, "None sex should not be filtered"


class TestAutosomeNotAffectedBySexFilter:
    """Autosomal variants must never be filtered regardless of sex."""

    _AUTOSOME_RSID = "rs80359550"
    _GENE = "BRCA2"

    def _brca2_annotation(self):
        return _make_annotation(
            rsid=self._AUTOSOME_RSID,
            chromosome="13",
            gene=self._GENE,
            clin_sigs=["Pathogenic"],
            cv_alt="T",
            conditions=["Hereditary breast and ovarian cancer syndrome"],
        )

    def _run(self, inferred_sex):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        variant = _make_variant(self._AUTOSOME_RSID, "13", "AT")
        annotation = self._brca2_annotation()
        profile = _make_profile(
            self._AUTOSOME_RSID, "AT", self._GENE,
            is_het=True, annotation_result=annotation, variant=variant,
        )
        ctx = _make_ctx(
            variants=[variant],
            profiles={self._AUTOSOME_RSID: profile},
            annotation_results={self._AUTOSOME_RSID: annotation},
            inferred_sex=inferred_sex,
        )
        _run(generate_rare_mutations(ctx))
        return ctx._added

    def test_autosome_female_not_filtered(self):
        assert len(self._run("female")) == 1

    def test_autosome_male_not_filtered(self):
        assert len(self._run("male")) == 1

    def test_autosome_unknown_not_filtered(self):
        assert len(self._run("unknown")) == 1


class TestMultipleVariantsMixedChromosomes:
    """Mixed X + autosomal variants: only het female X-chromosome ones are filtered."""

    def test_het_female_x_filtered_autosome_kept(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        rsid_x = "rs267608531"
        rsid_auto = "rs80359550"

        variant_x = _make_variant(rsid_x, "X", "DI")
        ann_x = _make_annotation(rsid_x, "X", "MECP2", ["Likely_pathogenic"], "I", ["Rett syndrome"])
        profile_x = _make_profile(rsid_x, "DI", "MECP2", is_het=True, annotation_result=ann_x, variant=variant_x)

        variant_auto = _make_variant(rsid_auto, "13", "AT")
        ann_auto = _make_annotation(rsid_auto, "13", "BRCA2", ["Pathogenic"], "T", ["HBOC"])
        profile_auto = _make_profile(rsid_auto, "AT", "BRCA2", is_het=True, annotation_result=ann_auto, variant=variant_auto)

        ctx = _make_ctx(
            variants=[variant_x, variant_auto],
            profiles={rsid_x: profile_x, rsid_auto: profile_auto},
            annotation_results={rsid_x: ann_x, rsid_auto: ann_auto},
            inferred_sex="female",
        )
        _run(generate_rare_mutations(ctx))
        added_genes = {obj.gene for obj in ctx._added}
        assert "MECP2" not in added_genes, "Het female X-linked should be filtered"
        assert "BRCA2" in added_genes, "Autosomal variant should be kept"

    def test_male_both_kept(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        rsid_x = "rs267608531"
        rsid_auto = "rs80359550"

        variant_x = _make_variant(rsid_x, "X", "DD")
        ann_x = _make_annotation(rsid_x, "X", "MECP2", ["Likely_pathogenic"], "I", ["Rett syndrome"])
        profile_x = _make_profile(rsid_x, "DD", "MECP2", is_het=False, annotation_result=ann_x, variant=variant_x)

        variant_auto = _make_variant(rsid_auto, "13", "AT")
        ann_auto = _make_annotation(rsid_auto, "13", "BRCA2", ["Pathogenic"], "T", ["HBOC"])
        profile_auto = _make_profile(rsid_auto, "AT", "BRCA2", is_het=True, annotation_result=ann_auto, variant=variant_auto)

        ctx = _make_ctx(
            variants=[variant_x, variant_auto],
            profiles={rsid_x: profile_x, rsid_auto: profile_auto},
            annotation_results={rsid_x: ann_x, rsid_auto: ann_auto},
            inferred_sex="male",
        )
        _run(generate_rare_mutations(ctx))
        added_genes = {obj.gene for obj in ctx._added}
        assert "MECP2" in added_genes
        assert "BRCA2" in added_genes


class TestKnownXLinkedGenes:
    """Spot-check known X-linked genes whose ClinVar condition names
    do NOT contain 'x-linked' in them."""

    @pytest.mark.parametrize("rsid,gene,condition", [
        ("rs267608531", "MECP2", "Rett syndrome"),
        ("rs886039136", "GLA", "Fabry disease"),
        ("rs398123342", "MID1", "Opitz G/BBB syndrome"),
        ("rs606231185", "PDHA1", "Pyruvate dehydrogenase E1-alpha deficiency"),
    ])
    def test_het_female_filtered_for_known_x_genes(self, rsid, gene, condition):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        variant = _make_variant(rsid, "X", "CT")
        annotation = _make_annotation(rsid, "X", gene, ["Likely_pathogenic"], "T", [condition])
        profile = _make_profile(rsid, "CT", gene, is_het=True, annotation_result=annotation, variant=variant)

        ctx = _make_ctx(
            variants=[variant],
            profiles={rsid: profile},
            annotation_results={rsid: annotation},
            inferred_sex="female",
        )
        _run(generate_rare_mutations(ctx))
        assert len(ctx._added) == 0, f"Het female should be filtered for {gene} ({condition})"

    @pytest.mark.parametrize("rsid,gene,condition", [
        ("rs267608531", "MECP2", "Rett syndrome"),
        ("rs886039136", "GLA", "Fabry disease"),
    ])
    def test_male_not_filtered_for_known_x_genes(self, rsid, gene, condition):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        variant = _make_variant(rsid, "X", "TT")
        annotation = _make_annotation(rsid, "X", gene, ["Likely_pathogenic"], "T", [condition])
        profile = _make_profile(rsid, "TT", gene, is_het=False, annotation_result=annotation, variant=variant)

        ctx = _make_ctx(
            variants=[variant],
            profiles={rsid: profile},
            annotation_results={rsid: annotation},
            inferred_sex="male",
        )
        _run(generate_rare_mutations(ctx))
        assert len(ctx._added) == 1, f"Male should see {gene} ({condition})"


class TestInheritancePatternStillWorksWhenPresent:
    """When a condition name does contain 'x-linked', that path also works correctly."""

    def test_explicit_x_linked_in_name_still_filtered_for_het_female(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        rsid = "rs387906460"
        variant = _make_variant(rsid, "X", "CT")
        annotation = _make_annotation(
            rsid, "X", "F8", ["Pathogenic"], "T",
            ["Thrombophilia, X-linked, due to factor 8 defect"],
        )
        profile = _make_profile(rsid, "CT", "F8", is_het=True, annotation_result=annotation, variant=variant)

        ctx = _make_ctx(
            variants=[variant],
            profiles={rsid: profile},
            annotation_results={rsid: annotation},
            inferred_sex="female",
        )
        _run(generate_rare_mutations(ctx))
        assert len(ctx._added) == 0


class TestIndelSingleSubmitterFilter:
    """Indels without frequency data must have multi-submitter ClinVar evidence.
    Single-submitter indels with unknown frequency are ambiguous (D/I alleles
    cannot be reliably mapped to ref/alt at complex multi-allelic sites) and
    should be excluded to prevent false positives.
    """

    def _run_indel(self, review_statuses, clin_sigs=None, freq=None, chromosome="X"):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        rsid = "rs267608531"
        genotype = "DD"
        variant = _make_variant(rsid, chromosome, genotype)
        annotation = _make_annotation(
            rsid, chromosome, "MECP2",
            clin_sigs or ["Likely_pathogenic"],
            "I",
            ["Rett syndrome"],
            review_statuses=review_statuses,
        )
        profile = _make_profile(
            rsid, genotype, "MECP2",
            is_het=False, freq=freq,
            annotation_result=annotation, variant=variant,
        )
        ctx = _make_ctx(
            variants=[variant],
            profiles={rsid: profile},
            annotation_results={rsid: annotation},
            inferred_sex="male",
        )
        _run(generate_rare_mutations(ctx))
        return ctx._added

    def test_single_submitter_indel_no_freq_filtered(self):
        added = self._run_indel(["criteria provided, single submitter"])
        assert len(added) == 0, "Single-submitter indel with no freq should be filtered"

    def test_multi_submitter_indel_no_freq_kept(self):
        added = self._run_indel(["criteria provided, multiple submitters, no conflicts"])
        assert len(added) == 1, "Multi-submitter indel with no freq should be kept"

    def test_expert_panel_indel_no_freq_kept(self):
        added = self._run_indel(["reviewed by expert panel"])
        assert len(added) == 1

    def test_practice_guideline_indel_no_freq_kept(self):
        added = self._run_indel(["practice guideline"])
        assert len(added) == 1

    def test_single_submitter_indel_with_freq_kept(self):
        added = self._run_indel(["criteria provided, single submitter"], freq=0.0001)
        assert len(added) == 1, "Indel with known rare frequency should always be kept"

    def test_empty_review_statuses_filtered(self):
        added = self._run_indel([])
        assert len(added) == 0

    def test_snp_single_submitter_no_freq_kept(self):
        """SNPs have allele verification; single submitter is acceptable."""
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        rsid = "rs267608531"
        variant = _make_variant(rsid, "X", "TT")
        annotation = _make_annotation(
            rsid, "X", "MECP2", ["Likely_pathogenic"], "T", ["Rett syndrome"],
            review_statuses=["criteria provided, single submitter"],
        )
        profile = _make_profile(rsid, "TT", "MECP2", is_het=False, annotation_result=annotation, variant=variant)
        ctx = _make_ctx(
            variants=[variant],
            profiles={rsid: profile},
            annotation_results={rsid: annotation},
            inferred_sex="male",
        )
        _run(generate_rare_mutations(ctx))
        assert len(ctx._added) == 1, "SNP with allele verification is kept even with single submitter"

    def test_real_production_false_positives_now_filtered(self):
        """Reproduces the exact ClinVar-flagged X-linked variants from production
        that were incorrectly appearing in a male user's rare mutations."""
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        cases = [
            ("rs267608531", "MECP2", "Rett syndrome", "DD"),
            ("rs267608566", "CDKL5", "Developmental and epileptic encephalopathy, 2", "DD"),
            ("rs398123342", "MID1", "X-linked Opitz G/BBB syndrome", "DD"),
            ("rs606231185", "PDHA1", "not provided", "II"),
            ("rs104886351", "COL4A5", "X-linked Alport syndrome", "DD"),
        ]
        for rsid, gene, condition, genotype in cases:
            variant = _make_variant(rsid, "X", genotype)
            annotation = _make_annotation(
                rsid, "X", gene, ["Likely_pathogenic"], "I", [condition],
                review_statuses=["criteria provided, single submitter"],
            )
            profile = _make_profile(rsid, genotype, gene, is_het=False, annotation_result=annotation, variant=variant)
            ctx = _make_ctx(
                variants=[variant],
                profiles={rsid: profile},
                annotation_results={rsid: annotation},
                inferred_sex="male",
            )
            _run(generate_rare_mutations(ctx))
            assert len(ctx._added) == 0, f"{gene} ({rsid}) single-submitter indel should be filtered"

    def test_multi_submitter_indel_kept_for_males(self):
        """ALD (ABCD1) and Fabry (GLA) have multi-submitter evidence — must appear for males."""
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations

        cases = [
            ("rs713993050", "ABCD1", "Adrenoleukodystrophy", "II"),
            ("rs886039136", "GLA", "Fabry disease", "DD"),
        ]
        for rsid, gene, condition, genotype in cases:
            variant = _make_variant(rsid, "X", genotype)
            annotation = _make_annotation(
                rsid, "X", gene, ["Pathogenic/Likely pathogenic"], "I", [condition],
                review_statuses=["criteria provided, multiple submitters, no conflicts"],
            )
            profile = _make_profile(rsid, genotype, gene, is_het=False, annotation_result=annotation, variant=variant)
            ctx = _make_ctx(
                variants=[variant],
                profiles={rsid: profile},
                annotation_results={rsid: annotation},
                inferred_sex="male",
            )
            _run(generate_rare_mutations(ctx))
            assert len(ctx._added) == 1, f"{gene} ({rsid}) multi-submitter indel should be kept for males"

