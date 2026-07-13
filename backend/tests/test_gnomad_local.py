"""Tests for gnomAD AF honesty: BigQuery unreachable from the analysis
lookup path, and CADD-only results never fabricate an allele frequency."""
import pytest
from unittest.mock import MagicMock


def _bigquery_call_forbidden(*args, **kwargs):
    raise AssertionError("BigQuery must not be reached from the analysis lookup path")


class TestBigQueryUnreachableFromAnalysisPath:
    def _make_service(self):
        from backend.services.gnomad_local import GnomadLocalService
        svc = GnomadLocalService()
        svc._variant_count = 0  # skip PG (PERF-01 empty-table guard)
        svc._cache = MagicMock(is_loaded=False, has_tabix_files=False, _is_grch38=False)
        svc._try_bigquery_rsid = _bigquery_call_forbidden
        svc._try_bigquery_pos = _bigquery_call_forbidden
        return svc

    @pytest.mark.asyncio
    async def test_lookup_batch_never_reaches_bigquery(self):
        svc = self._make_service()
        result = await svc.lookup_batch(["rs1"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_lookup_batch_by_position_never_reaches_bigquery(self):
        svc = self._make_service()
        result = await svc.lookup_batch_by_position([("rs1", "1", 12345, "A", "G")])
        assert result == {}

    @pytest.mark.asyncio
    async def test_lookup_local_only_skips_bigquery_fallback(self):
        svc = self._make_service()
        result = await svc.lookup("rs1", local_only=True)
        assert result == {"found": False, "source": "gnomad", "rsid": "rs1"}


class TestCaddOnlyResultHasNoAf:
    def test_format_result_omits_af_key(self):
        from backend.services.gnomad_local import GnomadCacheService
        cache = GnomadCacheService()
        parsed = {
            "chrom": "1", "pos": 69869, "ref": "A", "alt": "G",
            "variant_type": "SNV", "gene": "OR4F5", "consequence": "missense_variant",
            "cadd_raw": 3.2, "cadd_phred": 25.0,
            "sift_cat": None, "sift_val": None,
            "polyphen_cat": None, "polyphen_val": None,
            "phylop_primate": None, "phylop_mammal": None, "phylop_vertebrate": None,
            "splice_ai_acc_gain": None, "splice_ai_acc_loss": None,
            "splice_ai_don_gain": None, "splice_ai_don_loss": None,
        }
        result = cache._format_result(parsed, rsid="rs1")
        assert "af" not in result
        assert result["cadd"]["phred"] == 25.0
