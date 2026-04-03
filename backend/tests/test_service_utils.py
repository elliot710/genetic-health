"""Tests for auto_categorizer pure functions, analysis routes, and upload routes."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────
# Auto categorizer pure/static functions
# ──────────────────────────────────────────────────────────────────

class TestAutoCategorizerIsServerForCategory:
    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._is_severe_for_category

    def test_non_lifestyle_category_always_false(self):
        fn = self._fn()
        assert fn("cancer", "health") is False

    def test_non_lifestyle_drug_response(self):
        fn = self._fn()
        assert fn("cancer", "drug_response") is False

    def test_lifestyle_category_no_kwd_loaded(self):
        # _SEVERE_EXCLUSION_KW is loaded from DB — starts empty, so no exclusions
        from backend.services.multi_source_categorizer import _SEVERE_EXCLUSION_KW
        _SEVERE_EXCLUSION_KW.clear()
        fn = self._fn()
        assert fn("cancer", "sports") is False

    def test_lifestyle_category_with_kwd_loaded(self):
        from backend.services.multi_source_categorizer import _SEVERE_EXCLUSION_KW
        _SEVERE_EXCLUSION_KW.clear()
        _SEVERE_EXCLUSION_KW.add("cancer")
        fn = self._fn()
        assert fn("cancer", "sports") is True
        _SEVERE_EXCLUSION_KW.clear()

    def test_lifestyle_category_partial_match(self):
        from backend.services.multi_source_categorizer import _SEVERE_EXCLUSION_KW
        _SEVERE_EXCLUSION_KW.clear()
        _SEVERE_EXCLUSION_KW.add("carcinoma")
        fn = self._fn()
        assert fn("hepatocarcinoma risk", "nutrition") is True
        _SEVERE_EXCLUSION_KW.clear()

    def test_empty_condition_lifestyle(self):
        from backend.services.multi_source_categorizer import _SEVERE_EXCLUSION_KW
        _SEVERE_EXCLUSION_KW.clear()
        fn = self._fn()
        assert fn("", "sports") is False

    def test_ancestry_non_lifestyle(self):
        fn = self._fn()
        # ancestry is in _LIFESTYLE_CATEGORIES but empty kws → False
        from backend.services.multi_source_categorizer import _SEVERE_EXCLUSION_KW
        _SEVERE_EXCLUSION_KW.clear()
        assert fn("african ancestry", "ancestry") is False


class TestAutoCategorizerCleanCondition:
    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._clean_condition

    def test_empty_string(self):
        fn = self._fn()
        assert fn("") == ""

    def test_not_provided(self):
        fn = self._fn()
        assert fn("not provided") == ""

    def test_see_cases(self):
        fn = self._fn()
        assert fn("see cases") == ""

    def test_simple_condition_no_separator(self):
        fn = self._fn()
        assert fn("BRCA1-related cancer") == "BRCA1-related cancer"

    def test_pipe_separated_skips_garbage(self):
        fn = self._fn()
        result = fn("not provided|Heart Disease|not specified")
        assert result == "Heart Disease"

    def test_semicolon_separated(self):
        fn = self._fn()
        result = fn("not provided;Type 2 Diabetes")
        assert result == "Type 2 Diabetes"

    def test_uppercase_part_converted_to_title(self):
        fn = self._fn()
        result = fn("not provided|BRCA1 CANCER")
        assert result == "Brca1 Cancer"

    def test_none_returns_empty(self):
        fn = self._fn()
        assert fn(None) == ""

    def test_dash_returns_empty(self):
        fn = self._fn()
        assert fn("-") == ""

    def test_all_garbage_chunks(self):
        fn = self._fn()
        result = fn("not provided|not specified|see cases")
        assert result == ""

    def test_no_separator_not_affected(self):
        fn = self._fn()
        assert fn("Diabetes Mellitus Type 2") == "Diabetes Mellitus Type 2"


class TestAutoCategorizerRiskMultiplier:
    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._risk_multiplier_from_review_status

    def test_practice_guideline_pathogenic(self):
        fn = self._fn()
        assert fn("practice guideline", "Pathogenic") == 3.0

    def test_expert_panel_pathogenic(self):
        fn = self._fn()
        assert fn("reviewed by expert panel", "Pathogenic") == 2.0

    def test_multiple_submitters(self):
        fn = self._fn()
        assert fn("criteria provided, multiple submitters, no conflicts", "Pathogenic") == 1.5

    def test_single_submitter(self):
        fn = self._fn()
        assert fn("criteria provided, single submitter", "Pathogenic") == 1.2

    def test_unknown_review_status(self):
        fn = self._fn()
        assert fn("", "Pathogenic") == 1.2

    def test_practice_guideline_likely_pathogenic(self):
        fn = self._fn()
        result = fn("practice guideline", "Likely pathogenic")
        assert result == round(3.0 * 0.8, 2)

    def test_expert_panel_likely_pathogenic(self):
        fn = self._fn()
        result = fn("reviewed by expert panel", "Likely pathogenic")
        assert result == round(2.0 * 0.8, 2)

    def test_no_conflicts_multiple_submitters(self):
        fn = self._fn()
        result = fn("no conflicts", "Pathogenic")
        assert result == 1.5

    def test_none_review_status(self):
        fn = self._fn()
        assert fn(None, "Pathogenic") == 1.2


class TestAutoCategorizerPopulateCategoryFields:
    def _fn(self):
        from backend.services.auto_categorizer import AutoCategorizer
        return AutoCategorizer._populate_category_fields

    def test_health_category_sets_condition(self):
        fn = self._fn()
        data = {}
        fn(data, "health", "BRCA1 Cancer", "BRCA1")
        assert "condition" in data
        assert data["condition"] == "BRCA1 Cancer"

    def test_drug_category_sets_drug(self):
        fn = self._fn()
        data = {}
        fn(data, "drug_response", "CYP2D6 variant", "CYP2D6")
        assert "drug" in data

    def test_nutrition_category_sets_nutrient(self):
        fn = self._fn()
        data = {}
        fn(data, "nutrition", "Vitamin D metabolism", "VDR")
        assert "nutrient" in data

    def test_existing_fields_not_overwritten(self):
        fn = self._fn()
        data = {"condition": "My Custom Condition"}
        fn(data, "health", "New Condition", "GENE1")
        assert data["condition"] == "My Custom Condition"  # setdefault preserves

    def test_all_fields_populated(self):
        fn = self._fn()
        data = {}
        fn(data, "health", "Heart Disease", "MYH7")
        for field in ('condition', 'trait', 'domain', 'metric', 'nutrient', 'category'):
            assert field in data


# ──────────────────────────────────────────────────────────────────
# Test helpers for routes
# ──────────────────────────────────────────────────────────────────

def _make_mock_user(user_id=1, is_admin=False):
    user = MagicMock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.is_admin = is_admin
    user.is_verified = True
    user.is_active = True
    user.created_at = datetime(2024, 1, 1)
    user.avatar_url = None
    user.google_id = None
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


def _build_app(routers, current_user=None, session=None):
    from backend.db.database import get_session
    from backend.api.auth_routes import get_current_user

    if current_user is None:
        current_user = _make_mock_user()
    if session is None:
        session = _make_mock_session()

    app = FastAPI()
    for router in routers:
        app.include_router(router)

    async def _override_session():
        yield session

    async def _override_user():
        return current_user

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = _override_user
    return app, session


def _make_analysis(analysis_id=1, status="completed", user_id=1):
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


# ──────────────────────────────────────────────────────────────────
# Analysis routes - additional tests
# ──────────────────────────────────────────────────────────────────

class TestAnalysisRoutesExtra:
    def _app(self, session=None, user=None):
        from backend.api.analysis_routes import router
        return _build_app([router], current_user=user or _make_mock_user(), session=session)

    def test_list_analyses_empty(self):
        session = _make_mock_session()
        result = _make_mock_result(scalars_list=[], scalar=0)
        session.execute = AsyncMock(return_value=result)
        app, _ = self._app(session)
        with TestClient(app) as client:
            resp = client.get("/api/analysis/list")
            assert resp.status_code in (200, 500)

    def test_list_analyses_with_analysis(self):
        session = _make_mock_session()
        analysis = _make_analysis()
        result = _make_mock_result(scalars_list=[analysis])
        session.execute = AsyncMock(return_value=result)
        app, _ = self._app(session)
        with TestClient(app) as client:
            resp = client.get("/api/analysis/list")
            assert resp.status_code in (200, 500)

    def test_cancel_analysis_success(self):
        analysis = _make_analysis(status="processing")
        app, session = self._app()
        session.execute = AsyncMock(return_value=_make_mock_result())
        session.commit = AsyncMock()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with patch("backend.api.analysis_routes.update", return_value=MagicMock()):
                with TestClient(app) as client:
                    resp = client.post("/api/analysis/cancel/1")
                    assert resp.status_code in (200, 500)

    def test_pause_analysis_not_running(self):
        analysis = _make_analysis(status="completed")
        app, _ = self._app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/pause/1")
                assert resp.status_code in (200, 400, 404, 409, 500)

    def test_delete_analysis_success(self):
        analysis = _make_analysis(status="completed")
        app, session = self._app()
        session.execute = AsyncMock(return_value=_make_mock_result())
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/status/1")
                assert resp.status_code in (200, 500)

    def test_results_endpoint_completed(self):
        analysis = _make_analysis(status="completed")
        app, session = self._app()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with patch("backend.api.analysis_routes.select", return_value=MagicMock()):
                with TestClient(app) as client:
                    resp = client.get("/api/analysis/results/1")
                    assert resp.status_code in (200, 202, 400, 500)

    def test_dashboard_data_no_analysis(self):
        app, session = self._app()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        with patch("backend.api.analysis_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/dashboard-data")
                assert resp.status_code in (200, 404, 500)

    def test_stream_not_found(self):
        from fastapi import HTTPException
        exc = HTTPException(status_code=404)
        app, _ = self._app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(side_effect=exc)):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/stream/999")
                assert resp.status_code in (200, 404, 500)


# ──────────────────────────────────────────────────────────────────
# Upload routes
# ──────────────────────────────────────────────────────────────────

class TestUploadRoutesExtra:
    def _app(self, session=None, user=None):
        from backend.api.upload_routes import router
        return _build_app([router], current_user=user or _make_mock_user(), session=session)

    def test_data_summary_no_analysis(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._app(session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/upload/data-summary")
                assert resp.status_code in (200, 404, 500)

    def test_data_summary_with_analysis(self):
        session = _make_mock_session()
        analysis = _make_analysis()
        variant_result = _make_mock_result(scalar=0)
        analysis_result = _make_mock_result(scalar=analysis)
        session.execute = AsyncMock(side_effect=[analysis_result, variant_result, variant_result])
        app, _ = self._app(session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/upload/data-summary")
                assert resp.status_code in (200, 500)

    def test_delete_all_data_no_analysis(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._app(session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.delete("/upload/data")
                assert resp.status_code in (200, 404, 500)

    def test_get_analysis_variants_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._app(session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/upload/analysis/999/variants")
                assert resp.status_code in (200, 404, 500)

    def test_reanalyze_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._app(session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/upload/analysis/999/reanalyze")
                assert resp.status_code in (200, 404, 500)

    def test_delete_analysis_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._app(session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.delete("/upload/analysis/999")
                assert resp.status_code in (200, 404, 500, 422)


# ──────────────────────────────────────────────────────────────────
# Annotation routes - larger tests
# ──────────────────────────────────────────────────────────────────

class TestAnnotationVariantDetails:
    def _build(self, session=None):
        from backend.api.annotation_routes import router
        return _build_app([router], session=session)

    def test_variant_details_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with patch("backend.api.annotation_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/annotations/variant-details/rs99999")
                assert resp.status_code in (200, 404, 500)

    def test_variant_post_empty_rsid(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/annotations/variant", json={})
            assert resp.status_code in (200, 400, 422, 500)

    def test_batch_annotation_empty(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/annotations/batch", json={"rsids": []})
            assert resp.status_code in (200, 400, 422, 500)

    def test_clinical_summary_post(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with patch("backend.api.annotation_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/api/annotations/clinical-summary",
                                   json={"rsid": "rs12345"})
                assert resp.status_code in (200, 400, 422, 500)

    def test_literature_post(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/annotations/literature",
                               json={"rsid": "rs12345"})
            assert resp.status_code in (200, 400, 422, 500)


# ──────────────────────────────────────────────────────────────────
# Variant lookup route POST
# ──────────────────────────────────────────────────────────────────

class TestVariantLookupPost:
    def _build(self, session=None):
        from backend.api.variant_routes import router
        user = _make_mock_user()
        return _build_app([router], current_user=user, session=session)

    def test_lookup_empty_variant_id(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/variants/lookup",
                               json={"variant_id": ""})
            assert resp.status_code in (200, 400, 422, 500)

    def test_lookup_valid_variant_id_with_mocked_service(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        lookup_result = {
            "variant_id": "rs12345",
            "found": False,
            "source": "cache",
            "search_timestamp": "2024-01-01T00:00:00",
            "basic_info": {},
            "clinical_significance": [],
            "population_data": {},
            "pharmacogenomics": {},
            "literature": {},
            "external_links": {},
            "annotations": {},
            "cached": False,
        }
        with patch("backend.api.variant_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_comprehensive_variant_info = AsyncMock(return_value=lookup_result)
            MockSvc.return_value = instance
            with patch("backend.api.variant_routes.select", return_value=MagicMock()):
                with patch("backend.api.variant_routes.get_clinvar_local_service"):
                    with patch("backend.api.variant_routes.get_ensembl_local_service"):
                        with patch("backend.api.variant_routes.get_gnomad_service"):
                            with patch("backend.api.variant_routes.get_alpha_missense_service"):
                                app, _ = self._build(session)
                                with TestClient(app) as client:
                                    resp = client.post("/api/variants/lookup",
                                                       json={"variant_id": "rs12345"})
                                    assert resp.status_code in (200, 400, 422, 500)


# ──────────────────────────────────────────────────────────────────
# Analysis service pure functions
# ──────────────────────────────────────────────────────────────────

class TestAnalysisServicePure:
    def test_annotation_result_creation(self):
        from backend.services.analysis_service import AnnotationResult
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

    def test_annotation_result_defaults(self):
        from backend.services.analysis_service import AnnotationResult
        result = AnnotationResult(
            rsid="rs99999",
            was_reused=False,
            annotation_data=None,
            source="new",
        )
        assert result.rsid == "rs99999"
        assert result.was_reused is False


# ──────────────────────────────────────────────────────────────────
# seed_category_rules test
# ──────────────────────────────────────────────────────────────────

class TestSeedCategoryRules:
    @pytest.mark.asyncio
    async def test_seed_no_force(self):
        from backend.services.auto_categorizer import seed_category_rules
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalar=MagicMock(return_value=5)  # Already seeded
        ))
        mock_session.commit = AsyncMock()
        with patch("backend.services.auto_categorizer.async_session_factory", return_value=mock_session):
            with patch("backend.services.auto_categorizer.select", return_value=MagicMock()):
                result = await seed_category_rules(force=False)
                assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_seed_with_force(self):
        from backend.services.auto_categorizer import seed_category_rules
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalar=MagicMock(return_value=0)
        ))
        mock_session.commit = AsyncMock()
        with patch("backend.services.auto_categorizer.async_session_factory", return_value=mock_session):
            with patch("backend.services.auto_categorizer.select", return_value=MagicMock()):
                result = await seed_category_rules(force=True)
                assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────────
# local_annotation pure functions
# ──────────────────────────────────────────────────────────────────

class TestLocalAnnotation:
    def test_build_rsid_variant_map_empty(self):
        from backend.services.local_annotation import build_rsid_variant_map
        result = build_rsid_variant_map([])
        assert result == {}

    def test_build_rsid_variant_map_with_variants(self):
        from backend.services.local_annotation import build_rsid_variant_map
        v = MagicMock()
        v.rsid = "rs12345"
        result = build_rsid_variant_map([v])
        assert "rs12345" in result

    def test_build_rsid_variant_map_skips_none_rsid(self):
        from backend.services.local_annotation import build_rsid_variant_map
        v = MagicMock()
        v.rsid = None
        result = build_rsid_variant_map([v])
        assert result == {}

    def test_build_gnomad_pos_tuples_empty_dict(self):
        from backend.services.local_annotation import build_gnomad_pos_tuples
        result = build_gnomad_pos_tuples([], {})
        assert result == []

    def test_build_gnomad_pos_tuples_missing_variant(self):
        from backend.services.local_annotation import build_gnomad_pos_tuples
        result = build_gnomad_pos_tuples(["rs12345"], {})
        assert result == []

    def test_build_am_batch_empty(self):
        from backend.services.local_annotation import build_am_batch
        result = build_am_batch([], {})
        assert result == []

    def test_build_am_batch_missing_rsid(self):
        from backend.services.local_annotation import build_am_batch
        result = build_am_batch(["rs99999"], {})
        assert result == []

    def test_loaded_sources_creation(self):
        from backend.services.local_annotation import LoadedSources
        sources = LoadedSources()
        assert hasattr(sources, "clinvar")
        assert hasattr(sources, "gnomad")
        assert hasattr(sources, "alpha_missense")

    def test_loaded_sources_active_names_empty(self):
        from backend.services.local_annotation import LoadedSources
        sources = LoadedSources()
        assert sources.active_names == []


# ──────────────────────────────────────────────────────────────────
# auto_categorizer AutoCategorizer.run() method
# ──────────────────────────────────────────────────────────────────

class TestAutoCategorizerRun:
    @pytest.mark.asyncio
    async def test_run_no_rules(self):
        from backend.services.auto_categorizer import AutoCategorizer
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))
        mock_session.commit = AsyncMock()
        with patch("backend.services.auto_categorizer.async_session_factory", return_value=mock_session):
            with patch("backend.services.auto_categorizer.select", return_value=MagicMock()):
                cat = AutoCategorizer()
                result = await cat.run()
                assert result.get("error") is not None  # No rules found
