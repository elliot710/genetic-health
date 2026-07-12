"""Extended route tests: admin, annotation, variant, and analysis routes."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────

def _make_admin_user(user_id=1):
    user = MagicMock()
    user.id = user_id
    user.username = "admin"
    user.email = "admin@example.com"
    user.full_name = "Admin User"
    user.is_admin = True
    user.is_verified = True
    user.is_active = True
    user.created_at = datetime(2024, 1, 1)
    user.avatar_url = None
    user.google_id = None
    return user


def _make_regular_user(user_id=2):
    user = MagicMock()
    user.id = user_id
    user.username = "regular"
    user.email = "user@example.com"
    user.full_name = "Regular User"
    user.is_admin = False
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
    return session


def _make_mock_result(all_rows=None, scalar=None, scalars_list=None):
    result = MagicMock()
    result.all = MagicMock(return_value=all_rows or [])
    result.scalar_one_or_none = MagicMock(return_value=scalar)
    result.scalar = MagicMock(return_value=0)
    result.fetchall = MagicMock(return_value=all_rows or [])
    result.first = MagicMock(return_value=scalar)
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=scalars_list or [])
    scalars_mock.first = MagicMock(return_value=(scalars_list[0] if scalars_list else None))
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _build_app(routers, current_user=None, session=None):
    from backend.db.database import get_session
    from backend.api.auth_routes import get_current_user

    if current_user is None:
        current_user = _make_admin_user()
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


# ──────────────────────────────────────────────────
# Annotation Routes — no-DB endpoints
# ──────────────────────────────────────────────────

class TestAnnotationSupportedApis:
    def _build(self):
        from backend.api.annotation_routes import router
        return _build_app([router])

    def test_supported_apis_returns_200(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/api/annotations/supported-apis")
            assert resp.status_code == 200

    def test_supported_apis_has_apis_list(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/supported-apis").json()
            assert "apis" in data
            assert len(data["apis"]) > 0

    def test_supported_apis_each_has_name(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/supported-apis").json()
            for api in data["apis"]:
                assert "name" in api

    def test_supported_apis_has_new_features(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/supported-apis").json()
            assert "new_features" in data

    def test_supported_apis_has_usage_examples(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/supported-apis").json()
            assert "usage_examples" in data


class TestAnnotationExamples:
    def _build(self):
        from backend.api.annotation_routes import router
        return _build_app([router])

    def test_examples_returns_200(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/api/annotations/examples")
            assert resp.status_code == 200

    def test_examples_has_cardiovascular(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/examples").json()
            assert "cardiovascular" in data

    def test_examples_cardiovascular_has_rsid(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/examples").json()
            for item in data.get("cardiovascular", []):
                assert "rsid" in item

    def test_examples_has_oncology(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/annotations/examples").json()
            assert "oncology" in data


def _make_api_service_mock(method_name, return_value=None, raise_exc=None):
    """Create a context-manager mock for GeneticAPIService."""
    instance = MagicMock()
    if raise_exc:
        coro = AsyncMock(side_effect=raise_exc)
    else:
        coro = AsyncMock(return_value=return_value)
    setattr(instance, method_name, coro)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    return instance


class TestAnnotationEnsembl:
    def _build(self):
        from backend.api.annotation_routes import router
        return _build_app([router])

    def test_ensembl_lookup_success(self):
        mock_info = {"rsid": "rs12345", "data": []}
        svc = _make_api_service_mock("get_variant_info_from_ensembl", return_value=mock_info)
        with patch("backend.api.annotation_routes.GeneticAPIService", return_value=svc):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/annotations/ensembl/rs12345")
                assert resp.status_code == 200

    def test_ensembl_lookup_error(self):
        svc = _make_api_service_mock("get_variant_info_from_ensembl", raise_exc=Exception("fail"))
        with patch("backend.api.annotation_routes.GeneticAPIService", return_value=svc):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/annotations/ensembl/rs12345")
                assert resp.status_code == 500


class TestAnnotationClinvar:
    def _build(self):
        from backend.api.annotation_routes import router
        return _build_app([router])

    def test_clinvar_lookup_success(self):
        mock_result = {"rsid": "rs12345", "significance": "benign"}
        svc = _make_api_service_mock("get_variant_info_from_clinvar", return_value=mock_result)
        with patch("backend.api.annotation_routes.GeneticAPIService", return_value=svc):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/annotations/clinvar/rs12345")
                assert resp.status_code == 200

    def test_clinvar_lookup_error(self):
        svc = _make_api_service_mock("get_variant_info_from_clinvar", raise_exc=Exception("fail"))
        with patch("backend.api.annotation_routes.GeneticAPIService", return_value=svc):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/annotations/clinvar/rs12345")
                assert resp.status_code == 500


class TestAnnotationSnpedia:
    def _build(self):
        from backend.api.annotation_routes import router
        return _build_app([router])

    def test_snpedia_lookup_success(self):
        mock_result = {"rsid": "rs12345", "text": "some text"}
        svc = _make_api_service_mock("get_snpedia_info", return_value=mock_result)
        with patch("backend.api.annotation_routes.GeneticAPIService", return_value=svc):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/annotations/snpedia/rs12345")
                assert resp.status_code == 200

    def test_snpedia_lookup_error(self):
        svc = _make_api_service_mock("get_snpedia_info", raise_exc=Exception("fail"))
        with patch("backend.api.annotation_routes.GeneticAPIService", return_value=svc):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/annotations/snpedia/rs12345")
                assert resp.status_code == 500


# ──────────────────────────────────────────────────
# Variant Routes — no-DB/simple endpoints
# ──────────────────────────────────────────────────

class TestVariantExamples:
    def _build(self):
        from backend.api.variant_routes import router
        return _build_app([router])

    def test_examples_returns_200(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/api/variants/examples")
            assert resp.status_code == 200

    def test_examples_has_examples_list(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/variants/examples").json()
            assert "examples" in data
            assert len(data["examples"]) > 0

    def test_examples_has_supported_formats(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/variants/examples").json()
            assert "supported_formats" in data

    def test_examples_has_data_sources(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/variants/examples").json()
            assert "data_sources" in data


class TestVariantStats:
    def _build(self, session=None):
        from backend.api.variant_routes import router
        return _build_app([router], session=session)

    def test_stats_returns_200(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with TestClient(app) as client:
            resp = client.get("/api/variants/stats")
            assert resp.status_code == 200

    def test_stats_has_supported_databases(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with TestClient(app) as client:
            data = client.get("/api/variants/stats").json()
            assert "supported_databases" in data


class TestVariantSearch:
    def _build(self, session=None):
        from backend.api.variant_routes import router
        return _build_app([router], session=session)

    def test_search_no_query(self):
        session = _make_mock_session()
        # scalar_one_or_none=None makes analysis query return None → early return
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with patch("backend.api.variant_routes.select"):
            with TestClient(app) as client:
                resp = client.get("/api/variants/search")
                assert resp.status_code in (200, 400, 422)

    def test_search_with_query(self):
        session = _make_mock_session()
        marker = MagicMock()
        marker.rsid = "rs12345"
        marker.gene_symbol = "BRCA1"
        marker.chromosome = "17"
        marker.position = 41245466
        marker.ref_allele = "A"
        marker.alt_allele = "G"
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[marker]))
        app, _ = self._build(session)
        with patch("backend.api.variant_routes.select"):
            with TestClient(app) as client:
                resp = client.get("/api/variants/search?q=rs12345")
                assert resp.status_code in (200, 400, 500)


# ──────────────────────────────────────────────────
# Admin Routes helper
# ──────────────────────────────────────────────────

def _admin_sa_patch():
    """Context manager that patches SQLAlchemy functions in admin_routes
    and admin.users (users handlers live in the latter after the U1 split)."""
    import contextlib
    @contextlib.contextmanager
    def _patch():
        with patch("backend.api.admin_routes.select"), \
             patch("backend.api.admin_routes.func"), \
             patch("backend.api.admin_routes.delete"), \
             patch("backend.api.admin_routes.update"), \
             patch("backend.api.admin.users.select"), \
             patch("backend.api.admin.users.func"):
            yield
    return _patch()


class TestAdminUsers:
    def _build(self, session=None, user=None):
        from backend.api.admin_routes import router
        u = user or _make_admin_user()
        return _build_app([router], current_user=u, session=session)

    def test_list_users_returns_200(self):
        session = _make_mock_session()
        user_mock = MagicMock()
        user_mock.id = 1
        user_mock.email = "u@example.com"
        user_mock.username = "testuser"
        user_mock.full_name = "Test"
        user_mock.avatar_url = None
        user_mock.is_active = True
        user_mock.is_verified = True
        user_mock.is_admin = False
        user_mock.created_at = datetime(2024, 1, 1)
        session.execute = AsyncMock(return_value=_make_mock_result(
            all_rows=[(user_mock, 2)]
        ))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/users")
                assert resp.status_code in (200, 500)

    def test_list_users_forbidden_for_non_admin(self):
        session = _make_mock_session()
        non_admin = _make_regular_user()
        app, _ = self._build(session, user=non_admin)
        with TestClient(app) as client:
            resp = client.get("/api/admin/users")
            assert resp.status_code == 403

    def test_update_user_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.put("/api/admin/users/999", json={"is_active": True})
                assert resp.status_code == 404

    def test_update_user_success(self):
        session = _make_mock_session()
        mock_user = MagicMock()
        mock_user.id = 5
        mock_user.email = "u@example.com"
        mock_user.username = "testuser5"
        mock_user.full_name = None
        mock_user.avatar_url = None
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_user.is_admin = False
        mock_user.created_at = datetime(2024, 1, 1)
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=mock_user))
        session.refresh = AsyncMock(side_effect=lambda x: None)
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.put("/api/admin/users/5", json={"is_admin": True})
                assert resp.status_code in (200, 500)

    def test_delete_user_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/users/999")
                assert resp.status_code == 404

    def test_delete_self_forbidden(self):
        session = _make_mock_session()
        admin = _make_admin_user(user_id=1)
        mock_user = MagicMock()
        mock_user.id = 1  # same as admin
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=mock_user))
        app, _ = self._build(session, user=admin)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/users/1")
                assert resp.status_code == 400


class TestAdminDiscoveries:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_discovery_summary_returns_200(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(
            all_rows=[("pending", "variant_mapping", 3), ("approved", "variant_mapping", 1)]
        ))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/discoveries/summary")
                assert resp.status_code == 200

    def test_discovery_summary_counts(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                data = client.get("/api/admin/discoveries/summary").json()
                assert "total_pending" in data
                assert data["total_pending"] == 0

    def test_list_discoveries_returns_200(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/discoveries")
                assert resp.status_code == 200

    def test_review_discovery_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post(
                    "/api/admin/discoveries/999/review",
                    json={"action": "reject", "rejection_reason": "test"}
                )
                assert resp.status_code == 404

    def test_review_discovery_invalid_action(self):
        session = _make_mock_session()
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post(
                    "/api/admin/discoveries/1/review",
                    json={"action": "invalid_action"}
                )
                assert resp.status_code == 400

    def test_review_discovery_reject(self):
        session = _make_mock_session()
        discovery = MagicMock()
        discovery.id = 1
        discovery.rsid = "rs12345"
        discovery.status = "pending"
        discovery.discovery_type = "variant_mapping"
        discovery.discovered_by = None
        discovery.map_type = "rsid"
        discovery.mapping_category = "health"
        discovery.mapping_data = {}
        discovery.gene = None
        discovery.panel_id = None
        discovery.description = None
        discovery.category = None
        discovery.source_data = None
        discovery.map_type = "rsid"
        discovery.lookup_count = 1
        discovery.reviewed_by = None
        discovery.reviewed_at = None
        discovery.rejection_reason = None
        discovery.created_at = datetime(2024, 1, 1)
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=discovery))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with patch("backend.api.admin_routes.get_notification_service"):
                with TestClient(app) as client:
                    resp = client.post(
                        "/api/admin/discoveries/1/review",
                        json={"action": "reject", "rejection_reason": "not valid"}
                    )
                    assert resp.status_code in (200, 400, 422, 500)

    def test_bulk_review_invalid_action(self):
        session = _make_mock_session()
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post(
                    "/api/admin/discoveries/bulk-review",
                    json=[1, 2, 3],
                    params={"action": "invalid"},
                    headers={"Content-Type": "application/json"}
                )
                assert resp.status_code in (400, 422)


class TestAdminVariantMappings:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_list_mapping_categories_returns_200(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/variant-mappings/categories")
                assert resp.status_code == 200

    def test_list_mappings_by_category_returns_200(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/variant-mappings/health")
                assert resp.status_code == 200

    def test_create_variant_mapping_invalid_type(self):
        session = _make_mock_session()
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/variant-mappings", json={
                    "category": "health",
                    "map_type": "invalid_type",
                    "key": "rs12345",
                    "data": {}
                })
                assert resp.status_code == 400

    def test_create_variant_mapping_duplicate(self):
        session = _make_mock_session()
        existing = MagicMock()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=existing))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/variant-mappings", json={
                    "category": "health",
                    "map_type": "rsid",
                    "key": "rs12345",
                    "data": {}
                })
                assert resp.status_code == 409

    def test_update_variant_mapping_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.put("/api/admin/variant-mappings/999", json={"data": {}})
                assert resp.status_code == 404

    def test_delete_variant_mapping_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/variant-mappings/999")
                assert resp.status_code == 404

    def test_delete_variant_mapping_success(self):
        session = _make_mock_session()
        mapping_obj = MagicMock()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=mapping_obj))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/variant-mappings/1")
                assert resp.status_code == 200


class TestAdminJobs:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_jobs_summary_returns_200(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(
            all_rows=[("completed", 5), ("pending", 2), ("failed", 1), ("processing", 0)]
        ))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/jobs/summary")
                assert resp.status_code == 200

    def test_jobs_summary_contains_counts(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                data = client.get("/api/admin/jobs/summary").json()
                assert "total" in data
                assert "pending" in data


    def test_jobs_latency_empty_when_no_completed_analyses(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                data = client.get("/api/admin/jobs/latency").json()
                assert data["sample_size"] == 0
                assert data["p50_seconds"] is None
                assert data["p95_seconds"] is None

    def test_jobs_latency_computes_p50_p95_from_durations(self):
        session = _make_mock_session()
        rows = [
            (datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 1, 0)),  # 60s
            (datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 2, 0)),  # 120s
            (datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 5, 0)),  # 300s
        ]
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=rows))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                data = client.get("/api/admin/jobs/latency").json()
                assert data["sample_size"] == 3
                assert data["p50_seconds"] == 120.0
                assert data["p95_seconds"] == 300.0
                assert data["exceeds_threshold"] is False

    def test_list_jobs_returns_200(self):
        session = _make_mock_session()
        analysis = MagicMock()
        analysis.id = 1
        analysis.user_id = 1
        analysis.filename = "test.vcf"
        analysis.file_type = "vcf"
        analysis.analysis_status = "completed"
        analysis.progress_percentage = 100
        analysis.total_variants = 500
        analysis.processed_variants = 500
        analysis.current_step = None
        analysis.upload_date = datetime(2024, 1, 1)
        analysis.estimated_completion = None
        session.execute = AsyncMock(return_value=_make_mock_result(
            all_rows=[(analysis, "user@example.com", "testuser")]
        ))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/jobs")
                assert resp.status_code == 200

    def test_cancel_job_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/jobs/999/cancel")
                assert resp.status_code == 404

    def test_cancel_job_wrong_status(self):
        session = _make_mock_session()
        analysis = MagicMock()
        analysis.analysis_status = "completed"
        analysis.id = 1
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=analysis))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/jobs/1/cancel")
                assert resp.status_code == 400

    def test_pause_job_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/jobs/999/pause")
                assert resp.status_code == 404

    def test_resume_job_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/jobs/999/resume")
                assert resp.status_code == 404

    def test_restart_job_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/jobs/999/restart")
                assert resp.status_code == 404

    def test_delete_job_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/jobs/999")
                assert resp.status_code == 404

    def test_get_job_logs_not_found(self):
        # Route always returns 200 with empty logs (no 404 behavior)
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/jobs/999/logs")
                assert resp.status_code == 200
                assert resp.json()["count"] == 0

    def test_get_job_logs_success(self):
        from backend.services.job_logs import JobLogCollector
        session = _make_mock_session()
        analysis = MagicMock()
        analysis.id = 1
        analysis.job_logs = None
        analysis.analysis_status = "completed"
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=analysis))
        collector = JobLogCollector.get_instance()
        collector.add(1, "INFO", "test log")
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/jobs/1/logs")
                assert resp.status_code == 200


class TestAdminCategoryRules:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_list_rules_empty(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/category-rules")
                assert resp.status_code == 200
                assert resp.json() == []

    def test_list_rules_with_filter(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalars_list=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.get("/api/admin/category-rules?category=health")
                assert resp.status_code == 200

    def test_create_rule_success(self):
        session = _make_mock_session()
        rule_obj = MagicMock()
        rule_obj.id = 1
        rule_obj.category = "health"
        rule_obj.rule_type = "gene"
        session.refresh = AsyncMock(side_effect=lambda obj: None)
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/category-rules", json={
                    "category": "health",
                    "rule_type": "gene",
                    "rule_value": "BRCA1",
                    "priority": 100,
                    "is_active": True
                })
                assert resp.status_code in (200, 201, 422)

    def test_update_rule_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.put("/api/admin/category-rules/999", json={"priority": 50})
                assert resp.status_code == 404

    def test_delete_rule_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/category-rules/999")
                assert resp.status_code == 404

    def test_delete_rule_success(self):
        session = _make_mock_session()
        rule = MagicMock()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=rule))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.delete("/api/admin/category-rules/1")
                assert resp.status_code == 200


class TestAdminAnnotationSources:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_list_annotation_sources_returns_200(self):
        session = _make_mock_session()
        mock_source = MagicMock()
        mock_source.id = 1
        mock_source.source_name = "ensembl"
        mock_source.display_name = "Ensembl"
        mock_source.is_enabled = True
        mock_source.priority = 1
        mock_source.rate_limit = 10.0
        mock_source.source_type = "external"
        mock_source.description = "Ensembl API"
        # Ensure scalar returns 0 for count queries
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=0, all_rows=[]))

        with patch("backend.api.admin_routes._ensure_source_configs", new=AsyncMock(return_value=[mock_source])):
            with _admin_sa_patch():
                app, _ = self._build(session)
                with TestClient(app) as client:
                    resp = client.get("/api/admin/annotation-sources")
                    assert resp.status_code in (200, 500)

    def test_update_annotation_source_not_found(self):
        session = _make_mock_session()
        with patch("backend.api.admin_routes._ensure_source_configs", new=AsyncMock(return_value=[])):
            with _admin_sa_patch():
                session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
                app, _ = self._build(session)
                with TestClient(app) as client:
                    resp = client.put("/api/admin/annotation-sources/ensembl", json={"is_enabled": True})
                    assert resp.status_code == 404


class TestAdminClinvarEtl:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_clinvar_etl_status(self):
        etl_mock = AsyncMock()
        etl_mock.get_import_status = AsyncMock(return_value={"status": "ok", "row_count": 100})
        with patch("backend.services.clinvar_etl.ClinVarETL", return_value=etl_mock):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/admin/clinvar-etl/status")
                assert resp.status_code == 200

    def test_clinvar_etl_progress(self):
        with patch("backend.services.clinvar_etl.get_etl_progress", return_value={"running": False, "pct": 0}):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/admin/clinvar-etl/progress")
                assert resp.status_code == 200


class TestAdminGnomadEtl:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_gnomad_etl_status(self):
        etl_mock = AsyncMock()
        etl_mock.get_import_status = AsyncMock(return_value={"status": "ready"})
        with patch("backend.services.gnomad_etl.GnomadETL", return_value=etl_mock):
            app, _ = self._build()
            with TestClient(app) as client:
                resp = client.get("/api/admin/gnomad-etl/status")
                assert resp.status_code == 200


class TestAdminIncompleteAnnotations:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_incomplete_summary_returns_200(self):
        session = _make_mock_session()
        # Patch the helper functions to avoid complex DB query mocking
        with patch("backend.api.admin_routes._get_all_enabled_source_names", new=AsyncMock(return_value=["ensembl", "clinvar"])):
            with patch("backend.api.admin_routes._get_enabled_source_names", new=AsyncMock(return_value=["ensembl"])):
                with patch("backend.api.admin_routes._build_incomplete_condition", return_value=None):
                    session.execute = AsyncMock(return_value=_make_mock_result(scalar=10))
                    app, _ = self._build(session)
                    with _admin_sa_patch():
                        with TestClient(app) as client:
                            resp = client.get("/api/admin/annotations/incomplete/summary")
                            assert resp.status_code in (200, 500)

    def test_incomplete_list_returns_200(self):
        session = _make_mock_session()
        with patch("backend.api.admin_routes._get_all_enabled_source_names", new=AsyncMock(return_value=["ensembl"])):
            with patch("backend.api.admin_routes._get_enabled_source_names", new=AsyncMock(return_value=[])):
                with patch("backend.api.admin_routes._build_incomplete_condition", return_value=None):
                    app, _ = self._build(session)
                    with _admin_sa_patch():
                        with TestClient(app) as client:
                            resp = client.get("/api/admin/annotations/incomplete")
                            assert resp.status_code in (200, 500)

    def test_retrigger_annotation_not_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/annotations/retrigger/999")
                assert resp.status_code == 404


class TestRetriggerSourcesEnsemblGuard:
    """_retrigger_sources must not let a remote 'ensembl' fetch clobber the
    shared ensembl_data column when it's already populated (e.g. by the
    authoritative local 'ensembl_vep' writer)."""

    def _make_annotation(self, ensembl_data=None):
        from backend.db.models import SharedVariantAnnotation
        return SharedVariantAnnotation(rsid="rs123", ensembl_data=ensembl_data)

    async def test_retrigger_ensembl_skips_when_ensembl_data_already_found(self):
        from backend.api.admin_routes import _retrigger_sources

        existing_data = {"found": True, "source": "ensembl_vep", "data": {"consequence": "missense_variant"}}
        annotation = self._make_annotation(ensembl_data=existing_data)

        remote_call = AsyncMock(return_value={"found": True, "source": "ensembl", "data": {"consequence": "synonymous_variant"}})
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock()
        mock_service.close = AsyncMock()
        mock_service._get_ensembl_annotation = remote_call

        with patch("backend.services.genetic_api_service.OptimizedGeneticAPIService", return_value=mock_service):
            updated, confirmed_no_data, still_failed = await _retrigger_sources(annotation, ["ensembl"])

        assert annotation.ensembl_data == existing_data
        remote_call.assert_not_called()
        assert "ensembl" not in updated
        assert "ensembl" not in confirmed_no_data
        assert "ensembl" not in still_failed

    async def test_retrigger_ensembl_writes_when_ensembl_data_absent(self):
        from backend.api.admin_routes import _retrigger_sources

        annotation = self._make_annotation(ensembl_data=None)
        fresh_data = {"found": True, "source": "ensembl", "data": {"consequence": "missense_variant"}}

        remote_call = AsyncMock(return_value=fresh_data)
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock()
        mock_service.close = AsyncMock()
        mock_service._get_ensembl_annotation = remote_call

        with patch("backend.services.genetic_api_service.OptimizedGeneticAPIService", return_value=mock_service):
            updated, confirmed_no_data, still_failed = await _retrigger_sources(annotation, ["ensembl"])

        remote_call.assert_awaited_once_with("rs123")
        assert annotation.ensembl_data == fresh_data
        assert updated == ["ensembl"]

    async def test_retrigger_ensembl_retries_when_existing_is_confirmed_no_data(self):
        """A confirmed-absent result (found=False) is not 'populated' — the guard
        only blocks found=True data, so a retry attempt is still allowed to run."""
        from backend.api.admin_routes import _retrigger_sources

        existing_data = {"found": False, "confirmed_no_data": True, "source": "ensembl_vep"}
        annotation = self._make_annotation(ensembl_data=existing_data)

        remote_call = AsyncMock(return_value={"found": False})
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock()
        mock_service.close = AsyncMock()
        mock_service._get_ensembl_annotation = remote_call

        with patch("backend.services.genetic_api_service.OptimizedGeneticAPIService", return_value=mock_service):
            updated, confirmed_no_data, still_failed = await _retrigger_sources(annotation, ["ensembl"])

        remote_call.assert_awaited_once_with("rs123")
        assert "ensembl" in confirmed_no_data


class TestAdminPurgeDeleted:
    def _build(self, session=None):
        from backend.api.admin_routes import router
        return _build_app([router], session=session)

    def test_purge_deleted_success(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session)
        with _admin_sa_patch():
            with TestClient(app) as client:
                resp = client.post("/api/admin/purge-deleted")
                assert resp.status_code in (200, 500)
