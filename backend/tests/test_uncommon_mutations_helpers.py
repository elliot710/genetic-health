"""Tests for pure helpers in uncommon_mutations.py and rare_mutations.py."""


class TestGetAltAlleles:
    """Tests for _get_alt_alleles in uncommon_mutations.py."""

    def _fn(self):
        from backend.services.insight_generators.uncommon_mutations import _get_alt_alleles
        return _get_alt_alleles

    def test_returns_empty_when_no_data(self):
        assert self._fn()({}) == []

    def test_extracts_from_ensembl_allele_string(self):
        annotations = {
            "ensembl": {"data": [{"allele_string": "G/A"}]}
        }
        assert self._fn()(annotations) == ["A"]

    def test_extracts_multiple_alts_from_ensembl(self):
        annotations = {
            "ensembl": {"data": [{"allele_string": "G/A,T"}]}
        }
        result = self._fn()(annotations)
        assert "A" in result
        assert "T" in result
        assert len(result) == 2

    def test_skips_dash_alt(self):
        annotations = {
            "ensembl": {"data": [{"allele_string": "G/-"}]}
        }
        result = self._fn()(annotations)
        assert result == []

    def test_falls_back_to_clinvar(self):
        annotations = {
            "clinvar_local": {"found": True, "alt_allele": "T"}
        }
        assert self._fn()(annotations) == ["T"]

    def test_falls_back_to_gnomad(self):
        annotations = {
            "gnomad": {"found": True, "alt": "C"}
        }
        assert self._fn()(annotations) == ["C"]

    def test_skips_n_allele(self):
        annotations = {
            "ensembl": {"data": [{"allele_string": "G/N"}]}
        }
        result = self._fn()(annotations)
        assert result == []

    def test_ensembl_takes_priority_over_clinvar(self):
        annotations = {
            "ensembl": {"data": [{"allele_string": "G/A"}]},
            "clinvar_local": {"found": True, "alt_allele": "T"},
        }
        assert self._fn()(annotations) == ["A"]

    def test_empty_ensembl_data_falls_back(self):
        annotations = {
            "ensembl": {"data": []},
            "clinvar_local": {"found": True, "alt_allele": "C"},
        }
        assert self._fn()(annotations) == ["C"]

    def test_clinvar_not_found_falls_back_to_gnomad(self):
        annotations = {
            "clinvar_local": {"found": False, "alt_allele": "T"},
            "gnomad": {"found": True, "alt": "A"},
        }
        assert self._fn()(annotations) == ["A"]


class TestIndelDIsRef:
    """Tests for indel_d_is_ref in base.py."""

    def _fn(self):
        from backend.services.insight_generators.base import indel_d_is_ref
        return indel_d_is_ref

    def test_returns_none_when_no_ref(self):
        assert self._fn()(None, "AT") is None

    def test_returns_none_when_no_alt(self):
        assert self._fn()("A", None) is None

    def test_returns_true_when_ref_shorter(self):
        assert self._fn()("A", "AT") is True

    def test_returns_false_when_ref_longer(self):
        assert self._fn()("AT", "A") is False

    def test_returns_none_when_same_length(self):
        assert self._fn()("AT", "GC") is None

    def test_returns_none_for_n_ref(self):
        assert self._fn()("N", "AT") is None

    def test_returns_none_for_dot_alt(self):
        assert self._fn()("A", ".") is None

    def test_handles_multiallelic_alt(self):
        # Multi-allelic: takes first alt for comparison
        result = self._fn()("A", "AT,ATT")
        assert result is True

    def test_strips_whitespace(self):
        assert self._fn()(" A ", " AT ") is True
