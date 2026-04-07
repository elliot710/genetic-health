"""Tests for Open Targets service caching logic."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.open_targets_service import OpenTargetsService


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_ot_data(gene: str, found: bool = True) -> dict:
    if not found:
        return {"found": False, "source": "open_targets", "gene_symbol": gene}
    return {
        "found": True,
        "source": "open_targets",
        "gene_symbol": gene,
        "ensembl_id": f"ENSG_{gene}",
        "associations": [{"disease_name": f"{gene}_disease", "score": 0.8}],
        "top_disease": f"{gene}_disease",
        "max_score": 0.8,
        "has_strong_genetic_evidence": True,
    }


class TestLookupGenesBatchCacheHit:
    @patch("backend.services.open_targets_service.OpenTargetsService._persist_to_cache", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._query_api_batch", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._load_from_cache", new_callable=AsyncMock)
    def test_all_cached(self, mock_load, mock_api, mock_persist):
        svc = OpenTargetsService()
        cached = {"BRCA1": _make_ot_data("BRCA1"), "TP53": _make_ot_data("TP53")}
        mock_load.return_value = cached

        result = _run(svc.lookup_genes_batch(["BRCA1", "TP53"]))

        assert result == cached
        mock_api.assert_not_called()
        mock_persist.assert_not_called()

    @patch("backend.services.open_targets_service.OpenTargetsService._persist_to_cache", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._query_api_batch", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._load_from_cache", new_callable=AsyncMock)
    def test_partial_cache(self, mock_load, mock_api, mock_persist):
        svc = OpenTargetsService()
        mock_load.return_value = {"BRCA1": _make_ot_data("BRCA1")}
        api_result = {"TP53": _make_ot_data("TP53")}
        mock_api.return_value = api_result

        result = _run(svc.lookup_genes_batch(["BRCA1", "TP53"]))

        assert "BRCA1" in result
        assert "TP53" in result
        mock_api.assert_called_once_with(["TP53"])
        mock_persist.assert_called_once_with(api_result)

    @patch("backend.services.open_targets_service.OpenTargetsService._persist_to_cache", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._query_api_batch", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._load_from_cache", new_callable=AsyncMock)
    def test_no_cache(self, mock_load, mock_api, mock_persist):
        svc = OpenTargetsService()
        mock_load.return_value = {}
        api_result = {"BRCA1": _make_ot_data("BRCA1")}
        mock_api.return_value = api_result

        result = _run(svc.lookup_genes_batch(["BRCA1"]))

        assert result == api_result
        mock_api.assert_called_once_with(["BRCA1"])
        mock_persist.assert_called_once_with(api_result)

    @patch("backend.services.open_targets_service.OpenTargetsService._persist_to_cache", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._query_api_batch", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.OpenTargetsService._load_from_cache", new_callable=AsyncMock)
    def test_empty_input(self, mock_load, mock_api, mock_persist):
        svc = OpenTargetsService()
        result = _run(svc.lookup_genes_batch([]))
        assert result == {}
        mock_load.assert_not_called()


class TestLoadFromCache:
    @patch("backend.services.open_targets_service.select")
    @patch("backend.services.open_targets_service.async_session_factory")
    def test_loads_cached_rows(self, mock_factory, mock_select):
        svc = OpenTargetsService()
        row = MagicMock()
        row.gene_symbol = "BRCA1"
        row.data = _make_ot_data("BRCA1")

        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        result = _run(svc._load_from_cache(["BRCA1"]))

        assert "BRCA1" in result
        assert result["BRCA1"]["found"] is True

    @patch("backend.services.open_targets_service.async_session_factory")
    def test_cache_read_failure_returns_empty(self, mock_factory):
        svc = OpenTargetsService()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("db error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        result = _run(svc._load_from_cache(["BRCA1"]))
        assert result == {}


class TestQueryApiBatch:
    @patch("backend.services.open_targets_service.OpenTargetsService.lookup_by_gene", new_callable=AsyncMock)
    @patch("backend.services.open_targets_service.asyncio.sleep", new_callable=AsyncMock)
    def test_queries_all_genes(self, mock_sleep, mock_lookup):
        svc = OpenTargetsService()
        mock_lookup.side_effect = [
            _make_ot_data("BRCA1"),
            _make_ot_data("TP53", found=False),
        ]

        result = _run(svc._query_api_batch(["BRCA1", "TP53"]))

        assert result["BRCA1"]["found"] is True
        assert result["TP53"]["found"] is False
        assert mock_lookup.call_count == 2


class TestPersistToCache:
    @patch("backend.services.open_targets_service.pg_insert")
    @patch("backend.services.open_targets_service.async_session_factory")
    def test_persists_results(self, mock_factory, mock_pg_insert):
        svc = OpenTargetsService()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_update.return_value = mock_stmt
        mock_pg_insert.return_value = mock_stmt

        results = {"BRCA1": _make_ot_data("BRCA1"), "TP53": _make_ot_data("TP53")}
        _run(svc._persist_to_cache(results))

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_persist_empty_noop(self):
        svc = OpenTargetsService()
        _run(svc._persist_to_cache({}))

    @patch("backend.services.open_targets_service.pg_insert")
    @patch("backend.services.open_targets_service.async_session_factory")
    def test_persist_failure_does_not_raise(self, mock_factory, mock_pg_insert):
        svc = OpenTargetsService()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("db error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_update.return_value = mock_stmt
        mock_pg_insert.return_value = mock_stmt

        _run(svc._persist_to_cache({"BRCA1": _make_ot_data("BRCA1")}))
