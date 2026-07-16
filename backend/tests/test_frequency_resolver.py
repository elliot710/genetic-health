"""U1: one authoritative population-AF signal, fed from VEP -> gnomAD -> 1000G,
reaching the composite scorer even when the gnomAD annotation is absent."""
import pytest

from backend.services.insight_generators.base.frequency import (
    resolve_population_frequency,
    extract_frequency,
)
from backend.services.scoring_engine import ScoringEngine


def _ensembl_with_freq(af: float) -> dict:
    return {
        "data": [
            {"colocated_variants": [{"frequencies": {"T": {"gnomade": af}}}]}
        ]
    }


class TestResolvePopulationFrequency:
    def test_vep_colocated_frequency_is_used(self):
        annotations = {"ensembl": _ensembl_with_freq(0.79)}
        assert resolve_population_frequency(annotations) == pytest.approx(0.79)

    def test_gnomad_local_af_is_used_when_vep_absent(self):
        annotations = {"gnomad": {"found": True, "af": 0.42}}
        assert resolve_population_frequency(annotations) == pytest.approx(0.42)

    def test_thousand_genomes_global_af_is_last_fallback(self):
        annotations = {"thousand_genomes": {"found": True, "global_af": 0.31}}
        assert resolve_population_frequency(annotations) == pytest.approx(0.31)

    def test_vep_takes_priority_over_gnomad(self):
        annotations = {
            "ensembl": _ensembl_with_freq(0.79),
            "gnomad": {"found": True, "af": 0.02},
        }
        assert resolve_population_frequency(annotations) == pytest.approx(0.79)

    def test_returns_none_when_no_source_has_frequency(self):
        assert resolve_population_frequency({"clinvar_local": {"found": True}}) is None

    def test_extract_frequency_still_returns_float_zero_when_unknown(self):
        # Preserve the legacy float contract for existing callers.
        class _Ann:
            annotation_data = {"annotations": {}}
        assert extract_frequency(_Ann()) == 0.0


class TestScorerAfFallback:
    def test_gnomad_af_evidence_added_from_vep_when_gnomad_annotation_absent(self):
        # rs397518480 class: gnomAD annotation missing ("x gnomAD"), but VEP
        # carries the 79% frequency. The scorer must still receive the rarity
        # signal so a common allele is not scored as if frequency were unknown.
        annotations = {
            "ensembl": _ensembl_with_freq(0.79),
            "alpha_missense": {"am_pathogenicity": 0.9},
        }
        result = ScoringEngine().score_variant(annotations)
        assert "gnomad_af" in result["sources"]
        assert result["sources"]["gnomad_af"]["score"] == pytest.approx(0.10)

    def test_no_gnomad_af_evidence_when_no_frequency_anywhere(self):
        annotations = {"alpha_missense": {"am_pathogenicity": 0.9}}
        result = ScoringEngine().score_variant(annotations)
        assert "gnomad_af" not in result["sources"]
