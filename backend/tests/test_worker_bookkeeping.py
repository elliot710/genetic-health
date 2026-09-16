"""Worker failure-bookkeeping paths must stay observable.

These guard the paths that record *that a job failed*. If the recording write
itself fails and the error is swallowed, the job is stranded in its previous
state with nothing in the logs explaining why.
"""
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import backend.worker as worker


def _failing_session_ctx():
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("connection lost"))
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestRunJobBookkeeping:
    @pytest.mark.asyncio
    async def test_status_write_failure_is_logged(self, caplog):
        with patch.object(worker, "_execute_job", new=AsyncMock(side_effect=ValueError("job blew up"))), \
             patch.object(worker, "session_factory", return_value=_failing_session_ctx()), \
             caplog.at_level(logging.ERROR, logger="worker"):
            await worker._run_job(42, "some_job", {})

        messages = [r.getMessage() for r in caplog.records]
        assert any("connection lost" in m for m in messages)

    @pytest.mark.asyncio
    async def test_status_write_failure_does_not_propagate(self):
        with patch.object(worker, "_execute_job", new=AsyncMock(side_effect=ValueError("job blew up"))), \
             patch.object(worker, "session_factory", return_value=_failing_session_ctx()):
            await worker._run_job(42, "some_job", {})


class TestRunOneBookkeeping:
    @pytest.mark.asyncio
    async def test_analysis_failure_write_failure_is_logged(self, caplog):
        mock_service = MagicMock()
        mock_service.regenerate_insights = AsyncMock(side_effect=ValueError("regen blew up"))

        with patch.object(worker, "ComprehensiveAnalysisService", return_value=mock_service), \
             patch.object(worker, "session_factory", return_value=_failing_session_ctx()), \
             patch.object(worker, "_flush_logs_to_db", new=AsyncMock()), \
             caplog.at_level(logging.ERROR, logger="worker"):
            await worker._run_one(7, 1, regen_only=True)

        messages = [r.getMessage() for r in caplog.records]
        assert any("connection lost" in m for m in messages)
