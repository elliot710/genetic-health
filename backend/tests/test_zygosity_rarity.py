"""U3: a common allele cannot reach high/very_high personal risk, regardless of
composite score or zygosity — the risk level is capped at 'moderate'."""
from backend.services.insight_generators.base import assess_risk_level


_HIGH_COMPOSITE = {"composite_score": 0.9}


class TestRiskLevelRarityCap:
    def test_common_allele_capped_at_moderate(self):
        # hom-alt + composite >= 0.80 would escalate to very_high; the 79%
        # frequency caps it (rs397518480 class).
        level = assess_risk_level(
            "T/T", 2.3, ref_allele="C",
            pathogenicity_score=_HIGH_COMPOSITE, population_frequency=0.79,
        )
        assert level not in ("high", "very_high")

    def test_rare_allele_reaches_very_high(self):
        level = assess_risk_level(
            "T/T", 2.3, ref_allele="C",
            pathogenicity_score=_HIGH_COMPOSITE, population_frequency=0.0005,
        )
        assert level == "very_high"

    def test_unknown_frequency_does_not_cap(self):
        level = assess_risk_level(
            "T/T", 2.3, ref_allele="C",
            pathogenicity_score=_HIGH_COMPOSITE, population_frequency=None,
        )
        assert level == "very_high"
