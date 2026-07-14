import pytest
from backend.api.admin import _extract_am_coords
from backend.services.analysis_service import ComprehensiveAnalysisService


class TestExtractAmCoords:
    def _make_ensembl(self, chrom, pos, allele_str, found=True):
        return {
            "found": found,
            "data": [{"seq_region_name": chrom, "start": pos, "allele_string": allele_str}],
        }

    def test_returns_none_for_none_input(self):
        assert _extract_am_coords(None) is None

    def test_returns_none_when_not_found(self):
        data = self._make_ensembl("1", 100, "A/T", found=False)
        assert _extract_am_coords(data) is None

    def test_returns_coords_for_snp(self):
        data = self._make_ensembl("1", 100, "A/T")
        result = _extract_am_coords(data)
        assert result == ("1", 100, "A", "T")

    def test_returns_none_for_non_snp_alleles(self):
        data = self._make_ensembl("1", 100, "AT/T")
        assert _extract_am_coords(data) is None

    def test_returns_none_when_no_data_key(self):
        assert _extract_am_coords({"found": True}) is None

    def test_uses_first_element_of_data_list(self):
        data = {
            "found": True,
            "data": [
                {"seq_region_name": "2", "start": 200, "allele_string": "G/C"},
                {"seq_region_name": "1", "start": 100, "allele_string": "A/T"},
            ],
        }
        result = _extract_am_coords(data)
        assert result == ("2", 200, "G", "C")

    def test_handles_dict_data_not_list(self):
        data = {"found": True, "data": {"seq_region_name": "X", "start": 50, "allele_string": "C/G"}}
        result = _extract_am_coords(data)
        assert result == ("X", 50, "C", "G")

    def test_returns_none_when_allele_string_missing(self):
        data = {"found": True, "data": [{"seq_region_name": "1", "start": 100}]}
        assert _extract_am_coords(data) is None


class TestComprehensiveAnalysisServiceConstants:
    def test_completed_phases_is_class_attribute(self):
        assert hasattr(ComprehensiveAnalysisService, '_COMPLETED_PHASES')

    def test_completed_phases_keys(self):
        phases = ComprehensiveAnalysisService._COMPLETED_PHASES
        assert 'initializing' in phases
        assert 'annotation_complete' in phases
        assert 'completed' in phases

    def test_annotating_variants_restarts_phase_2(self):
        phases = ComprehensiveAnalysisService._COMPLETED_PHASES
        assert phases['annotating_variants'] == 0

    def test_annotation_complete_skips_to_phase_3(self):
        phases = ComprehensiveAnalysisService._COMPLETED_PHASES
        assert phases['annotation_complete'] == 1

    def test_completed_is_max_phase(self):
        phases = ComprehensiveAnalysisService._COMPLETED_PHASES
        assert phases['completed'] == max(phases.values())


class TestUpdateDb:
    @pytest.mark.asyncio
    async def test_update_progress_delegates(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from types import SimpleNamespace

        svc = ComprehensiveAnalysisService(user_id=1)

        progress = SimpleNamespace(
            progress_percentage=50,
            processed_variants=100,
            current_step="annotating",
            status="in_progress",
            estimated_completion=None,
        )

        with patch.object(svc, '_update_db', new_callable=AsyncMock) as mock_update:
            await svc._update_progress(42, progress)
            mock_update.assert_called_once_with(
                42,
                progress_percentage=50,
                processed_variants=100,
                current_step="annotating",
                analysis_status="in_progress",
                estimated_completion=None,
                guard_paused=True,
            )

    @pytest.mark.asyncio
    async def test_update_analysis_status_delegates(self):
        from unittest.mock import AsyncMock, patch

        svc = ComprehensiveAnalysisService(user_id=1)

        with patch.object(svc, '_update_db', new_callable=AsyncMock) as mock_update:
            await svc._update_analysis_status(99, "completed", "done")
            mock_update.assert_called_once_with(
                99, analysis_status="completed", current_step="done"
            )


    @pytest.mark.asyncio
    async def test_update_progress_completed_sets_completed_at(self):
        from unittest.mock import AsyncMock, patch
        from types import SimpleNamespace

        svc = ComprehensiveAnalysisService(user_id=1)
        progress = SimpleNamespace(
            progress_percentage=100,
            processed_variants=500,
            current_step="completed",
            status="completed",
            estimated_completion=None,
        )

        with patch.object(svc, '_update_db', new_callable=AsyncMock) as mock_update:
            await svc._update_progress(42, progress, force_percentage=100, completed=True)
            _, kwargs = mock_update.call_args
            assert 'completed_at' in kwargs

    @pytest.mark.asyncio
    async def test_update_progress_not_completed_omits_completed_at(self):
        from unittest.mock import AsyncMock, patch
        from types import SimpleNamespace

        svc = ComprehensiveAnalysisService(user_id=1)
        progress = SimpleNamespace(
            progress_percentage=50,
            processed_variants=100,
            current_step="annotating",
            status="processing",
            estimated_completion=None,
        )

        with patch.object(svc, '_update_db', new_callable=AsyncMock) as mock_update:
            await svc._update_progress(42, progress)
            _, kwargs = mock_update.call_args
            assert 'completed_at' not in kwargs

    @pytest.mark.asyncio
    async def test_update_analysis_status_failed_omits_completed_at(self):
        from unittest.mock import AsyncMock, patch

        svc = ComprehensiveAnalysisService(user_id=1)

        with patch.object(svc, '_update_db', new_callable=AsyncMock) as mock_update:
            await svc._update_analysis_status(99, "failed", "Failed: boom")
            _, kwargs = mock_update.call_args
            assert 'completed_at' not in kwargs


class TestFinalizeAnalysisCompletion:
    @pytest.mark.asyncio
    async def test_finalize_analysis_marks_completed_at(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from types import SimpleNamespace

        svc = ComprehensiveAnalysisService(user_id=1)
        progress = SimpleNamespace(
            current_step="", status="", processed_variants=0, phase=0, phase_progress=0.0,
        )
        analysis = MagicMock(user_id=1)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.object(svc, '_update_progress', new_callable=AsyncMock) as mock_update_progress, \
             patch("backend.db.database.async_session_factory", return_value=mock_session):
            await svc._finalize_analysis(42, analysis, variants=[1, 2, 3], progress=progress)

        mock_update_progress.assert_called_once_with(
            42, progress, force_percentage=100, completed=True
        )


class TestAnalysisCoverage:
    def test_averages_variant_and_category_rates(self):
        from backend.api.analysis_routes import _analysis_coverage
        status = {"generators_total": 14, "generators_succeeded": 7}
        # variant rate 1.0, category rate 0.5 → mean 0.75 → 75
        assert _analysis_coverage(status, 100, 100)["score"] == 75

    def test_falls_back_to_variant_rate_when_no_insight_status(self):
        from backend.api.analysis_routes import _analysis_coverage
        assert _analysis_coverage(None, 80, 100)["score"] == 80

    def test_score_none_when_no_signal(self):
        from backend.api.analysis_routes import _analysis_coverage
        assert _analysis_coverage(None, 0, 0)["score"] is None
