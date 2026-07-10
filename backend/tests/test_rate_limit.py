"""Per-IP rate limiting (U6) and cookie-secure wiring tests."""
import sys
import importlib

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.core.rate_limit import limiter
from backend.db.database import get_session
import backend.api.auth_routes as auth_routes
import backend.api.upload_routes as upload_routes
from backend.api.auth_routes import get_current_user, router as auth_router
from backend.api.upload_routes import router as upload_router


def _make_mock_user(user_id=1, username="testuser"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    return user


def _make_mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    # GeneticAnalysis is a conftest stub whose __getattr__ fabricates a fresh
    # MagicMock per access — set a real, JSON-serializable id on refresh so
    # upload_routes' JSONResponse({"analysis_id": ...}) doesn't 500.
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", 1))
    return session


def _build_app(current_user=None, session=None):
    if current_user is None:
        current_user = _make_mock_user()
    if session is None:
        session = _make_mock_session()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(auth_router)
    app.include_router(upload_router)

    async def override_session():
        yield session

    async def override_current_user():
        return current_user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    return app, session


def _load_real_auth_module():
    """Reimport the real backend.core.auth, bypassing conftest's MagicMock stub.

    conftest.py replaces sys.modules['backend.core.auth'] for the whole test
    session so unrelated tests never touch real JWT/cookie code. Cookie-secure
    wiring lives in that real module, so this test needs the genuine one —
    popped and reimported fresh, then the stub is restored for later tests.
    """
    saved = sys.modules.get('backend.core.auth')
    sys.modules.pop('backend.core.auth', None)
    try:
        return importlib.import_module('backend.core.auth')
    finally:
        if saved is not None:
            sys.modules['backend.core.auth'] = saved
        else:
            sys.modules.pop('backend.core.auth', None)


@pytest.fixture(autouse=True)
def _isolated_limiter_storage():
    """The limiter is a process-wide singleton with in-memory hit counters —
    reset before and after every test so one test's requests never count
    toward another's limit (all tests share the same TestClient IP/key)."""
    limiter.reset()
    yield
    limiter.reset()


class TestHappyPathUnthrottled:
    def test_many_requests_not_throttled_when_limiter_disabled(self):
        """Default test-session state: RATE_LIMIT_ENABLED unset -> limiter.enabled
        is False, so even a burst of requests never gets a 429. This is the
        behavior the whole existing suite (1755 tests) relies on."""
        app, _ = _build_app()
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.authenticate_user = AsyncMock(return_value=None)
            MockUS.return_value = mock_svc
            with TestClient(app) as client:
                statuses = [
                    client.post(
                        "/auth/login", json={"username": "u", "password": "p"}
                    ).status_code
                    for _ in range(20)
                ]
        assert 429 not in statuses


class TestLoginRateLimitExceeded:
    def test_exceeding_login_limit_returns_429_with_clear_message(self, monkeypatch):
        monkeypatch.setattr(limiter, "enabled", True)
        monkeypatch.setattr(auth_routes.settings.rate_limit, "auth_per_minute", 2)
        app, _ = _build_app()
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.authenticate_user = AsyncMock(return_value=None)
            MockUS.return_value = mock_svc
            with TestClient(app) as client:
                responses = [
                    client.post("/auth/login", json={"username": "u", "password": "p"})
                    for _ in range(3)
                ]
        assert [r.status_code for r in responses] == [401, 401, 429]
        assert "rate limit exceeded" in responses[2].json()["error"].lower()

    def test_limit_is_scoped_per_client_key(self, monkeypatch):
        """Two distinct source IPs each get their own quota — a second IP is
        not blocked by the first IP's requests. slowapi's default key_func
        (get_remote_address) reads request.client.host, so distinct IPs are
        simulated via TestClient's `client=(host, port)` param."""
        monkeypatch.setattr(limiter, "enabled", True)
        monkeypatch.setattr(auth_routes.settings.rate_limit, "auth_per_minute", 1)
        app, _ = _build_app()
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.authenticate_user = AsyncMock(return_value=None)
            MockUS.return_value = mock_svc
            login_body = {"username": "u", "password": "p"}
            with TestClient(app, client=("10.0.0.1", 12345)) as client_a:
                client_a_first = client_a.post("/auth/login", json=login_body)
                client_a_second = client_a.post("/auth/login", json=login_body)
            with TestClient(app, client=("10.0.0.2", 12345)) as client_b:
                client_b_first = client_b.post("/auth/login", json=login_body)
        assert client_a_first.status_code == 401
        assert client_a_second.status_code == 429
        assert client_b_first.status_code == 401


class TestUploadRateLimitExceeded:
    def test_exceeding_upload_limit_returns_429_without_starting_analysis(self, monkeypatch):
        monkeypatch.setattr(limiter, "enabled", True)
        monkeypatch.setattr(upload_routes.settings.rate_limit, "upload_per_hour", 1)
        app, session = _build_app()
        with patch("backend.api.upload_routes.VCFParser") as MockParser, \
             patch("backend.api.upload_routes._process_upload_background", new=AsyncMock()) as mock_bg:
            mock_parser = MagicMock()
            mock_parser.parse_vcf_content = AsyncMock(return_value=[{"rsid": "rs1"}])
            MockParser.return_value = mock_parser
            with TestClient(app) as client:
                file_content = b"##fileformat=VCFv4.2\n"
                first = client.post(
                    "/upload/vcf",
                    files={"file": ("test.vcf", file_content, "text/plain")},
                )
                second = client.post(
                    "/upload/vcf",
                    files={"file": ("test.vcf", file_content, "text/plain")},
                )
        assert first.status_code == 200
        assert second.status_code == 429
        assert session.add.call_count == 1
        assert mock_bg.call_count == 1


class TestConfigDrivenThreshold:
    @pytest.mark.parametrize("threshold", [1, 3])
    def test_effective_limit_follows_config_value(self, monkeypatch, threshold):
        monkeypatch.setattr(limiter, "enabled", True)
        monkeypatch.setattr(auth_routes.settings.rate_limit, "auth_per_minute", threshold)
        app, _ = _build_app()
        with patch("backend.api.auth_routes.UserService") as MockUS:
            mock_svc = MagicMock()
            mock_svc.authenticate_user = AsyncMock(return_value=None)
            MockUS.return_value = mock_svc
            with TestClient(app) as client:
                statuses = [
                    client.post(
                        "/auth/login", json={"username": "u", "password": "p"}
                    ).status_code
                    for _ in range(threshold + 1)
                ]
        assert statuses[:threshold] == [401] * threshold
        assert statuses[threshold] == 429


class TestCookieSecureWiring:
    def test_production_environment_sets_secure_cookie_header(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret-for-cookie-check")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
        real_auth = _load_real_auth_module()
        response = Response()
        real_auth.set_auth_cookies(response, "access-tok", "refresh-tok")
        set_cookie_headers = response.headers.getlist("set-cookie")
        assert len(set_cookie_headers) == 2
        assert all("Secure" in h for h in set_cookie_headers)

    def test_development_environment_omits_secure_cookie_header(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret-for-cookie-check")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
        real_auth = _load_real_auth_module()
        response = Response()
        real_auth.set_auth_cookies(response, "access-tok", "refresh-tok")
        set_cookie_headers = response.headers.getlist("set-cookie")
        assert len(set_cookie_headers) == 2
        assert all("Secure" not in h for h in set_cookie_headers)

    def test_explicit_cookie_secure_env_overrides_dev_default(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret-for-cookie-check")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("COOKIE_SECURE", "true")
        real_auth = _load_real_auth_module()
        response = Response()
        real_auth.set_auth_cookies(response, "access-tok", "refresh-tok")
        set_cookie_headers = response.headers.getlist("set-cookie")
        assert all("Secure" in h for h in set_cookie_headers)
