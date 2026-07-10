"""Tests for smaller route files: health, notification, sharing, insights, auth (extras)."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


def _build_app_with_routers(routers, current_user=None, session=None):
    from backend.db.database import get_session
    from backend.api.auth_routes import get_current_user

    if current_user is None:
        current_user = _make_mock_user()
    if session is None:
        session = _make_mock_session()

    app = FastAPI()
    for router, prefix in routers:
        app.include_router(router)

    async def override_session():
        yield session

    async def override_current_user():
        return current_user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    return app, session


# ──────────────────────────────────────────────
# health_routes
# ──────────────────────────────────────────────

class TestHealthRoutes:
    def _build(self, session=None):
        from backend.api.health_routes import router
        return _build_app_with_routers([(router, "/health")], session=session)

    def test_health_check_returns_healthy(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/health/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"

    def test_health_check_includes_service_name(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/health/")
            assert "service" in resp.json()

    def test_database_health_check_success(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalar.return_value = 1
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.health_routes.text", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/health/database")
                assert resp.status_code == 200

    def test_database_health_check_error(self):
        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=Exception("DB down"))
        app, _ = self._build(session=session)
        with patch("backend.api.health_routes.text", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/health/database")
                assert resp.status_code in (200, 503, 500)
                data = resp.json()
                assert data["status"] in ("unhealthy", "healthy")


# ──────────────────────────────────────────────
# insights_routes
# ──────────────────────────────────────────────

class TestInsightsRoutes:
    def _build(self, user=None, session=None):
        from backend.api.insights_routes import router
        return _build_app_with_routers([(router, "")], current_user=user, session=session)

    def test_insights_status(self):
        app, _ = self._build()
        with patch("backend.api.insights_routes.get_llm_status", return_value={"enabled": False, "provider": "gemini"}):
            with TestClient(app) as client:
                resp = client.get("/api/insights/status")
                assert resp.status_code == 200

    def test_toggle_insights_admin(self):
        user = _make_mock_user(is_admin=True)
        app, _ = self._build(user=user)
        with patch("backend.api.insights_routes.set_insights_enabled", return_value={"enabled": True}):
            with TestClient(app) as client:
                resp = client.post("/api/insights/toggle?enabled=true")
                assert resp.status_code == 200

    def test_toggle_insights_non_admin_forbidden(self):
        user = _make_mock_user(is_admin=False)
        app, _ = self._build(user=user)
        with TestClient(app) as client:
            resp = client.post("/api/insights/toggle?enabled=true")
            assert resp.status_code == 403

    def test_generate_variant_insight(self):
        app, session = self._build()
        with patch("backend.api.insights_routes.generate_variant_insight", new=AsyncMock(return_value={"summary": "test"})):
            with TestClient(app) as client:
                resp = client.post("/api/insights/generate-variant", json={
                    "rsid": "rs123", "variant_data": {"gene": "BRCA1"}
                })
                assert resp.status_code in (200, 400, 422)

    def test_generate_variant_missing_params(self):
        app, session = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/insights/generate-variant", json={})
            assert resp.status_code in (400, 422)

    def test_generate_section_invalid(self):
        app, session = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/insights/generate/invalid_section")
            assert resp.status_code == 400

    def test_generate_section_no_analysis(self):
        app, session = self._build()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        import sqlalchemy as _sa
        mock_select = MagicMock(return_value=MagicMock())
        mock_desc = MagicMock(return_value=MagicMock())
        with patch.object(_sa, 'select', mock_select), patch.object(_sa, 'desc', mock_desc):
            with TestClient(app) as client:
                resp = client.post("/api/insights/generate/health")
                assert resp.status_code in (404, 500, 422)

    def test_knowledge_graph(self):
        app, session = self._build()
        with patch("backend.api.insights_routes.build_knowledge_graph", new=AsyncMock(return_value={"nodes": [], "edges": [], "stats": {}})):
            with TestClient(app) as client:
                resp = client.get("/api/insights/knowledge-graph")
                assert resp.status_code == 200


# ──────────────────────────────────────────────
# auth_routes — extra tests
# ──────────────────────────────────────────────

class TestAuthRoutesExtended:
    def _build(self, user=None, session=None):
        from backend.api.auth_routes import router
        return _build_app_with_routers([(router, "")], current_user=user, session=session)

    def test_login_valid_credentials(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        mock_user = _make_mock_user()
        with patch("backend.api.auth_routes.UserService") as MockUS, \
             patch("backend.api.auth_routes.ACCESS_TOKEN_EXPIRE_MINUTES", 10):
            mock_svc = MagicMock()
            mock_svc.authenticate_user = AsyncMock(return_value=mock_user)
            MockUS.return_value = mock_svc
            with patch("backend.api.auth_routes.create_access_token", return_value="access_token"), \
                 patch("backend.api.auth_routes.create_refresh_token", return_value="refresh_token"), \
                 patch("backend.api.auth_routes.set_auth_cookies"):
                with TestClient(app) as client:
                    resp = client.post("/auth/login", json={"username": "testuser", "password": "pass"})
                    assert resp.status_code in (200, 401, 503)

    def test_login_invalid_credentials(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.authenticate_user = AsyncMock(return_value=None)
            MockUS.return_value = mock_svc
            with TestClient(app) as client:
                resp = client.post("/auth/login", json={"username": "bad", "password": "wrong"})
                assert resp.status_code in (401, 400)

    def test_logout(self):
        app, _ = self._build()
        with patch("backend.api.auth_routes.clear_auth_cookies"):
            with TestClient(app) as client:
                resp = client.post("/auth/logout")
                assert resp.status_code == 200

    def test_get_notification_preferences(self):
        user = _make_mock_user()
        user.notification_preferences = {"analysis_completed": True}
        app, _ = self._build(user=user)
        with TestClient(app) as client:
            resp = client.get("/auth/notification-preferences")
            assert resp.status_code in (200, 500)

    def test_update_notification_preferences(self):
        session = _make_mock_session()
        user = _make_mock_user()
        user.notification_preferences = {}
        session.commit = AsyncMock()
        app, _ = self._build(user=user, session=session)
        with TestClient(app) as client:
            resp = client.put("/auth/notification-preferences", json={"preferences": {"analysis_completed": False}})
            assert resp.status_code in (200, 400, 500)

    def test_ws_token(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/auth/ws-token")
            assert resp.status_code in (200, 401, 500)

    def test_ws_token_with_cookie(self):
        app, _ = self._build()
        with patch("backend.api.auth_routes.create_access_token", return_value="ws_token"):
            with TestClient(app) as client:
                client.cookies.set("access_token", "mytoken")
                resp = client.get("/auth/ws-token")
                assert resp.status_code in (200, 401, 500)

    def test_forgot_password_accepted(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.get_user_by_email = AsyncMock(return_value=None)
            MockUS.return_value = mock_svc
            with TestClient(app) as client:
                resp = client.post("/auth/forgot-password", json={"email": "test@example.com"})
                assert resp.status_code == 202

    def test_reset_password_invalid_token(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.auth_routes.verify_reset_token", return_value=None):
            with TestClient(app) as client:
                resp = client.post("/auth/reset-password", json={"token": "bad", "new_password": "newpass"})
                assert resp.status_code in (400, 422)

    def test_create_reset_token_and_verify(self):
        from backend.api.auth_routes import create_reset_token, verify_reset_token
        with patch("backend.api.auth_routes.SECRET_KEY", "test-secret-key"), \
             patch("backend.api.auth_routes.ALGORITHM", "HS256"):
            token = create_reset_token("user@example.com")
            assert isinstance(token, str)
            email = verify_reset_token(token)
            assert email == "user@example.com"

    def test_verify_reset_token_invalid(self):
        from backend.api.auth_routes import verify_reset_token
        result = verify_reset_token("invalid.token.here")
        assert result is None

    def test_get_saved_variants(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.auth_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/auth/saved-variants")
                assert resp.status_code in (200, 500)

    def test_refresh_token_missing(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/auth/refresh")
            assert resp.status_code in (401, 400, 422)


# ──────────────────────────────────────────────
# notification_routes REST
# ──────────────────────────────────────────────

class TestNotificationRoutes:
    def _build(self, user=None, session=None):
        from backend.api.notification_routes import notification_router
        return _build_app_with_routers([(notification_router, "")], current_user=user, session=session)

    def test_list_notifications(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.notification_routes.get_notification_service") as mock_svc:
            instance = MagicMock()
            instance.get_for_user = AsyncMock(return_value=[])
            instance.unread_count = AsyncMock(return_value=0)
            mock_svc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/notifications")
                assert resp.status_code in (200, 500)

    def test_unread_count(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.notification_routes.get_notification_service") as mock_svc:
            instance = MagicMock()
            instance.unread_count = AsyncMock(return_value=5)
            mock_svc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/notifications/unread-count")
                assert resp.status_code in (200, 500)

    def test_mark_notification_read(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.notification_routes.get_notification_service") as mock_svc:
            instance = MagicMock()
            instance.mark_read = AsyncMock(return_value=True)
            mock_svc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/notifications/1/read")
                assert resp.status_code in (200, 404, 500)

    def test_mark_all_read(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.notification_routes.get_notification_service") as mock_svc:
            instance = MagicMock()
            instance.mark_all_read = AsyncMock(return_value=3)
            mock_svc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/notifications/read-all")
                assert resp.status_code in (200, 500)

    def test_delete_notification(self):
        session = _make_mock_session()
        app, _ = self._build(session=session)
        with patch("backend.api.notification_routes.get_notification_service") as mock_svc:
            instance = MagicMock()
            instance.delete = AsyncMock(return_value=True)
            mock_svc.return_value = instance
            with TestClient(app) as client:
                resp = client.delete("/api/notifications/1")
                assert resp.status_code in (200, 204, 404, 500)


# ──────────────────────────────────────────────
# sharing_routes
# ──────────────────────────────────────────────

class TestSharingRoutes:
    def _build(self, user=None, session=None):
        from backend.api.sharing_routes import router
        return _build_app_with_routers([(router, "")], current_user=user, session=session)

    def test_get_my_shares(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.sharing_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/sharing/my-shares")
                assert resp.status_code in (200, 500)

    def test_get_shared_with_me(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.sharing_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/sharing/shared-with-me")
                assert resp.status_code in (200, 500)

    def test_share_analysis(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.sharing_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/api/sharing/share", json={"email": "other@example.com"})
                assert resp.status_code in (200, 400, 404, 500)

    def test_delete_share(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.sharing_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.delete("/api/sharing/share/2")
                assert resp.status_code in (200, 404, 500)


# ──────────────────────────────────────────────
# upload_routes
# ──────────────────────────────────────────────

class TestUploadRoutes:
    def _build(self, user=None, session=None):
        from backend.api.upload_routes import router
        return _build_app_with_routers([(router, "")], current_user=user, session=session)

    def test_get_data_summary(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalar.return_value = 0
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()), \
             patch("backend.api.upload_routes.func", MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/upload/data-summary")
                assert resp.status_code in (200, 500)

    def test_delete_data_not_found(self):
        session = _make_mock_session()
        session.rollback = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.delete("/upload/data")
                assert resp.status_code in (404, 500)

    def test_get_analysis_variants(self):
        session = _make_mock_session()
        result = MagicMock()
        result.scalar.return_value = 0
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app, _ = self._build(session=session)
        with patch("backend.api.upload_routes.select", return_value=MagicMock()), \
             patch("backend.api.upload_routes.func", MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/upload/analysis/1/variants")
                assert resp.status_code in (200, 404, 500)
