import pytest
from types import SimpleNamespace

from backend.services.dashboard_serializers import (
    _dedup_by,
    _clean_trait_name,
    _to_list,
)
from backend.services.dashboard_service import (
    extract_panel_rsids,
    analysis_fingerprint,
)
from backend.services.dashboard_maps import (
    _populate_allele_string_map,
    _populate_am_map,
    _populate_cv_count_map,
    _populate_pharmgkb_map,
)


class TestDedupBy:
    def test_removes_duplicates_by_key(self):
        items = [{"name": "a", "v": 1}, {"name": "b", "v": 2}, {"name": "a", "v": 3}]
        result = _dedup_by(items, "name")
        assert len(result) == 2
        assert result[0]["v"] == 1

    def test_preserves_order(self):
        items = [{"k": "c"}, {"k": "a"}, {"k": "b"}, {"k": "a"}]
        result = _dedup_by(items, "k")
        assert [r["k"] for r in result] == ["c", "a", "b"]

    def test_empty_list(self):
        assert _dedup_by([], "key") == []

    def test_all_unique(self):
        items = [{"x": i} for i in range(5)]
        assert len(_dedup_by(items, "x")) == 5


class TestCleanTraitName:
    def test_plain_string_unchanged(self):
        assert _clean_trait_name("Hemochromatosis") == "Hemochromatosis"

    def test_pipe_delimited_picks_first_meaningful(self):
        raw = "not provided|MTHFR deficiency|other"
        result = _clean_trait_name(raw)
        assert result == "MTHFR deficiency"

    def test_semicolon_delimited(self):
        raw = "not specified;Brugada syndrome"
        result = _clean_trait_name(raw)
        assert result == "Brugada syndrome"

    def test_all_caps_becomes_title_case(self):
        raw = "not provided|BRCA1 MUTATION"
        result = _clean_trait_name(raw)
        assert result == "Brca1 Mutation"

    def test_empty_string_returns_unknown(self):
        assert _clean_trait_name("") == "Unknown"

    def test_none_returns_unknown(self):
        assert _clean_trait_name(None) == "Unknown"


class TestToList:
    def test_list_passed_through(self):
        assert _to_list(["a", "b"]) == ["a", "b"]

    def test_string_wrapped_in_list(self):
        assert _to_list("hello") == ["hello"]

    def test_none_returns_empty(self):
        assert _to_list(None) == []

    def test_empty_string_returns_empty(self):
        assert _to_list("") == []


class TestExtractPanelRsids:
    def test_extracts_variants_from_associated_variants(self):
        data = {
            "health_risks": [{"associated_variants": ["rs123", "rs456"]}],
            "drug_responses": [{"variants_involved": ["rs789"]}],
        }
        result = extract_panel_rsids(data)
        assert {"rs123", "rs456", "rs789"}.issubset(result)

    def test_extracts_direct_rsid_fields(self):
        data = {"rare_mutations": [{"rsid": "rs111"}]}
        result = extract_panel_rsids(data)
        assert "rs111" in result

    def test_ignores_non_rs_values(self):
        data = {"physical_traits": [{"rsid": "GENE_NAME", "associated_variants": ["rs999"]}]}
        result = extract_panel_rsids(data)
        assert "GENE_NAME" not in result
        assert "rs999" in result

    def test_empty_data(self):
        assert extract_panel_rsids({}) == set()


class TestPopulateAlleleStringMap:
    def _make_row(self, rsid="rs1", ensembl_data=None, ref_allele=None, alt_alleles=None):
        return SimpleNamespace(
            rsid=rsid,
            ensembl_data=ensembl_data,
            ref_allele=ref_allele,
            alt_alleles=alt_alleles,
        )

    def test_uses_ensembl_allele_string_first(self):
        allele_string_map = {}
        row = self._make_row(
            ensembl_data={"data": [{"allele_string": "A/T"}]},
            ref_allele="T",
            alt_alleles="A",
        )
        _populate_allele_string_map(row, allele_string_map)
        assert allele_string_map["rs1"] == "A/T"

    def test_falls_back_to_marker_data_when_no_ensembl(self):
        allele_string_map = {}
        row = self._make_row(ref_allele="G", alt_alleles="C")
        _populate_allele_string_map(row, allele_string_map)
        assert allele_string_map["rs1"] == "G/C"

    def test_skips_malformed_ensembl_allele_string(self):
        allele_string_map = {}
        row = self._make_row(
            ensembl_data={"data": [{"allele_string": "INVALID"}]},
            ref_allele="A",
            alt_alleles="C",
        )
        _populate_allele_string_map(row, allele_string_map)
        assert allele_string_map["rs1"] == "A/C"

    def test_skips_row_with_no_allele_info(self):
        allele_string_map = {}
        row = self._make_row()
        _populate_allele_string_map(row, allele_string_map)
        assert "rs1" not in allele_string_map


