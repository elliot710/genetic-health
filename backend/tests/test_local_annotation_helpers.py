import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services.local_annotation import (
    _count_found,
    _rsids_for,
    _build_pos_tuples,
    build_am_batch,
)


class TestCountFound:
    def test_empty_dict(self):
        assert _count_found({}) == 0

    def test_all_found(self):
        result = {"rs1": {"found": True}, "rs2": {"found": True}}
        assert _count_found(result) == 2

    def test_none_values_not_counted(self):
        result = {"rs1": None, "rs2": {"found": True}}
        assert _count_found(result) == 1

    def test_not_found_values(self):
        result = {"rs1": {"found": False}, "rs2": {"found": True}}
        assert _count_found(result) == 1

    def test_missing_found_key(self):
        result = {"rs1": {"data": "x"}, "rs2": {"found": True}}
        assert _count_found(result) == 1


class TestRsidsFor:
    def test_returns_full_rsids_when_no_per_source(self):
        rsids = ["rs1", "rs2", "rs3"]
        result = _rsids_for('clinvar_local', rsids, None)
        assert result == rsids

    def test_returns_per_source_when_provided(self):
        rsids = ["rs1", "rs2", "rs3"]
        per_source = {"clinvar_local": ["rs1"], "gnomad": ["rs2", "rs3"]}
        assert _rsids_for('clinvar_local', rsids, per_source) == ["rs1"]
        assert _rsids_for('gnomad', rsids, per_source) == ["rs2", "rs3"]

    def test_returns_empty_for_missing_source(self):
        per_source = {"gnomad": ["rs1"]}
        assert _rsids_for('clinvar_local', ["rs1", "rs2"], per_source) == []

    def test_empty_rsids_returns_empty(self):
        assert _rsids_for('clinvar_local', [], None) == []


class TestBuildPosTuples:
    def _make_variant(self, chrom, pos, ref, alt):
        marker = MagicMock()
        marker.chromosome = chrom
        marker.position = pos
        marker.ref_allele = ref
        marker.alt_alleles = alt
        v = MagicMock()
        v.marker = marker
        return v

    def test_builds_tuple_from_variant(self):
        v = self._make_variant("1", 100, "A", "T")
        result = _build_pos_tuples(["rs1"], {"rs1": v})
        assert result == [("rs1", "1", 100, "A", "T")]

    def test_skips_missing_rsid(self):
        result = _build_pos_tuples(["rs99"], {})
        assert result == []

    def test_skips_variant_without_chromosome(self):
        v = self._make_variant(None, 100, "A", "T")
        result = _build_pos_tuples(["rs1"], {"rs1": v})
        assert result == []

    def test_skips_variant_without_ref_allele(self):
        v = self._make_variant("1", 100, None, "T")
        result = _build_pos_tuples(["rs1"], {"rs1": v})
        assert result == []

    def test_multiple_variants(self):
        v1 = self._make_variant("1", 100, "A", "T")
        v2 = self._make_variant("2", 200, "G", "C")
        result = _build_pos_tuples(["rs1", "rs2"], {"rs1": v1, "rs2": v2})
        assert len(result) == 2


class TestBuildAmBatch:
    def _make_variant(self, chrom, pos, ref, alt):
        marker = MagicMock()
        marker.chromosome = chrom
        marker.position = pos
        marker.ref_allele = ref
        marker.alt_alleles = alt
        v = MagicMock()
        v.marker = marker
        return v

    def test_builds_batch_entry(self):
        v = self._make_variant("1", 100, "A", "T")
        result = build_am_batch(["rs1"], {"rs1": v})
        assert len(result) == 1
        assert result[0]["rsid"] == "rs1"
        assert result[0]["ref_allele"] == "A"
        assert result[0]["alt_allele"] == "T"

    def test_skips_missing_variant(self):
        result = build_am_batch(["rs99"], {})
        assert result == []

    def test_skips_incomplete_variant(self):
        v = self._make_variant("1", None, "A", "T")
        result = build_am_batch(["rs1"], {"rs1": v})
        assert result == []

    def test_uses_only_first_alt(self):
        v = self._make_variant("1", 100, "A", "T,G")
        result = build_am_batch(["rs1"], {"rs1": v})
        assert len(result) == 1
        assert result[0]["alt_allele"] == "T"


class TestApplyPositionFallback:
    @pytest.mark.asyncio
    async def test_skips_when_no_method(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock(spec=[])  # no lookup_batch_by_position
        result_dict = {"rs1": {"found": False}}
        await _apply_position_fallback(svc, ["rs1"], result_dict, {})
        assert result_dict["rs1"] == {"found": False}

    @pytest.mark.asyncio
    async def test_skips_when_no_misses(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock()
        svc.lookup_batch_by_position = AsyncMock(return_value={})
        result_dict = {"rs1": {"found": True}}
        await _apply_position_fallback(svc, ["rs1"], result_dict, {})
        svc.lookup_batch_by_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_fills_in_from_position_results(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock()
        svc.lookup_batch_by_position = AsyncMock(return_value={"rs1": {"found": True, "data": "x"}})
        marker = MagicMock()
        marker.chromosome = "1"
        marker.position = 100
        marker.ref_allele = "A"
        marker.alt_alleles = "T"
        v = MagicMock()
        v.marker = marker
        result_dict: dict = {}
        await _apply_position_fallback(svc, ["rs1"], result_dict, {"rs1": v})
        assert result_dict["rs1"]["found"] is True
