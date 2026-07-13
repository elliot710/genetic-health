from pathlib import Path

from backend.api.admin_routes import _is_source_stale, _source_cache_file_size


class TestIsSourceStale:
    def test_enabled_source_with_rows_but_zero_found_is_stale(self):
        # The honest found-rate exposes an empty build: annotated>0 but found=0.
        assert _is_source_stale(True, found_count=0, annotated_count=500, cache_file_bytes=None) is True

    def test_tiny_cache_file_is_stale(self):
        assert _is_source_stale(True, found_count=10, annotated_count=10, cache_file_bytes=180_000) is True

    def test_healthy_source_is_not_stale(self):
        assert _is_source_stale(True, found_count=480, annotated_count=500, cache_file_bytes=None) is False

    def test_disabled_source_with_zero_found_is_not_flagged(self):
        assert _is_source_stale(False, found_count=0, annotated_count=500, cache_file_bytes=None) is False

    def test_large_cache_file_is_not_stale(self):
        assert _is_source_stale(True, found_count=5, annotated_count=5, cache_file_bytes=50_000_000) is False


class TestSourceCacheFileSize:
    def test_unknown_source_returns_none(self):
        assert _source_cache_file_size('clinvar') is None

    def test_gnomad_absent_cache_reports_none_not_error(self, monkeypatch):
        import backend.services.gnomad_local as gnomad_local
        monkeypatch.setattr(gnomad_local, '_SQLITE_FILE', Path('/nonexistent/gnomad_cache.db'))
        assert _source_cache_file_size('gnomad') is None