def _make_row(**kwargs):
    return SimpleNamespace(**kwargs)


class TestPopulateAmMap:
    def test_populates_when_found(self):
        am_map = {}
        row = _make_row(rsid="rs1", alpha_missense_data={"found": True, "am_pathogenicity": 0.9, "am_class": "pathogenic"})
        _populate_am_map(row, am_map)
        assert am_map["rs1"] == {"score": 0.9, "classification": "pathogenic"}

    def test_skips_when_not_found(self):
        am_map = {}
        row = _make_row(rsid="rs1", alpha_missense_data={"found": False})
        _populate_am_map(row, am_map)
        assert "rs1" not in am_map

    def test_skips_when_none(self):
        am_map = {}
        row = _make_row(rsid="rs1", alpha_missense_data=None)
        _populate_am_map(row, am_map)
        assert "rs1" not in am_map

    def test_skips_when_not_dict(self):
        am_map = {}
        row = _make_row(rsid="rs1", alpha_missense_data="invalid")
        _populate_am_map(row, am_map)
        assert "rs1" not in am_map


class TestPopulateCvCountMap:
    def test_populates_count_when_found(self):
        cv_map = {}
        row = _make_row(rsid="rs1", clinvar_data={"found": True, "count": 3})
        _populate_cv_count_map(row, cv_map)
        assert cv_map["rs1"] == 3

    def test_skips_when_count_is_zero(self):
        cv_map = {}
        row = _make_row(rsid="rs1", clinvar_data={"found": True, "count": 0})
        _populate_cv_count_map(row, cv_map)
        assert "rs1" not in cv_map

    def test_skips_when_not_found(self):
        cv_map = {}
        row = _make_row(rsid="rs1", clinvar_data={"found": False, "count": 5})
        _populate_cv_count_map(row, cv_map)
        assert "rs1" not in cv_map

    def test_skips_when_none(self):
        cv_map = {}
        row = _make_row(rsid="rs1", clinvar_data=None)
        _populate_cv_count_map(row, cv_map)
        assert "rs1" not in cv_map


class TestPopulatePharmgkbMap:
    def test_populates_when_found(self):
        pgkb_map = {}
        row = _make_row(rsid="rs1", pharmgkb_data={"found": True, "gene": "CYP2D6"})
        _populate_pharmgkb_map(row, pgkb_map)
        assert "rs1" in pgkb_map
        assert pgkb_map["rs1"]["gene"] == "CYP2D6"

    def test_skips_when_not_found(self):
        pgkb_map = {}
        row = _make_row(rsid="rs1", pharmgkb_data={"found": False})
        _populate_pharmgkb_map(row, pgkb_map)
        assert "rs1" not in pgkb_map

    def test_extracts_haplotypes(self):
        pgkb_map = {}
        row = _make_row(rsid="rs1", pharmgkb_data={
            "found": True, "gene": "CYP2D6",
            "variants": [{"haplotype": "*1"}, {"star_allele": "*4"}],
        })
        _populate_pharmgkb_map(row, pgkb_map)
        assert "haplotypes" in pgkb_map["rs1"]

    def test_extracts_cpic_guideline_from_guidelines(self):
        pgkb_map = {}
        row = _make_row(rsid="rs1", pharmgkb_data={
            "found": True, "gene": "VKORC1",
            "guidelines": [{"name": "CPIC Warfarin guideline", "url": "https://cpicpgx.org/..."}],
        })
        _populate_pharmgkb_map(row, pgkb_map)
        assert pgkb_map["rs1"].get("cpic_guideline") == "CPIC Warfarin guideline"


class TestAnalysisFingerprint:
    def test_produces_string(self):
        a = SimpleNamespace(id=1, analysis_status="complete", processed_variants=100)
        result = analysis_fingerprint([a])
        assert isinstance(result, str)

    def test_sorts_analyses(self):
        a1 = SimpleNamespace(id=2, analysis_status="complete", processed_variants=50)
        a2 = SimpleNamespace(id=1, analysis_status="complete", processed_variants=100)
        result = analysis_fingerprint([a1, a2])
        assert result == analysis_fingerprint([a2, a1])

    def test_different_status_gives_different_fingerprint(self):
        a1 = SimpleNamespace(id=1, analysis_status="complete", processed_variants=100)
        a2 = SimpleNamespace(id=1, analysis_status="failed", processed_variants=100)
        assert analysis_fingerprint([a1]) != analysis_fingerprint([a2])

    def test_handles_none_processed_variants(self):
        a = SimpleNamespace(id=1, analysis_status="pending", processed_variants=None)
        result = analysis_fingerprint([a])
        assert "1:pending:0" in result
