import pytest
from types import SimpleNamespace

from backend.services.insight_generators.base import (
    indel_d_is_ref,
    is_homozygous_reference,
    is_heterozygous,
    is_clinvar_benign,
    _get_all_clinvar_significances,
    _has_computational_pathogenicity,
)


def _make_annotation_result(annotations: dict):
    return SimpleNamespace(annotation_data={"annotations": annotations})


class TestIndelDIsRef:
    def test_insertion_variant_returns_true(self):
        assert indel_d_is_ref("A", "ATCG") is True

    def test_deletion_variant_returns_false(self):
        assert indel_d_is_ref("ATCG", "A") is False

    def test_snp_returns_none(self):
        assert indel_d_is_ref("A", "T") is None

    def test_unknown_char_returns_none(self):
        assert indel_d_is_ref("N", "A") is None
        assert indel_d_is_ref("-", "A") is None

    def test_none_inputs_return_none(self):
        assert indel_d_is_ref(None, "A") is None
        assert indel_d_is_ref("A", None) is None

    def test_multiallelic_alt_uses_first(self):
        assert indel_d_is_ref("A", "ATCG,ATG") is True

    def test_equal_length_returns_none(self):
        assert indel_d_is_ref("AT", "GC") is None


class TestIsHomozygousReference:
    def test_homozygous_ref_returns_true(self):
        assert is_homozygous_reference("AA", ref_allele="A") is True

    def test_homozygous_alt_returns_false(self):
        assert is_homozygous_reference("TT", ref_allele="A") is False

    def test_heterozygous_returns_false(self):
        assert is_homozygous_reference("AT", ref_allele="A") is False

    def test_no_call_returns_false(self):
        assert is_homozygous_reference("--") is False
        assert is_homozygous_reference("00") is False

    def test_indel_dd_with_d_is_ref(self):
        assert is_homozygous_reference("DD", ref_allele="A", alt_allele="ATG") is True

    def test_indel_ii_with_d_is_alt(self):
        assert is_homozygous_reference("II", ref_allele="ATG", alt_allele="A") is True

    def test_none_genotype_returns_false(self):
        assert is_homozygous_reference(None) is False

    def test_no_ref_allele_returns_false(self):
        assert is_homozygous_reference("AA") is False


class TestGetAllClinvarSignificances:
    def test_empty_annotations_returns_empty(self):
        assert _get_all_clinvar_significances({}) == []

    def test_clinvar_local_significances(self):
        anns = {"clinvar_local": {"found": True, "clinical_significances": ["Benign", "Likely benign"]}}
        result = _get_all_clinvar_significances(anns)
        assert "Benign" in result
        assert "Likely benign" in result

    def test_clinvar_api_entries(self):
        anns = {"clinvar": {"found": True, "entries": [{"clinical_significance": ["Pathogenic"]}]}}
        result = _get_all_clinvar_significances(anns)
        assert "Pathogenic" in result

    def test_clinvar_api_string_significance(self):
        anns = {"clinvar": {"found": True, "clinical_significance": "VUS", "entries": []}}
        result = _get_all_clinvar_significances(anns)
        assert "VUS" in result

    def test_not_found_source_excluded(self):
        anns = {"clinvar_local": {"found": False, "clinical_significances": ["Benign"]}}
        result = _get_all_clinvar_significances(anns)
        assert result == []


class TestHasComputationalPathogenicity:
    def test_alpha_missense_pathogenic(self):
        anns = {"alpha_missense": {"found": True, "am_class": "likely_pathogenic"}}
        assert _has_computational_pathogenicity(anns) is True

    def test_alpha_missense_benign_not_flagged(self):
        anns = {"alpha_missense": {"found": True, "am_class": "likely_benign"}}
        assert _has_computational_pathogenicity(anns) is False

    def test_cadd_high_score(self):
        anns = {"gnomad": {"found": True, "cadd": {"phred": 30}}}
        assert _has_computational_pathogenicity(anns) is True

    def test_cadd_low_score(self):
        anns = {"gnomad": {"found": True, "cadd": {"phred": 10}}}
        assert _has_computational_pathogenicity(anns) is False

    def test_empty_annotations(self):
        assert _has_computational_pathogenicity({}) is False


class TestIsClinvarBenign:
    def test_no_annotation_result_returns_false(self):
        assert is_clinvar_benign(None) is False

    def test_no_annotation_data_returns_false(self):
        ar = SimpleNamespace(annotation_data=None)
        assert is_clinvar_benign(ar) is False

    def test_no_clinvar_data_returns_false(self):
        ar = _make_annotation_result({"ensembl": {"found": True}})
        assert is_clinvar_benign(ar) is False

    def test_benign_clinvar_with_benign_am_returns_true(self):
        ar = _make_annotation_result({
            "clinvar_local": {"found": True, "clinical_significances": ["Benign"]},
            "alpha_missense": {"found": True, "am_class": "likely_benign"},
        })
        assert is_clinvar_benign(ar) is True

    def test_pathogenic_clinvar_returns_false(self):
        ar = _make_annotation_result({
            "clinvar_local": {"found": True, "clinical_significances": ["Pathogenic"]},
        })
        assert is_clinvar_benign(ar) is False

    def test_benign_clinvar_but_pathogenic_am_returns_false(self):
        ar = _make_annotation_result({
            "clinvar_local": {"found": True, "clinical_significances": ["Benign"]},
            "alpha_missense": {"found": True, "am_class": "likely_pathogenic"},
        })
        assert is_clinvar_benign(ar) is False

    def test_mixed_benign_and_vus_returns_false(self):
        ar = _make_annotation_result({
            "clinvar_local": {"found": True, "clinical_significances": ["Benign", "Uncertain significance"]},
        })
        assert is_clinvar_benign(ar) is False

    def test_likely_benign_accepted(self):
        ar = _make_annotation_result({
            "clinvar_local": {"found": True, "clinical_significances": ["Likely benign"]},
        })
        assert is_clinvar_benign(ar) is True

    def test_high_cadd_overrides_benign_clinvar(self):
        ar = _make_annotation_result({
            "clinvar_local": {"found": True, "clinical_significances": ["Benign"]},
            "gnomad": {"found": True, "cadd": {"phred": 28}},
        })
        assert is_clinvar_benign(ar) is False
