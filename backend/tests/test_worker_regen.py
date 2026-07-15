"""Worker regen-completion behavior."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import backend.worker as worker


def _session_ctx():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestRunOneRegenStatus:
    @pytest.mark.asyncio
    async def test_successful_regen_marks_analysis_completed(self):
        # regenerate_insights never touches analysis_status, so without this the
        # job sits at 'processing'/90% until a worker restart — and the dashboard
        # won't surface the freshly generated insights.
        captured: dict = {}

        def _capture_values(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        mock_update = MagicMock()
        mock_update.return_value.where.return_value.values.side_effect = _capture_values

        mock_service = MagicMock()
        mock_service.regenerate_insights = AsyncMock()

        with patch.object(worker, "ComprehensiveAnalysisService", return_value=mock_service), \
             patch.object(worker, "session_factory", return_value=_session_ctx()), \
             patch.object(worker, "update", mock_update), \
             patch.object(worker, "_flush_logs_to_db", new=AsyncMock()):
            await worker._run_one(7, 1, regen_only=True)

        mock_service.regenerate_insights.assert_awaited_once_with(7)
        assert captured.get("analysis_status") == "completed"
        assert captured.get("progress_percentage") == 100
        assert captured.get("current_step") == "completed"
