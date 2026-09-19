"""Parity guard: no generator turns an ambiguous indel code into a claim.

Consumer arrays report indels as I (longer allele) and D (shorter allele).
Which of those is the alternate allele depends on the variant, and at a
multi-allelic site it is not recoverable at all. Every generator that can emit
a clinical claim must therefore stay silent when the direction is unresolvable,
rather than guessing. The 2026-09 false positives came from one generator
guessing while its neighbours did not, so the asymmetry is what this file locks
down.
"""
import asyncio
from unittest.mock import MagicMock

from backend.services.insight_generators.base import GeneratorContext

UNRESOLVABLE = ("AT", "GC")      # equal lengths — neither allele is "the longer one"
MULTI_ALLELIC = ("A", "AT,ATT")  # I could be either alternate
DELETION = ("AT", "A")           # ref longer — D is the alternate


def _make_variant(rsid, genotype, ref_allele, alt_allele, chromosome="1"):
    variant = MagicMock()
    variant.rsid = rsid
    variant.genotype = genotype
    variant.chromosome = chromosome
    marker = MagicMock()
    marker.ref_allele = ref_allele
    marker.alt_alleles = alt_allele
    marker.gene_symbol = "XYZ"
    variant.marker = marker
    return variant


def _make_annotation(rsid, ref_allele, alt_allele, gene="XYZ",
                     consequence="frameshift_variant", frequency=None):
    annotation = MagicMock()
    annotation.rsid = rsid
    annotation.annotation_data = {
        "annotations": {
            "ensembl": {
                "data": [{
                    "allele_string": f"{ref_allele}/{alt_allele}",
                    "most_severe_consequence": consequence,
                    "transcript_consequences": [
                        {"gene_symbol": gene, "consequence_terms": [consequence],
                         "impact": "HIGH"},
                    ],
                }],
            },
            "clinvar_local": {
                "found": True,
                "clinical_significances": ["Pathogenic"],
                "genes": [gene],
                "conditions": ["Some recessive disease"],
                "gene_conditions": [{"gene": gene, "disease": "Some recessive disease"}],
                "ref_allele": ref_allele,
                "alt_allele": alt_allele,
                "review_statuses": ["criteria provided, multiple submitters, no conflicts"],
            },
        }
    }
    if frequency is not None:
        annotation.annotation_data["annotations"]["gnomad"] = {
            "found": True, "af": frequency,
        }
    return annotation


def _make_ctx(variants, annotations, rsid_map=None, gene_map=None, inferred_sex=None):
    ctx = MagicMock(spec=GeneratorContext)
    ctx.analysis_id = 1
    ctx.variants = variants
    ctx.annotation_results = annotations
    ctx.rsid_gene_map = {}
    ctx.variant_profiles = {}
    ctx.inferred_sex = inferred_sex
    ctx.session = MagicMock()
    ctx.get_maps = MagicMock(return_value=(rsid_map or {}, gene_map or {}))
    return ctx


def _run_carrier(genotype, alleles):
    from backend.services.insight_generators.carrier import generate_carrier_status
    ref, alt = alleles
    variant = _make_variant("rs999", genotype, ref, alt)
    annotation = _make_annotation("rs999", ref, alt)
    ctx = _make_ctx([variant], {"rs999": annotation})
    return asyncio.run(generate_carrier_status(ctx)), ctx


class TestCarrierStatus:
    def test_unresolvable_direction_emits_no_carrier_finding(self):
        count, _ = _run_carrier("II", UNRESOLVABLE)
        assert count == 0

    def test_multi_allelic_site_emits_no_carrier_finding(self):
        count, _ = _run_carrier("II", MULTI_ALLELIC)
        assert count == 0

    def test_heterozygous_indel_code_is_reported_as_carrier(self):
        _, ctx = _run_carrier("DI", DELETION)
        emitted = ctx.session.add.call_args[0][0]
        assert emitted.carrier_status == "carrier"

    def test_heterozygous_indel_code_is_never_reported_as_affected(self):
        _, ctx = _run_carrier("ID", DELETION)
        emitted = ctx.session.add.call_args[0][0]
        assert emitted.carrier_status != "affected"


class TestCognitiveProfile:
    """Holds baseline on an indel code rather than fabricating a dosage boost."""

    def _percentile(self, genotype, ref_allele):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        return _adjust_percentile(50, genotype, ref_allele)

    def test_indel_code_leaves_percentile_at_baseline(self):
        assert self._percentile("II", "AT") == 50

    def test_resolvable_homozygote_still_receives_the_dosage_boost(self):
        assert self._percentile("TT", "A") == 60


class TestUncommonMutations:
    def test_indel_coded_genotype_is_excluded(self):
        from backend.services.insight_generators.uncommon_mutations import (
            generate_uncommon_mutations,
        )
        ref, alt = UNRESOLVABLE
        variant = _make_variant("rs888", "II", ref, alt)
        annotation = _make_annotation("rs888", ref, alt, frequency=0.01)
        ctx = _make_ctx([variant], {"rs888": annotation})
        assert asyncio.run(generate_uncommon_mutations(ctx)) == 0


class TestRareMutations:
    def test_unresolvable_direction_emits_no_rare_mutation(self):
        from backend.services.insight_generators.rare_mutations import (
            generate_rare_mutations,
        )
        ref, alt = UNRESOLVABLE
        variant = _make_variant("rs777", "II", ref, alt, chromosome="X")
        annotation = _make_annotation("rs777", ref, alt, frequency=1e-5)
        ctx = _make_ctx([variant], {"rs777": annotation}, inferred_sex="male")
        asyncio.run(generate_rare_mutations(ctx))
        assert ctx.session.add.call_count == 0
