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

    def test_missing_significance_alone_is_not_disqualifying(self):
        # May rest on non-ClinVar evidence (gnomAD LoF); don't auto-deactivate.
        assert is_reliable_clinical_mapping(None, "missense_variant", 0.0001)[0] is True
        assert is_reliable_clinical_mapping("", None)[0] is True

    def test_missing_significance_with_synonymous_still_rejected(self):
        assert is_reliable_clinical_mapping(None, "synonymous_variant")[0] is False

    def test_intron_and_utr_rejected(self):
        assert is_reliable_clinical_mapping("Pathogenic", "intron_variant")[0] is False
        assert is_reliable_clinical_mapping("Pathogenic", "3_prime_UTR_variant")[0] is False

    def test_multi_consequence_with_damaging_transcript_is_kept(self):
        # molecular_consequence lists consequences across transcripts; a real
        # missense/nonsense/splice variant must not be flagged just because an
        # alternate transcript is intronic/UTR/synonymous.
        assert is_reliable_clinical_mapping("Pathogenic", "missense_variant, intron_variant")[0] is True
        assert is_reliable_clinical_mapping("Pathogenic", "splice_acceptor_variant, synonymous_variant")[0] is True
        assert is_reliable_clinical_mapping("Pathogenic", "nonsense, 5_prime_UTR_variant")[0] is True

    def test_only_non_damaging_consequences_rejected(self):
        assert is_reliable_clinical_mapping("Pathogenic", "synonymous_variant, intron_variant")[0] is False


class TestEvaluateClinicalMapping:
    """U6: audit an existing mapping by joining it to its ClinVar record."""

    def _record(self, **kw):
        from types import SimpleNamespace
        defaults = dict(clinical_significance="Pathogenic", molecular_consequence=None,
                        af_exac=None, af_tgp=None, af_esp=None)
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    def _eval(self):
        from backend.scripts.remediate_mappings import evaluate_clinical_mapping
        return evaluate_clinical_mapping

    def test_synonymous_record_makes_mapping_unreliable(self):
        ok, reason = self._eval()(
            {"clinical_significance": "pathogenic", "condition": "X-linked parkinsonism"},
            self._record(molecular_consequence="synonymous_variant"),
        )
        assert ok is False
        assert "consequence" in reason.lower()

    def test_common_record_makes_mapping_unreliable(self):
        ok, reason = self._eval()(
            {"clinical_significance": "pathogenic"},
            self._record(molecular_consequence="missense_variant", af_tgp=0.79),
        )
        assert ok is False
        assert "common" in reason.lower()

    def test_rare_missense_record_is_reliable(self):
        ok, reason = self._eval()(
            {"clinical_significance": "pathogenic"},
            self._record(molecular_consequence="missense_variant", af_tgp=0.0002),
        )
        assert ok is True

    def test_missing_clinvar_record_uses_mapping_significance(self):
        # No ClinVar record found: fall back to the mapping's own significance;
        # unknown consequence/frequency is not disqualifying.
        ok, reason = self._eval()({"clinical_significance": "pathogenic"}, None)
        assert ok is True

    def test_merge_picks_consequence_from_vcf_row(self):
        # rs397518480 has a tsv row (consequence NULL) + a vcf row (synonymous);
        # merging must surface the synonymous consequence regardless of row order.
        from types import SimpleNamespace
        from backend.scripts.remediate_mappings import _merge_clinvar_records
        tsv = SimpleNamespace(rsid="rs397518480", clinical_significance="Pathogenic",
                              molecular_consequence=None, af_exac=None, af_tgp=None, af_esp=None)
        vcf = SimpleNamespace(rsid="rs397518480", clinical_significance="Pathogenic",
                              molecular_consequence="synonymous_variant", af_exac=None,
                              af_tgp=None, af_esp=None)
        merged = _merge_clinvar_records([tsv, vcf])
        assert merged["rs397518480"].molecular_consequence == "synonymous_variant"
        ok, reason = self._eval()({"clinical_significance": "pathogenic"}, merged["rs397518480"])
        assert ok is False
        assert "consequence" in reason.lower()
