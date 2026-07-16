"""U5/U6: the single reliability predicate that gates new auto-discovered
clinical mappings and audits existing ones — a clinical mapping is unreliable
when its variant is benign/conflicting, a non-damaging consequence
(synonymous/intron/UTR/…), or a common allele."""
from backend.services.mapping_reliability import is_reliable_clinical_mapping


class TestIsReliableClinicalMapping:
    def test_missense_pathogenic_rare_is_reliable(self):
        ok, reason = is_reliable_clinical_mapping(
            "Pathogenic", "missense_variant", 0.0005, None, None
        )
        assert ok is True
        assert reason is None

    def test_synonymous_is_rejected(self):
        # rs397518480 class: p.Ser115= synonymous, ClinVar 'Pathogenic'.
        ok, reason = is_reliable_clinical_mapping(
            "Pathogenic", "synonymous_variant", None, None, None
        )
        assert ok is False
        assert "consequence" in reason.lower()

    def test_common_allele_is_rejected(self):
        ok, reason = is_reliable_clinical_mapping(
            "Pathogenic", "missense_variant", None, 0.79, None
        )
        assert ok is False
        assert "common" in reason.lower()

    def test_benign_significance_is_rejected(self):
        ok, reason = is_reliable_clinical_mapping(
            "Benign", "missense_variant", 0.0005, None, None
        )
        assert ok is False

    def test_conflicting_significance_is_rejected(self):
        ok, reason = is_reliable_clinical_mapping(
            "Conflicting_interpretations_of_pathogenicity", "missense_variant", None, None, None
        )
        assert ok is False

    def test_unknown_consequence_and_frequency_is_reliable(self):
        # Missing consequence/frequency is unknown, not disqualifying — the
        # runtime matching gate (U2) still guards these.
        ok, reason = is_reliable_clinical_mapping("Pathogenic", None, None, None, None)
        assert ok is True

    def test_intron_and_utr_rejected(self):
        assert is_reliable_clinical_mapping("Pathogenic", "intron_variant")[0] is False
        assert is_reliable_clinical_mapping("Pathogenic", "3_prime_UTR_variant")[0] is False
