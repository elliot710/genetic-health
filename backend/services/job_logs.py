"""
In-memory per-job log collector.
Captures log entries from analysis processing and stores them per analysis_id.
Uses contextvars for proper async task tracking in asyncio.
"""
import contextvars
import logging
import re
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Dict, List, Optional

# ContextVar tracks the active analysis_id per asyncio Task
_current_analysis_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    '_current_analysis_id', default=None
)


class JobLogCollector:
    """Stores recent log entries per analysis job in memory."""

    _instance: Optional['JobLogCollector'] = None

    def __init__(self, max_lines_per_job: int = 500, max_jobs: int = 50):
        self._logs: Dict[int, deque] = {}
        self._max_lines = max_lines_per_job
        self._max_jobs = max_jobs
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'JobLogCollector':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_active_job(self, analysis_id: int):
        """Set the active job for the current async task context."""
        _current_analysis_id.set(analysis_id)
        with self._lock:
            if analysis_id not in self._logs:
                self._logs[analysis_id] = deque(maxlen=self._max_lines)
                # Evict oldest jobs if we exceed max
                if len(self._logs) > self._max_jobs:
                    oldest = next(iter(self._logs))
                    del self._logs[oldest]

    def clear_active_job(self):
        _current_analysis_id.set(None)

    @staticmethod
    def get_active_job() -> Optional[int]:
        return _current_analysis_id.get(None)

    def add(self, analysis_id: int, level: str, message: str):
        """Add a log entry for a specific job."""
        with self._lock:
            if analysis_id not in self._logs:
                self._logs[analysis_id] = deque(maxlen=self._max_lines)
            self._logs[analysis_id].append({
                "ts": datetime.now(UTC).strftime("%H:%M:%S"),
                "level": level,
                "msg": message,
            })

    def get_logs(self, analysis_id: int, last_n: Optional[int] = None) -> List[dict]:
        """Get log entries for a job."""
        with self._lock:
            entries = self._logs.get(analysis_id, deque())
            items = list(entries)
        if last_n:
            items = items[-last_n:]
        return items

    def clear(self, analysis_id: int):
        with self._lock:
            self._logs.pop(analysis_id, None)

    def get_all_job_ids(self) -> List[int]:
        with self._lock:
            return list(self._logs.keys())


_ANALYSIS_ID_RE = re.compile(r'[Aa]nalysis\s+(\d+)')


class JobLogHandler(logging.Handler):
    """
    Logging handler that routes log records to the JobLogCollector.
    Uses contextvars to identify which analysis task emitted the log.
    Falls back to regex extraction from the message text.
    """

    def __init__(self):
        super().__init__()
        self.collector = JobLogCollector.get_instance()

    def emit(self, record: logging.LogRecord):
        analysis_id = _current_analysis_id.get(None)
        if analysis_id is None:
            m = _ANALYSIS_ID_RE.search(record.getMessage())
            if m:
                analysis_id = int(m.group(1))
        if analysis_id is not None:
            self.collector.add(
                analysis_id,
                record.levelname,
                record.getMessage()
            )
