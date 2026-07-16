"""U4: a common allele cannot be classified 'Pathogenic' by the composite,
regardless of ClinVar — the rarity cap downgrades the label and records a
conflict. A genuinely rare pathogenic allele is unaffected."""
import pytest

from backend.services.scoring_engine import ScoringEngine


def _annotations(freq: float) -> dict:
    return {
        "clinvar": {"found": True, "clinical_significance": "Pathogenic"},
        "ensembl": {"data": [{"colocated_variants": [{"frequencies": {"T": {"gnomade": freq}}}]}]},
    }


class TestCompositeRarityCap:
    def test_common_pathogenic_allele_is_not_classified_pathogenic(self):
        result = ScoringEngine().score_variant(_annotations(0.79))
        assert result["classification"] not in ("pathogenic", "likely_pathogenic")

    def test_common_pathogenic_allele_records_rarity_conflict(self):
        result = ScoringEngine().score_variant(_annotations(0.79))
        assert any(
            "common" in c.lower() or "frequen" in c.lower()
            for c in result["conflicts"]
        )

    def test_rare_pathogenic_allele_stays_pathogenic(self):
        result = ScoringEngine().score_variant(_annotations(0.0005))
        assert result["classification"] == "pathogenic"
