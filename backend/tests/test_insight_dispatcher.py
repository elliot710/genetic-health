import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.analysis_service import AnalysisProgress
from backend.services.insight_dispatcher import (
    generate_comprehensive_insights,
    _build_insight_status,
)


def _mock_session_ctx():
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_progress():
    return AnalysisProgress(
        total_variants=0, processed_variants=0, annotated_variants=0,
        new_annotations=0, reused_annotations=0,
        current_step="generating_insights", status="processing",
    )


class TestGeneratorFaultIsolation:
    @pytest.mark.asyncio
    async def test_generator_exception_is_logged_with_name_and_others_still_run(self, caplog):
        async def ok_generator(ctx):
            return 3

        async def boom_generator(ctx):
            raise RuntimeError("synthetic generator failure")

        fake_generators = [("boom_panel", boom_generator), ("ok_panel", ok_generator)]

        with patch("backend.services.insight_dispatcher.async_session_factory",
                   return_value=_mock_session_ctx()), \
             patch("backend.services.insight_dispatcher.delete"), \
             patch("backend.services.insight_dispatcher.ALL_GENERATORS", fake_generators), \
             patch("backend.services.insight_dispatcher.build_variant_profiles",
                   AsyncMock(return_value={})), \
             caplog.at_level(logging.ERROR, logger="backend.services.insight_dispatcher"):
            total_insights = await generate_comprehensive_insights(
                variants=[], annotation_results={}, analysis_id=1,
                rsid_gene_map={}, registry={}, progress=_make_progress(),
            )

        # ok_panel's insights are not dropped just because boom_panel failed
        assert total_insights == 3
        assert any("boom_panel" in r.message for r in caplog.records)


class TestBuildInsightStatus:
    def _statuses(self):
        return {
            "health_risks": {"status": "generated", "count": 5},
            "ancestry_results": {"status": "empty", "count": 0},
            "drug_responses": {"status": "failed", "count": 0},
        }

    def test_failed_list_records_failed_generator(self):
        status = _build_insight_status(self._statuses(), ["drug_responses"], 5, 14)
        assert status["failed"] == ["drug_responses"]

    def test_generated_list_excludes_empty_and_failed(self):
        status = _build_insight_status(self._statuses(), ["drug_responses"], 5, 14)
        assert status["generated"] == ["health_risks"]

    def test_generators_succeeded_counts_non_failed(self):
        status = _build_insight_status(self._statuses(), ["drug_responses"], 5, 14)
        assert status["generators_succeeded"] == 2


class TestTargetedRegeneration:
    def _fake_generators(self, calls):
        async def gen_health(ctx):
            calls.append("health_risks")
            return 1

        async def gen_drug(ctx):
            calls.append("drug_responses")
            return 2

        return [("health_risks", gen_health), ("drug_responses", gen_drug)]

    async def _run(self, only_categories):
        calls: list[str] = []
        with patch("backend.services.insight_dispatcher.async_session_factory",
                   return_value=_mock_session_ctx()), \
             patch("backend.services.insight_dispatcher.delete"), \
             patch("backend.services.insight_dispatcher.ALL_GENERATORS",
                   self._fake_generators(calls)), \
             patch("backend.services.insight_dispatcher.build_variant_profiles",
                   AsyncMock(return_value={})):
            total = await generate_comprehensive_insights(
                variants=[], annotation_results={}, analysis_id=1,
                rsid_gene_map={}, registry={}, progress=_make_progress(),
                only_categories=only_categories,
            )
        return calls, total

    @pytest.mark.asyncio
    async def test_only_selected_generator_runs(self):
        calls, _ = await self._run(only_categories=["health_risks"])
        assert calls == ["health_risks"]

    @pytest.mark.asyncio
    async def test_total_reflects_only_selected(self):
        _, total = await self._run(only_categories=["health_risks"])
        assert total == 1

    @pytest.mark.asyncio
    async def test_none_runs_all_generators(self):
        calls, _ = await self._run(only_categories=None)
        assert calls == ["health_risks", "drug_responses"]
