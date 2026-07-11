"""Negative-authz gate for the admin API surface.

Enumerates every route registered on the admin router (rather than a
hand-maintained list) and asserts each one rejects a caller who is not an
admin -- either unauthenticated, or authenticated as a regular user. This is
the safety net for the admin_routes.py -> admin/ package split: existing
admin tests authenticate AS an admin and would not notice a route silently
losing its `require_admin` guard during the move.
"""
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from backend.api.admin_routes import router as admin_router
from backend.api.auth_routes import get_current_user
from backend.db.database import get_session

_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _admin_routes():
    """(method, concrete_path) for every route on the admin router.

    Path params are replaced with a dummy value: the admin guard runs before
    FastAPI validates path/query/body params, so a placeholder is enough to
    reach it (see docs/plans -- verified against real FastAPI dependency
    resolution order).
    """
    pairs = []
    for route in admin_router.routes:
        concrete_path = _PATH_PARAM.sub("1", route.path)
        for method in route.methods:
            if method == "HEAD":
                continue
            pairs.append((method, concrete_path))
    return sorted(pairs)


ADMIN_ROUTES = _admin_routes()


def _make_mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    return session


def _make_non_admin_user():
    user = MagicMock()
    user.id = 2
    user.username = "not_admin"
    user.is_admin = False
    return user


def _build_app(*, authenticate_as_non_admin: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router)

    async def override_session():
        yield _make_mock_session()

    app.dependency_overrides[get_session] = override_session

    if authenticate_as_non_admin:
        non_admin = _make_non_admin_user()

        async def override_current_user():
            return non_admin

        app.dependency_overrides[get_current_user] = override_current_user
    return app


class TestAdminRouteAuthzGate:
    """Every admin route must return 401/403 without the admin role."""

    def test_route_enumeration_covers_expected_surface(self):
        assert len(ADMIN_ROUTES) >= 60

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_rejects_unauthenticated_caller(self, method, path):
        app = _build_app(authenticate_as_non_admin=False)
        with TestClient(app) as client:
            response = client.request(method, path)
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_rejects_non_admin_caller(self, method, path):
        app = _build_app(authenticate_as_non_admin=True)
        with TestClient(app) as client:
            response = client.request(method, path)
        assert response.status_code == 403
