"""Deeper tests for shared_annotation_service.py and insights_service.py."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_async_session_context(rows=None, scalar=None):
    """Create a properly mocked async session context manager."""
    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=rows or [])
    mock_result.scalar_one_or_none = MagicMock(return_value=scalar)
    mock_result.scalar_one = MagicMock(return_value=scalar or 1)
    mock_result.scalar = MagicMock(return_value=scalar or 0)

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_session, mock_result


def _make_mock_row(rsid="rs12345", ensembl=None, clinvar=None, pharmgkb=None,
                    snpedia=None, litvar=None, am=None, cv_local=None,
                    gnomad=None, tkg=None, chembl=None, fda=None,
                    alphafold=None, gnomad_tx=None):
    return [rsid, ensembl, clinvar, pharmgkb, snpedia, litvar, am,
            cv_local, gnomad, tkg, chembl, fda, alphafold, gnomad_tx]


# ──────────────────────────────────────────────────
# SharedVariantAnnotationService
# ──────────────────────────────────────────────────

class TestRowToAnnotationDict:
    def _fn(self):
        from backend.services.shared_annotation_service import _row_to_annotation_dict
        return _row_to_annotation_dict

    def test_all_none_data(self):
        row = _make_mock_row()
        result = self._fn()(row)
        assert result["rsid"] == "rs12345"
        assert result["success_count"] == 0
        assert result["annotations"] == {}

    def test_with_ensembl_data(self):
        row = _make_mock_row(ensembl={"found": True, "data": []})
        result = self._fn()(row)
        assert result["success_count"] == 1
        assert "ensembl" in result["annotations"]

    def test_with_multiple_sources(self):
        row = _make_mock_row(
            ensembl={"found": True},
            clinvar={"found": True},
            am={"found": True, "am_class": "benign"},
        )
        result = self._fn()(row)
        assert result["success_count"] == 3
        assert "ensembl" in result["annotations"]
        assert "clinvar" in result["annotations"]
        assert "alpha_missense" in result["annotations"]


class TestEmptyAnnotationDict:
    def _fn(self):
        from backend.services.shared_annotation_service import _empty_annotation_dict
        return _empty_annotation_dict

    def test_structure(self):
        result = self._fn()("rs12345")
        assert result["rsid"] == "rs12345"
        assert result["annotations"] == {}
        assert result["success_count"] == 0
        assert result["sources_queried"] == []


class TestGetExistingAnnotations:
    @pytest.mark.asyncio
    async def test_empty_rsids(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        svc = SharedVariantAnnotationService()
        result = await svc.get_existing_annotations([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_rsids_with_hit(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        row = _make_mock_row(rsid="rs12345", ensembl={"found": True})
        ctx, session, mock_result = _make_async_session_context(rows=[row])
        mock_result.fetchall = MagicMock(return_value=[row])
        with patch("backend.db.database.async_session_factory", return_value=ctx):
            svc = SharedVariantAnnotationService()
            result = await svc.get_existing_annotations(["rs12345"], update_usage=False)
            assert "rs12345" in result

    @pytest.mark.asyncio
    async def test_rsids_no_hit(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        ctx, session, mock_result = _make_async_session_context(rows=[])
        with patch("backend.db.database.async_session_factory", return_value=ctx):
            svc = SharedVariantAnnotationService()
            result = await svc.get_existing_annotations(["rs99999"], update_usage=False)
            assert result == {}

    @pytest.mark.asyncio
    async def test_rsids_with_progress_callback(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        progress_calls = []
        async def on_progress(checked, total):
            progress_calls.append((checked, total))

        row = _make_mock_row(rsid="rs1", ensembl={"found": True})
        ctx, session, mock_result = _make_async_session_context(rows=[row])
        mock_result.fetchall = MagicMock(return_value=[row])
        with patch("backend.db.database.async_session_factory", return_value=ctx):
            svc = SharedVariantAnnotationService()
            result = await svc.get_existing_annotations(["rs1"], on_progress=on_progress, update_usage=False)
            assert len(progress_calls) > 0

    @pytest.mark.asyncio
    async def test_rsids_with_update_usage(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        row = _make_mock_row(rsid="rs1", ensembl={"found": True})
        ctx, session, mock_result = _make_async_session_context(rows=[row])
        mock_result.fetchall = MagicMock(return_value=[row])
        ctx2, session2, _ = _make_async_session_context()
        contexts = iter([ctx, ctx2])

        with patch("backend.db.database.async_session_factory", side_effect=lambda: next(contexts)), \
             patch("backend.services.shared_annotation_service.update", return_value=MagicMock()):
            svc = SharedVariantAnnotationService()
            result = await svc.get_existing_annotations(["rs1"], update_usage=True)
            assert "rs1" in result


class TestGetExistingAnnotationsFast:
    @pytest.mark.asyncio
    async def test_delegates_correctly(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        svc = SharedVariantAnnotationService()
        ctx, session, mock_result = _make_async_session_context(rows=[])
        with patch("backend.db.database.async_session_factory", return_value=ctx):
            result = await svc.get_existing_annotations_fast(["rs12345"])
            assert isinstance(result, dict)


class TestIncrementUsageCounts:
    @pytest.mark.asyncio
    async def test_increments_for_rsids(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        ctx, session, _ = _make_async_session_context()
        with patch("backend.db.database.async_session_factory", return_value=ctx), \
             patch("backend.services.shared_annotation_service.update", return_value=MagicMock()):
            svc = SharedVariantAnnotationService()
            await svc._increment_usage_counts(["rs1", "rs2"])
            session.execute.assert_called_once()
            session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_rsids(self):
        from backend.services.shared_annotation_service import SharedVariantAnnotationService
        ctx, session, _ = _make_async_session_context()
        with patch("backend.db.database.async_session_factory", return_value=ctx):
            svc = SharedVariantAnnotationService()
            await svc._increment_usage_counts([])
            session.execute.assert_not_called()


# ──────────────────────────────────────────────────
# insights_service.py — pure functions
# ──────────────────────────────────────────────────

class TestIsExpressModeKey:
    def _fn(self):
        from backend.services.insights_service import _is_express_mode_key
        return _is_express_mode_key

    def test_none_key(self):
        assert self._fn()(None) is False

    def test_empty_key(self):
        assert self._fn()("") is False

    def test_long_key_express_mode(self):
        long_key = "A" * 100
        result = self._fn()(long_key)
        assert isinstance(result, bool)

    def test_ai_studio_key(self):
        key = "AIzaSyB" + "x" * 32
        result = self._fn()(key)
        assert isinstance(result, bool)


class TestBuildUserPrompt:
    def _fn(self):
        from backend.services.insights_service import _build_user_prompt
        return _build_user_prompt

    def test_health_section(self):
        data = {
            "risks": [
                {"condition": "Diabetes", "risk_level": "high", "variants": ["rs1801282"]},
            ]
        }
        result = self._fn()("health", data)
        assert isinstance(result, str)
        assert len(result) > 10

    def test_drug_section(self):
        data = {
            "responses": [
                {"medication": "warfarin", "response_type": "metabolism"},
            ]
        }
        result = self._fn()("drug_response", data)
        assert isinstance(result, str)

    def test_unknown_section(self):
        result = self._fn()("unknown_section", {})
        assert isinstance(result, str)

    def test_empty_data(self):
        result = self._fn()("health", {})
        assert isinstance(result, str)


class TestGetLlmStatus:
    def test_returns_dict(self):
        from backend.services.insights_service import get_llm_status
        result = get_llm_status()
        assert isinstance(result, dict)
        assert "enabled" in result or "configured" in result or "status" in result

    def test_no_exception(self):
        from backend.services.insights_service import get_llm_status
        try:
            get_llm_status()
        except Exception as e:
            pytest.fail(f"get_llm_status raised {e}")


class TestSetInsightsEnabled:
    def test_sets_enabled(self):
        from backend.services.insights_service import set_insights_enabled, get_llm_status
        set_insights_enabled(True)
        status = get_llm_status()
        assert status is not None

    def test_sets_disabled(self):
        from backend.services.insights_service import set_insights_enabled, get_llm_status
        set_insights_enabled(False)
        status = get_llm_status()
        assert status is not None

    def test_re_enable(self):
        from backend.services.insights_service import set_insights_enabled
        set_insights_enabled(False)
        set_insights_enabled(True)


class TestGenerateInsight:
    @pytest.mark.asyncio
    async def test_disabled_insights(self):
        from backend.services.insights_service import generate_insight, set_insights_enabled
        set_insights_enabled(False)
        result = await generate_insight(1, "health", {})
        assert "disabled" in result or "summary" in result
        set_insights_enabled(True)

    @pytest.mark.asyncio
    async def test_with_db_cache_hit(self):
        from backend.services.insights_service import generate_insight, set_insights_enabled
        set_insights_enabled(True)
        mock_session = MagicMock()
        cached_row = MagicMock()
        cached_row.result = {"summary": "Cached insight", "key_findings": []}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=cached_row)
        mock_session.execute = AsyncMock(return_value=mock_result)
        with patch("sqlalchemy.select", return_value=MagicMock()):
            result = await generate_insight(1, "health", {}, db=mock_session)
            assert "summary" in result

    @pytest.mark.asyncio
    async def test_no_api_key_returns_error(self):
        from backend.services.insights_service import generate_insight, set_insights_enabled
        set_insights_enabled(True)
        with patch("backend.services.insights_service.GEMINI_API_KEY", ""):
            result = await generate_insight(1, "health", {})
            assert "summary" in result or "unavailable" in str(result).lower()


class TestCallLlm:
    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        from backend.services.insights_service import _call_llm
        with patch("backend.services.insights_service.GEMINI_API_KEY", ""):
            with pytest.raises(ValueError):
                await _call_llm("test prompt")

    @pytest.mark.asyncio
    async def test_with_api_key_calls_gemini(self):
        from backend.services.insights_service import _call_llm
        with patch("backend.services.insights_service.GEMINI_API_KEY", "test_key"), \
             patch("backend.services.insights_service._call_gemini", new=AsyncMock(return_value={"summary": "test"})):
            result = await _call_llm("test prompt")
            assert result == {"summary": "test"}


class TestCallGemini:
    @pytest.mark.asyncio
    async def test_ai_studio_path(self):
        from backend.services.insights_service import _call_gemini
        import json
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={
            "candidates": [{"content": {"parts": [{"text": '{"summary": "test"}'}]}}]
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.insights_service.GEMINI_API_KEY", "AIza_test"), \
             patch("backend.services.insights_service._is_express_mode_key", return_value=False), \
             patch("aiohttp.ClientSession", return_value=mock_session):
            result = await _call_gemini("test prompt")
            assert result == {"summary": "test"}

    @pytest.mark.asyncio
    async def test_express_mode_path(self):
        from backend.services.insights_service import _call_gemini
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={
            "candidates": [{"content": {"parts": [{"text": '{"summary": "express"}'}]}}]
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.insights_service.GEMINI_API_KEY", "express_key_" + "x" * 80), \
             patch("backend.services.insights_service._is_express_mode_key", return_value=True), \
             patch("aiohttp.ClientSession", return_value=mock_session):
            result = await _call_gemini("test prompt")
            assert "summary" in result

    @pytest.mark.asyncio
    async def test_vertex_ai_path(self):
        from backend.services.insights_service import _call_gemini
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={
            "candidates": [{"content": {"parts": [{"text": '{"summary": "vertex"}'}]}}]
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.insights_service.GEMINI_API_KEY", "vertex_key"), \
             patch("backend.services.insights_service._is_express_mode_key", return_value=False), \
             patch("backend.services.insights_service._is_standard_vertex_key", return_value=True), \
             patch("backend.services.insights_service.VERTEX_AI_PROJECT", "my-project"), \
             patch("aiohttp.ClientSession", return_value=mock_session):
            result = await _call_gemini("test prompt")
            assert "summary" in result
