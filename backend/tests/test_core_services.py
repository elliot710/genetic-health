"""Tests for core/config.py and core/exceptions.py."""
import os
import pytest
from unittest.mock import patch
import importlib.util as _ilu


def _load_real_config():
    spec = _ilu.spec_from_file_location(
        "_real_config",
        os.path.join(os.path.dirname(__file__), '..', 'core', 'config.py'),
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_real_config = _load_real_config()


class TestAPIConfiguration:
    def test_defaults(self):
        cfg = _real_config.APIConfiguration()
        assert cfg.base_delay == 0.1
        assert cfg.max_retries == 3
        assert cfg.timeout == 30.0
        assert cfg.batch_size == 50
        assert cfg.max_concurrent == 3

    def test_custom_values(self):
        cfg = _real_config.APIConfiguration(base_delay=0.5, max_retries=5, timeout=60.0)
        assert cfg.base_delay == 0.5
        assert cfg.max_retries == 5
        assert cfg.timeout == 60.0


class TestAnalysisConfiguration:
    def test_defaults(self):
        cfg = _real_config.AnalysisConfiguration()
        assert cfg.default_batch_size == 10
        assert cfg.max_variants_per_batch == 20
        assert cfg.processing_timeout == 3600
        assert cfg.enable_specialized_analysis is True
        assert cfg.enable_parallel_processing is True
        assert cfg.exclude_benign_from_panels is True

    def test_custom_values(self):
        cfg = _real_config.AnalysisConfiguration(default_batch_size=5, enable_specialized_analysis=False)
        assert cfg.default_batch_size == 5
        assert cfg.enable_specialized_analysis is False


class TestDatabaseConfiguration:
    def test_defaults(self):
        cfg = _real_config.DatabaseConfiguration()
        assert cfg.max_connections == 20
        assert cfg.connection_timeout == 30
        assert cfg.query_timeout == 60
        assert cfg.enable_connection_pooling is True


class TestSettings:
    def test_has_sections(self):
        s = _real_config.Settings()
        assert hasattr(s, 'api')
        assert hasattr(s, 'analysis')
        assert hasattr(s, 'database')

    def test_env_override_api_delay(self):
        with patch.dict(os.environ, {'API_BASE_DELAY': '0.5'}):
            s = _real_config.Settings()
            assert s.api.base_delay == 0.5

    def test_env_override_api_retries(self):
        with patch.dict(os.environ, {'API_MAX_RETRIES': '10'}):
            s = _real_config.Settings()
            assert s.api.max_retries == 10

    def test_env_override_api_timeout(self):
        with patch.dict(os.environ, {'API_TIMEOUT': '120.0'}):
            s = _real_config.Settings()
            assert s.api.timeout == 120.0

    def test_env_override_batch_size(self):
        with patch.dict(os.environ, {'API_BATCH_SIZE': '25'}):
            s = _real_config.Settings()
            assert s.api.batch_size == 25

    def test_env_override_max_concurrent(self):
        with patch.dict(os.environ, {'API_MAX_CONCURRENT': '5'}):
            s = _real_config.Settings()
            assert s.api.max_concurrent == 5

    def test_env_override_analysis_batch(self):
        with patch.dict(os.environ, {'ANALYSIS_BATCH_SIZE': '20'}):
            s = _real_config.Settings()
            assert s.analysis.default_batch_size == 20

    def test_env_override_max_variants_per_batch(self):
        with patch.dict(os.environ, {'ANALYSIS_MAX_VARIANTS_PER_BATCH': '50'}):
            s = _real_config.Settings()
            assert s.analysis.max_variants_per_batch == 50

    def test_env_override_timeout(self):
        with patch.dict(os.environ, {'ANALYSIS_TIMEOUT': '7200'}):
            s = _real_config.Settings()
            assert s.analysis.processing_timeout == 7200

    def test_env_override_specialized_false(self):
        with patch.dict(os.environ, {'ENABLE_SPECIALIZED_ANALYSIS': 'false'}):
            s = _real_config.Settings()
            assert s.analysis.enable_specialized_analysis is False

    def test_env_override_parallel_false(self):
        with patch.dict(os.environ, {'ENABLE_PARALLEL_PROCESSING': 'false'}):
            s = _real_config.Settings()
            assert s.analysis.enable_parallel_processing is False

    def test_env_override_exclude_benign_false(self):
        with patch.dict(os.environ, {'EXCLUDE_BENIGN_FROM_PANELS': 'false'}):
            s = _real_config.Settings()
            assert s.analysis.exclude_benign_from_panels is False

    def test_env_override_db_connections(self):
        with patch.dict(os.environ, {'DB_MAX_CONNECTIONS': '50'}):
            s = _real_config.Settings()
            assert s.database.max_connections == 50

    def test_env_override_db_connection_timeout(self):
        with patch.dict(os.environ, {'DB_CONNECTION_TIMEOUT': '60'}):
            s = _real_config.Settings()
            assert s.database.connection_timeout == 60

    def test_env_override_db_query_timeout(self):
        with patch.dict(os.environ, {'DB_QUERY_TIMEOUT': '120'}):
            s = _real_config.Settings()
            assert s.database.query_timeout == 120

    def test_global_settings_instance(self):
        s = _real_config.settings
        assert s is not None
        assert hasattr(s, 'api')


# ──────────────────────────────────────────────
# core/exceptions.py
# ──────────────────────────────────────────────

class TestExceptions:
    def test_genetic_analysis_exception_basic(self):
        from backend.core.exceptions import GeneticAnalysisException
        e = GeneticAnalysisException("test error")
        assert e.message == "test error"
        assert e.details == {}
        assert str(e) == "test error"

    def test_genetic_analysis_exception_with_details(self):
        from backend.core.exceptions import GeneticAnalysisException
        e = GeneticAnalysisException("test", details={"key": "val"})
        assert e.details == {"key": "val"}

    def test_analysis_not_found_exception(self):
        from backend.core.exceptions import AnalysisNotFoundException
        e = AnalysisNotFoundException("not found")
        assert isinstance(e, Exception)

    def test_variant_processing_exception(self):
        from backend.core.exceptions import VariantProcessingException
        e = VariantProcessingException("processing failed")
        assert e.message == "processing failed"

    def test_api_service_exception(self):
        from backend.core.exceptions import APIServiceException
        e = APIServiceException("api error")
        assert e.message == "api error"

    def test_api_rate_limit_exception(self):
        from backend.core.exceptions import APIRateLimitException, APIServiceException
        e = APIRateLimitException("rate limited")
        assert isinstance(e, APIServiceException)

    def test_api_connection_exception(self):
        from backend.core.exceptions import APIConnectionException, APIServiceException
        e = APIConnectionException("connection failed")
        assert isinstance(e, APIServiceException)

    def test_api_response_exception(self):
        from backend.core.exceptions import APIResponseException, APIServiceException
        e = APIResponseException("bad response")
        assert isinstance(e, APIServiceException)

    def test_database_exception(self):
        from backend.core.exceptions import DatabaseException, GeneticAnalysisException
        e = DatabaseException("db error")
        assert isinstance(e, GeneticAnalysisException)

    def test_analysis_timeout_exception(self):
        from backend.core.exceptions import AnalysisTimeoutException
        e = AnalysisTimeoutException("timed out")
        assert e.message == "timed out"

    def test_invalid_variant_exception(self):
        from backend.core.exceptions import InvalidVariantException
        e = InvalidVariantException("bad variant")
        assert e.message == "bad variant"

    def test_specialized_analysis_exception(self):
        from backend.core.exceptions import SpecializedAnalysisException
        e = SpecializedAnalysisException("specialized failed")
        assert e.message == "specialized failed"

    def test_exception_is_catchable_as_base(self):
        from backend.core.exceptions import AnalysisNotFoundException, GeneticAnalysisException
        with pytest.raises(GeneticAnalysisException):
            raise AnalysisNotFoundException("not found")

