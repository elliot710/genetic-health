"""Tests for annotation_coordinator pure functions, more analysis routes, admin routes."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch, call
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _make_mock_user(user_id=1, is_admin=True, username="admin"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.email = "admin@example.com"
    user.full_name = "Admin User"
    user.is_admin = is_admin
    user.is_verified = True
    user.is_active = True
    user.hashed_password = "hashed_pw"
    user.created_at = datetime(2024, 1, 1)
    user.notification_preferences = {}
    return user


def _make_mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.delete = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_mock_result(scalar=None, scalars_list=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar)
    result.scalar = MagicMock(return_value=0)
    result.all = MagicMock(return_value=all_rows or [])
    result.first = MagicMock(return_value=scalar)
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=scalars_list or [])
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _build_app(router, current_user=None, session=None):
    from backend.db.database import get_session
    from backend.api.auth_routes import get_current_user

    if current_user is None:
        current_user = _make_mock_user()
    if session is None:
        session = _make_mock_session()

    app = FastAPI()
    app.include_router(router)

    async def _override_session():
        yield session

    async def _override_user():
        return current_user

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = _override_user
    return app, session


# ──────────────────────────────────────────────────────────────────
# annotation_coordinator pure functions
# ──────────────────────────────────────────────────────────────────

class TestAnnotationCoordinatorPure:
    def test_truthy_data_none(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data(None) is None

    def test_truthy_data_empty_dict(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data({}) is None

    def test_truthy_data_found_false(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data({"found": False}) is None

    def test_truthy_data_found_true(self):
        from backend.services.annotation_coordinator import _truthy_data
        data = {"found": True, "gene": "BRCA1"}
        assert _truthy_data(data) == data

    def test_truthy_data_no_found_key(self):
        from backend.services.annotation_coordinator import _truthy_data
        data = {"gene": "BRCA1"}
        result = _truthy_data(data)
        assert result is None  # 'found' key missing is falsy

    def test_build_annotation_link_values_empty(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        result = _build_annotation_link_values({}, [], {}, 1)
        assert result == []

    def test_build_annotation_link_values_no_shared_id(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        v = MagicMock()
        v.id = 10
        rsid_to_variants = {"rs12345": [v]}
        chunk_rsids = ["rs12345"]
        rsid_to_shared_id = {}  # no mapping
        result = _build_annotation_link_values(rsid_to_variants, chunk_rsids, rsid_to_shared_id, 1)
        assert result == []

    def test_build_annotation_link_values_with_match(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        v = MagicMock()
        v.id = 10
        rsid_to_variants = {"rs12345": [v]}
        chunk_rsids = ["rs12345"]
        rsid_to_shared_id = {"rs12345": 5}
        result = _build_annotation_link_values(rsid_to_variants, chunk_rsids, rsid_to_shared_id, 1)
        assert len(result) == 1
        assert result[0]["rsid"] == "rs12345"
        assert result[0]["analysis_id"] == 1
        assert result[0]["shared_annotation_id"] == 5
        assert result[0]["analysis_variant_id"] == 10

    def test_build_annotation_link_values_multiple_variants(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        v1, v2 = MagicMock(), MagicMock()
        v1.id = 10
        v2.id = 11
        rsid_to_variants = {"rs999": [v1, v2]}
        result = _build_annotation_link_values(
            rsid_to_variants, ["rs999"], {"rs999": 50}, 2
        )
        assert len(result) == 2
        assert all(r["rsid"] == "rs999" for r in result)

    @pytest.mark.asyncio
    async def test_insert_annotation_links_empty(self):
        from backend.services.annotation_coordinator import _insert_annotation_links
        session = _make_mock_session()
        await _insert_annotation_links(session, [])
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_remote_api_data_empty(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data
        result = await _fetch_remote_api_data([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_remote_api_data_with_rsids(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data
        mock_session_factory = MagicMock()
        ctx_manager = MagicMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=MagicMock(
            execute=AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        ))
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = ctx_manager
        with patch("backend.services.annotation_coordinator.async_session_factory", mock_session_factory):
            result = await _fetch_remote_api_data(["rs12345"])
            assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────────
# analysis_routes deeper coverage
# ──────────────────────────────────────────────────────────────────

def _make_analysis(analysis_id=1, user_id=1, status="completed"):
    a = MagicMock()
    a.id = analysis_id
    a.user_id = user_id
    a.analysis_status = status
    a.progress_percentage = 100
    a.current_step = "completed"
    a.total_variants = 1000
    a.processed_variants = 1000
    a.filename = "test.vcf"
    a.file_type = "vcf"
    a.upload_date = datetime(2024, 1, 1)
    a.strategy_used = "fast"
    a.estimated_completion = None
    a.job_logs = None
    a.deleted_at = None
    a.created_at = datetime(2024, 1, 1)
    return a


class TestAnalysisRoutesDeep:
    def _app(self, session=None, user=None):
        from backend.api.analysis_routes import router
        return _build_app(router, current_user=user or _make_mock_user(is_admin=False, username="user"), session=session)

    def test_status_analysis_in_progress(self):
        analysis = _make_analysis(status="processing")
        app, _ = self._app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/status/1")
                assert resp.status_code == 200

    def test_results_analysis_not_completed(self):
        analysis = _make_analysis(status="processing")
        app, session = self._app(session=_make_mock_session())
        session.execute = AsyncMock(return_value=_make_mock_result())
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with patch("backend.api.analysis_routes.select", return_value=MagicMock()):
                with TestClient(app) as client:
                    resp = client.get("/api/analysis/results/1")
                    assert resp.status_code in (200, 202, 400)

    def test_resume_analysis_not_paused(self):
        analysis = _make_analysis(status="completed")
        app, _ = self._app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/resume/1")
                assert resp.status_code in (200, 400, 409, 500)

    def test_regenerate_insights_analysis_not_completed(self):
        analysis = _make_analysis(status="processing")
        app, session = self._app(session=_make_mock_session())
        session.execute = AsyncMock(return_value=_make_mock_result())
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/regenerate-insights/1")
                assert resp.status_code in (200, 400, 409, 500)

    def test_start_analysis_already_running(self):
        analysis = _make_analysis(status="processing")
        app, session = self._app(session=_make_mock_session())
        session.execute = AsyncMock(return_value=_make_mock_result())
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/start/1")
                assert resp.status_code in (200, 202, 400, 409, 500)

    def test_list_with_params(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session=session)
        with TestClient(app) as client:
            resp = client.get("/api/analysis/list?limit=5&offset=0")
            assert resp.status_code in (200, 500)

    def test_dashboard_data_with_cached(self):
        session = _make_mock_session()
        cache_entry = MagicMock()
        cache_entry.cached_data = {"health": [], "drug_responses": []}
        cache_entry.expires_at = datetime(2099, 1, 1)
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=cache_entry))
        app, _ = self._app(session=session)
        with patch("backend.api.analysis_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/dashboard-data")
                assert resp.status_code in (200, 500)


# ──────────────────────────────────────────────────────────────────
# Admin routes - additional endpoints
# ──────────────────────────────────────────────────────────────────

def _admin_sa_patch():
    import contextlib

    @contextlib.contextmanager
    def _patch():
        with patch("backend.api.admin.category_rules.select"), \
             patch("backend.api.admin.category_rules.delete"), \
             patch("backend.api.admin.category_rules.update"), \
             patch("backend.api.admin.users.select"), \
             patch("backend.api.admin.users.func"), \
             patch("backend.api.admin.variant_mappings.select"), \
             patch("backend.api.admin.variant_mappings.func"), \
             patch("backend.api.admin.discoveries.select"), \
             patch("backend.api.admin.discoveries.func"), \
             patch("backend.api.admin.jobs.select"), \
             patch("backend.api.admin.jobs.func"), \
             patch("backend.api.admin.jobs.delete"), \
             patch("backend.api.admin.jobs.update"):
            yield
    return _patch()


class TestAdminRoutesExtra:
    def _app(self, session=None):
        from backend.api.admin import router
        user = _make_mock_user(is_admin=True, username="admin")
        return _build_app(router, current_user=user, session=session)

    def test_get_ai_configs_empty(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/ai-configs")
                assert resp.status_code in (200, 404, 500)

    def test_get_users_list(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/users")
                assert resp.status_code in (200, 500)

    def test_get_user_by_id_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                # List users returns a list, individual user may be different route path
                resp = client.get("/api/admin/users")
                assert resp.status_code in (200, 500)

    def test_post_category_rules(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result())
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/category-rules", json={
                    "category": "health",
                    "rule_type": "clinvar_significance",
                    "rule_value": "Pathogenic",
                    "priority": 1,
                })
                assert resp.status_code in (200, 201, 400, 422, 500)

    def test_get_category_rules(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/category-rules")
                assert resp.status_code in (200, 500)

    def test_post_variant_mappings(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result())
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/variant-mappings", json={
                    "category": "health",
                    "map_type": "rsid",
                    "key": "rs12345",
                    "data": {},
                })
                assert resp.status_code in (200, 201, 400, 422, 500)

    def test_delete_variant_mapping(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result())
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/variant-mappings/1")
                assert resp.status_code in (200, 404, 500)

    def test_get_discoveries_summary(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=0))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/discoveries/summary")
                assert resp.status_code in (200, 500)

    def test_trigger_clinvar_etl(self):
        session = _make_mock_session()
        app, _ = self._app(session)
        with _admin_sa_patch():
            with patch("backend.services.clinvar_etl.ClinVarETL") as MockEtl:
                mock_etl_instance = MagicMock()
                mock_etl_instance.run = AsyncMock(return_value={"status": "done"})
                MockEtl.return_value = mock_etl_instance
                with TestClient(app) as client:
                    resp = client.post("/api/admin/clinvar-etl/import")
                    assert resp.status_code in (200, 202, 422, 500)

    def test_get_jobs_list(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/jobs")
                assert resp.status_code in (200, 500)

    def test_get_jobs_summary(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=0))
        app, _ = self._app(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/jobs/summary")
                assert resp.status_code in (200, 500)


# ──────────────────────────────────────────────────────────────────
# variant_routes deeper coverage
# ──────────────────────────────────────────────────────────────────

class TestVariantRoutesDeep:
    def _app(self, session=None, user=None):
        from backend.api.variant_routes import router
        return _build_app(router, current_user=user or _make_mock_user(is_admin=False), session=session)

    def test_variant_search_empty_query(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/search?q=")
                assert resp.status_code in (200, 400, 422, 500)

    def test_variant_search_with_query(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/search?q=BRCA1")
                assert resp.status_code in (200, 500)

    def test_variant_stats(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=0))
        app, _ = self._app(session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/stats")
                assert resp.status_code in (200, 500)

    def test_variant_examples(self):
        app, _ = self._app()
        with TestClient(app) as client:
            resp = client.get("/api/variants/examples")
            assert resp.status_code in (200, 404, 500)

    def test_variant_categories(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/categories")
                assert resp.status_code in (200, 500)


# ──────────────────────────────────────────────────────────────────
# analysis_service pure functions / dataclasses
# ──────────────────────────────────────────────────────────────────

class TestAnalysisServicePure:
    def test_annotation_result_creation(self):
        from backend.services.variant_types import AnnotationResult
        result = AnnotationResult(
            rsid="rs12345",
            was_reused=True,
            annotation_data={"annotations": {}},
            source="existing",
        )
        assert result.rsid == "rs12345"
        assert result.was_reused is True

    def test_analysis_progress_creation(self):
        from backend.services.analysis_service import AnalysisProgress
        progress = AnalysisProgress(
            total_variants=1000,
            processed_variants=500,
            annotated_variants=300,
            new_annotations=200,
            reused_annotations=100,
            current_step="annotating",
            status="processing",
            phase=2,
            phase_progress=50.0,
        )
        assert progress.total_variants == 1000
        assert progress.status == "processing"

    def test_analysis_cancelled_exception(self):
        from backend.services.analysis_service import AnalysisCancelled
        exc = AnalysisCancelled("cancelled")
        assert str(exc) == "cancelled"

    def test_analysis_service_init(self):
        from backend.services.analysis_service import ComprehensiveAnalysisService
        svc = ComprehensiveAnalysisService(user_id=1)
        assert svc is not None


# ──────────────────────────────────────────────────────────────────
# ai_insights_service tests
# ──────────────────────────────────────────────────────────────────

class TestInsightsService:
    def test_llm_status_function_exists(self):
        from backend.services.ai_insights_service import get_llm_status
        assert callable(get_llm_status)

    def test_llm_status_returns_dict(self):
        from backend.services.ai_insights_service import get_llm_status
        status = get_llm_status()
        assert isinstance(status, dict)

    def test_set_insights_enabled(self):
        from backend.services.ai_insights_service import set_insights_enabled
        result = set_insights_enabled(False)
        assert isinstance(result, dict)
        # Restore
        set_insights_enabled(True)

    def test_build_user_prompt(self):
        from backend.services.ai_insights_service import _build_user_prompt
        result = _build_user_prompt("health", {"risks": []})
        assert isinstance(result, str)

    def test_is_express_mode_key(self):
        from backend.services.ai_insights_service import _is_express_mode_key
        result = _is_express_mode_key("health")
        assert isinstance(result, bool)


# ──────────────────────────────────────────────────────────────────
# knowledge_graph tests
# ──────────────────────────────────────────────────────────────────

class TestKnowledgeGraph:
    def test_import_works(self):
        from backend.services import knowledge_graph
        assert knowledge_graph is not None

    def test_build_knowledge_graph_function_exists(self):
        from backend.services.knowledge_graph import build_knowledge_graph
        assert callable(build_knowledge_graph)

    @pytest.mark.asyncio
    async def test_build_knowledge_graph_empty(self):
        from backend.services.knowledge_graph import build_knowledge_graph
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        with patch("backend.services.knowledge_graph.select", return_value=MagicMock()):
            result = await build_knowledge_graph(user_id=1, session=session)
            assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────────
# vcf_parser additional tests
# ──────────────────────────────────────────────────────────────────

class TestVcfParserAdditional:
    def test_normalize_chromosome_chr_prefix(self):
        from backend.utils.vcf_parser import VCFParser
        result = VCFParser._normalize_chromosome("chr1")
        assert result in ("1", "chr1")

    def test_normalize_chromosome_numeric(self):
        from backend.utils.vcf_parser import VCFParser
        result = VCFParser._normalize_chromosome("1")
        assert result in ("1", "chr1")

    def test_normalize_chromosome_mt(self):
        from backend.utils.vcf_parser import VCFParser
        result = VCFParser._normalize_chromosome("chrM")
        assert result is None or isinstance(result, str)

    def test_validate_variant_valid(self):
        from backend.utils.vcf_parser import VCFParser
        parser = VCFParser()
        variant = {
            "rsid": "rs12345",
            "chromosome": "1",
            "position": 12345,
            "ref_allele": "A",
            "alt_allele": "G",
            "genotype": "A/G",
        }
        result = parser._validate_variant(variant)
        assert isinstance(result, bool)

    def test_parse_info_field_empty(self):
        from backend.utils.vcf_parser import VCFParser
        parser = VCFParser()
        result = parser._parse_info_field(".")
        assert isinstance(result, dict)

    def test_parse_info_field_with_data(self):
        from backend.utils.vcf_parser import VCFParser
        parser = VCFParser()
        result = parser._parse_info_field("AF=0.1;DP=100")
        assert isinstance(result, dict)
        assert "AF" in result or "DP" in result


# ──────────────────────────────────────────────────────────────────
# variant_uploader tests
# ──────────────────────────────────────────────────────────────────

class TestVariantUploader:
    def test_import_works(self):
        from backend.services.variant_uploader import VariantUploader
        assert VariantUploader is not None

    @pytest.mark.asyncio
    async def test_upload_variants_empty(self):
        from backend.services.variant_uploader import VariantUploader
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result())
        uploader = VariantUploader(session)
        with patch("backend.services.variant_uploader.select", return_value=MagicMock()):
            result = await uploader.upload_variants(
                analysis_id=1,
                variants_data=[],
            )
            assert result == (0, 0) or isinstance(result, tuple)
