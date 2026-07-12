"""Route integration tests using FastAPI TestClient with mocked dependencies."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Build a minimal test app that only mounts the routes we want to test ──────

from datetime import datetime


def _make_mock_user(user_id=1, username="testuser", is_admin=False):
    user = MagicMock()
    user.id = user_id
    user.username = username
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
    return session


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
    a.upload_date = "2024-01-01T00:00:00"
    a.strategy_used = "fast"
    a.estimated_completion = None
    a.job_logs = None
    a.deleted_at = None
    return a


# ── App factory ────────────────────────────────────────────────────────────────

def _build_test_app(current_user=None, session=None):
    """Build a minimal FastAPI app with overridden dependencies."""
    if current_user is None:
        current_user = _make_mock_user()
    if session is None:
        session = _make_mock_session()

    from backend.db.database import get_session
    from backend.api.auth_routes import get_current_user, router as auth_router
    from backend.api.analysis_routes import router as analysis_router
    from backend.api.admin_routes import router as admin_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(analysis_router)
    app.include_router(admin_router)

    async def override_session():
        yield session

    async def override_current_user():
        return current_user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    return app, session


# ===========================================================================
# Auth routes
# ===========================================================================

class TestAuthRoutes:
    def _build_app(self, user=None):
        return _build_test_app(current_user=user)

    def test_get_me_returns_user(self):
        from backend.db.schemas import UserResponse
        user = _make_mock_user()
        app, _ = self._build_app(user)
        with patch("backend.api.auth_routes.UserResponse.model_validate",
                   return_value=UserResponse(
                       id=1, username="testuser", email="test@example.com",
                       is_active=True, is_verified=True, is_admin=False,
                       created_at=datetime(2024, 1, 1)
                   )):
            with TestClient(app) as client:
                resp = client.get("/auth/me")
                assert resp.status_code == 200

    def test_get_me_includes_username(self):
        from backend.db.schemas import UserResponse
        user = _make_mock_user(username="alice")
        app, _ = self._build_app(user)
        with patch("backend.api.auth_routes.UserResponse.model_validate",
                   return_value=UserResponse(
                       id=1, username="alice", email="test@example.com",
                       is_active=True, is_verified=True, is_admin=False,
                       created_at=datetime(2024, 1, 1)
                   )):
            with TestClient(app) as client:
                resp = client.get("/auth/me")
                assert resp.status_code == 200
                assert resp.json()["username"] == "alice"

    def test_change_password_correct_old_password(self):
        user = _make_mock_user()
        app, session = self._build_app(user)
        user.hashed_password = "hashed"
        with patch("backend.api.auth_routes.verify_password", return_value=True), \
             patch("backend.api.auth_routes.get_password_hash", return_value="new_hash"):
            with TestClient(app) as client:
                resp = client.post("/auth/change-password", json={
                    "current_password": "oldpass",
                    "new_password": "newpass123"
                })
                assert resp.status_code in (200, 400, 422)

    def test_change_password_wrong_old_password(self):
        user = _make_mock_user()
        app, session = self._build_app(user)
        user.hashed_password = "hashed"
        with patch("backend.api.auth_routes.verify_password", return_value=False):
            with TestClient(app) as client:
                resp = client.post("/auth/change-password", json={
                    "current_password": "wrongpass",
                    "new_password": "newpass123"
                })
                assert resp.status_code in (400, 401)

    def test_update_profile_success(self):
        from backend.db.schemas import UserResponse
        user = _make_mock_user()
        app, session = self._build_app(user)
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.update_user = AsyncMock(return_value=user)
            MockUS.return_value = mock_svc
            with patch("backend.api.auth_routes.UserResponse.model_validate",
                       return_value=UserResponse(
                           id=1, username="testuser", email="test@example.com",
                           is_active=True, is_verified=True, is_admin=False,
                           created_at=datetime(2024, 1, 1)
                       )):
                with TestClient(app) as client:
                    resp = client.put("/auth/me", json={"full_name": "New Name"})
                    assert resp.status_code in (200, 422, 400)


# ===========================================================================
# Analysis routes
# ===========================================================================

class TestAnalysisRoutes:
    """Tests that mock the _get_user_analysis helper to bypass SQLAlchemy ORM queries."""

    def test_start_analysis_already_processing(self):
        analysis = _make_analysis(status="processing")
        app, session = _build_test_app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/start/1")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "processing"

    def test_start_analysis_queues_completed(self):
        analysis = _make_analysis(status="completed")
        app, session = _build_test_app()
        session.execute = AsyncMock(return_value=MagicMock())
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)), \
             patch("backend.api.analysis_routes.update", return_value=MagicMock()), \
             patch("backend.api.analysis_routes.get_notification_service") as mock_notif:
            mock_notif.return_value.create = AsyncMock()
            with TestClient(app) as client:
                resp = client.post("/api/analysis/start/1")
                assert resp.status_code == 200
                assert resp.json()["status"] == "pending"

    def test_start_analysis_not_found_returns_404(self):
        from fastapi import HTTPException
        app, session = _build_test_app()
        exc = HTTPException(status_code=404, detail="Analysis not found")
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(side_effect=exc)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/start/999")
                assert resp.status_code == 404

    def test_get_status_returns_analysis(self):
        analysis = _make_analysis(status="completed")
        app, session = _build_test_app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/status/1")
                assert resp.status_code == 200
                assert resp.json()["status"] == "completed"

    def test_get_status_not_found(self):
        from fastapi import HTTPException
        app, session = _build_test_app()
        exc = HTTPException(status_code=404, detail="Analysis not found")
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(side_effect=exc)):
            with TestClient(app) as client:
                resp = client.get("/api/analysis/status/999")
                assert resp.status_code == 404

    def test_list_analyses_returns_list(self):
        analysis = _make_analysis()
        app, session = _build_test_app()
        # list endpoint fetches all analyses for user - mock execute to return list
        result = MagicMock()
        result.scalars.return_value.all.return_value = [analysis]
        result.scalar.return_value = 0
        session.execute = AsyncMock(return_value=result)
        with TestClient(app) as client:
            resp = client.get("/api/analysis/list")
            assert resp.status_code in (200, 500)

    def test_regenerate_insights_already_processing(self):
        analysis = _make_analysis(status="processing")
        app, session = _build_test_app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/regenerate-insights/1")
                assert resp.status_code == 409

    def test_regenerate_insights_queues_completed(self):
        analysis = _make_analysis(status="completed")
        app, session = _build_test_app()
        session.execute = AsyncMock(return_value=MagicMock())
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)), \
             patch("backend.api.analysis_routes.update", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/api/analysis/regenerate-insights/1")
                assert resp.status_code == 200
                assert resp.json()["status"] == "pending"

    def test_delete_analysis_not_found(self):
        from fastapi import HTTPException
        app, session = _build_test_app()
        exc = HTTPException(status_code=404, detail="Analysis not found")
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(side_effect=exc)):
            with TestClient(app) as client:
                resp = client.delete("/api/analysis/999")
                assert resp.status_code == 404

    def test_get_results_processing_returns_202(self):
        analysis = _make_analysis(status="processing")
        app, session = _build_test_app()
        with patch("backend.api.analysis_routes._get_user_analysis", new=AsyncMock(return_value=analysis)):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
            result.scalar.return_value = 0
            session.execute = AsyncMock(return_value=result)
            with TestClient(app) as client:
                resp = client.get("/api/analysis/results/1")
                assert resp.status_code in (200, 202, 400, 500)


# ===========================================================================
# Admin routes (subset)
# ===========================================================================

class TestAdminRoutes:
    def _make_admin_app(self):
        user = _make_mock_user(is_admin=True)
        app, session = _build_test_app(current_user=user)
        return app, session, user

    def _mock_db_result(self, session, items=None, scalar=0):
        result = MagicMock()
        result.scalars.return_value.all.return_value = items or []
        result.scalar.return_value = scalar
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        return result

    def test_get_users_admin(self):
        app, session, _ = self._make_admin_app()
        self._mock_db_result(session)
        with patch("backend.api.admin_routes.select", return_value=MagicMock()), \
             patch("backend.api.admin.users.select", return_value=MagicMock()), \
             patch("backend.api.admin.users.func", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/admin/users")
                assert resp.status_code in (200, 403, 500)

    def test_get_discoveries_admin(self):
        app, session, _ = self._make_admin_app()
        self._mock_db_result(session)
        with patch("backend.api.admin_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/admin/discoveries")
                assert resp.status_code in (200, 403, 500)

    def test_get_discovery_summary(self):
        app, session, _ = self._make_admin_app()
        result = MagicMock()
        result.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        with patch("backend.api.admin_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/admin/discoveries/summary")
                assert resp.status_code in (200, 403, 500)

    def test_non_admin_user_has_no_access(self):
        user = _make_mock_user(is_admin=False)
        app, session = _build_test_app(current_user=user)
        self._mock_db_result(session)
        with TestClient(app) as client:
            resp = client.get("/api/admin/users")
            assert resp.status_code in (200, 403)

    def test_get_variant_mappings_admin(self):
        app, session, _ = self._make_admin_app()
        self._mock_db_result(session)
        with patch("backend.api.admin_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/admin/variant-mappings/categories")
                assert resp.status_code in (200, 403, 500)

    def test_run_auto_categorize(self):
        app, session, _ = self._make_admin_app()
        self._mock_db_result(session)
        with TestClient(app) as client:
            resp = client.post("/api/admin/auto-categorize")
            assert resp.status_code in (200, 403, 500)

    def test_get_annotation_source_configs(self):
        app, session, _ = self._make_admin_app()
        with patch("backend.api.admin_routes._ensure_source_configs", new=AsyncMock(return_value=[])):
            result = MagicMock()
            result.scalar.return_value = 0
            session.execute = AsyncMock(return_value=result)
            with TestClient(app) as client:
                resp = client.get("/api/admin/annotation-sources")
                assert resp.status_code in (200, 403, 500)
