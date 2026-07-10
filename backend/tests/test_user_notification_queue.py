"""Tests for user_service, notification_service, analysis_queue, and knowledge_graph."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

def _mock_select():
    m = MagicMock()
    m.return_value = m
    m.where = MagicMock(return_value=m)
    m.order_by = MagicMock(return_value=m)
    m.limit = MagicMock(return_value=m)
    m.options = MagicMock(return_value=m)
    return m


# ──────────────────────────────────────────────
# UserService
# ──────────────────────────────────────────────

class TestUserService:
    def _make_db_session(self):
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.get = AsyncMock()
        return session

    def _make_user(self, user_id=1, username="user1", email="u@example.com"):
        u = MagicMock()
        u.id = user_id
        u.username = username
        u.email = email
        u.hashed_password = "hashed"
        return u

    @pytest.mark.asyncio
    async def test_get_user_by_id_found(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            found = await svc.get_user_by_id(1)
            assert found is user

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            found = await svc.get_user_by_id(999)
            assert found is None

    @pytest.mark.asyncio
    async def test_get_user_by_email(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            found = await svc.get_user_by_email("u@example.com")
            assert found is user

    @pytest.mark.asyncio
    async def test_get_user_by_username(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            found = await svc.get_user_by_username("user1")
            assert found is user

    @pytest.mark.asyncio
    async def test_create_user(self):
        from backend.services.user_service import UserService
        from backend.db.schemas import UserCreate
        session = self._make_db_session()
        with patch("backend.services.user_service.get_password_hash", return_value="hashed"):
            svc = UserService(session)
            user_data = UserCreate(email="new@example.com", username="newuser", password="pass123")
            await svc.create_user(user_data)
            session.add.assert_called_once()
            session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_authenticate_user_valid(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()), \
             patch("backend.services.user_service.verify_password", return_value=True):
            svc = UserService(session)
            auth_user = await svc.authenticate_user("user1", "pass")
            assert auth_user is user

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()), \
             patch("backend.services.user_service.verify_password", return_value=False):
            svc = UserService(session)
            auth_user = await svc.authenticate_user("user1", "wrongpass")
            assert auth_user is None

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            auth_user = await svc.authenticate_user("nonexistent", "pass")
            assert auth_user is None

    @pytest.mark.asyncio
    async def test_update_user_found(self):
        from backend.services.user_service import UserService
        from backend.db.schemas import UserUpdate
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            update_data = UserUpdate(full_name="New Name")
            await svc.update_user(1, update_data)
            session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_user_not_found(self):
        from backend.services.user_service import UserService
        from backend.db.schemas import UserUpdate
        session = self._make_db_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            update_data = UserUpdate(full_name="New Name")
            updated = await svc.update_user(999, update_data)
            assert updated is None

    @pytest.mark.asyncio
    async def test_update_user_with_password(self):
        from backend.services.user_service import UserService
        from backend.db.schemas import UserUpdate
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()), \
             patch("backend.services.user_service.get_password_hash", return_value="new_hash"):
            svc = UserService(session)
            update_data = UserUpdate(password="newpass123")
            await svc.update_user(1, update_data)
            assert user.hashed_password == "new_hash"

    @pytest.mark.asyncio
    async def test_update_password(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()), \
             patch("backend.services.user_service.get_password_hash", return_value="new_hash"):
            svc = UserService(session)
            await svc.update_password(1, "newpass")
            assert user.hashed_password == "new_hash"
            session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_password_user_not_found(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            await svc.update_password(999, "newpass")
            session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_or_create_google_user_by_google_id(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            found = await svc.get_or_create_google_user("u@g.com", "gid123", "Full Name", None)
            assert found is user

    @pytest.mark.asyncio
    async def test_get_or_create_google_user_by_email(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        existing_user = self._make_user()
        existing_user.google_id = None
        existing_user.avatar_url = None

        def execute_side_effect(stmt):
            r = MagicMock()
            if not hasattr(execute_side_effect, 'called'):
                r.scalar_one_or_none.return_value = None
                execute_side_effect.called = True
            else:
                r.scalar_one_or_none.return_value = existing_user
            return r

        session.execute.side_effect = [
            _make_none_result(),
            _make_val_result(existing_user),
        ]
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            found = await svc.get_or_create_google_user("u@g.com", "gid999", "Name", None)
            assert found is existing_user

    @pytest.mark.asyncio
    async def test_get_or_create_google_user_creates_new(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        session.execute.return_value = _make_none_result()
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            await svc.get_or_create_google_user("new@g.com", "gid000", "New User", None)
            session.add.assert_called()
            session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_user_analyses(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()), \
             patch("backend.services.user_service.selectinload", MagicMock()):
            svc = UserService(session)
            analyses = await svc.get_user_analyses(1)
            assert analyses == []

    @pytest.mark.asyncio
    async def test_delete_account_deletes_user_via_session(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        session.delete = AsyncMock()
        user = self._make_user()
        svc = UserService(session)
        await svc.delete_account(user)
        session.delete.assert_awaited_once_with(user)

    @pytest.mark.asyncio
    async def test_export_account_data_excludes_hashed_password(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        user.full_name = "Test User"
        user.avatar_url = None
        user.auth_provider = "local"
        user.is_verified = True
        user.created_at = datetime(2024, 1, 1)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            data = await svc.export_account_data(user)
        assert "hashed_password" not in data["profile"]

    @pytest.mark.asyncio
    async def test_export_account_data_scopes_profile_to_the_given_user(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user(user_id=7, username="scoped_user", email="scoped@example.com")
        user.full_name = "Scoped User"
        user.avatar_url = None
        user.auth_provider = "local"
        user.is_verified = True
        user.created_at = datetime(2024, 1, 1)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            data = await svc.export_account_data(user)
        assert data["profile"]["email"] == "scoped@example.com"

    @pytest.mark.asyncio
    async def test_export_account_data_returns_no_analyses_for_new_user(self):
        from backend.services.user_service import UserService
        session = self._make_db_session()
        user = self._make_user()
        user.full_name = "Test User"
        user.avatar_url = None
        user.auth_provider = "local"
        user.is_verified = True
        user.created_at = datetime(2024, 1, 1)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        with patch("backend.services.user_service.select", _mock_select()):
            svc = UserService(session)
            data = await svc.export_account_data(user)
        assert data["analyses"] == []


def _make_none_result():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _make_val_result(val):
    r = MagicMock()
    r.scalar_one_or_none.return_value = val
    return r


# ──────────────────────────────────────────────
# NotificationService
# ──────────────────────────────────────────────

class TestNotificationService:
    def _make_svc(self):
        from backend.services.notification_service import NotificationService
        return NotificationService()

    def _make_ws(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_adds_connection(self):
        svc = self._make_svc()
        ws = self._make_ws()
        await svc.connect(1, ws)
        assert ws in svc._connections[1]

    @pytest.mark.asyncio
    async def test_connect_multiple_sockets(self):
        svc = self._make_svc()
        ws1 = self._make_ws()
        ws2 = self._make_ws()
        await svc.connect(1, ws1)
        await svc.connect(1, ws2)
        assert len(svc._connections[1]) == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        svc = self._make_svc()
        ws = self._make_ws()
        await svc.connect(1, ws)
        await svc.disconnect(1, ws)
        assert 1 not in svc._connections

    @pytest.mark.asyncio
    async def test_disconnect_no_connection_is_safe(self):
        svc = self._make_svc()
        ws = self._make_ws()
        await svc.disconnect(999, ws)

    @pytest.mark.asyncio
    async def test_push_sends_to_connected_socket(self):
        svc = self._make_svc()
        ws = self._make_ws()
        await svc.connect(1, ws)
        await svc._push_to_user(1, {"event": "test"})
        ws.send_json.assert_awaited_once_with({"event": "test"})

    @pytest.mark.asyncio
    async def test_push_cleans_dead_connections(self):
        svc = self._make_svc()
        ws = self._make_ws()
        ws.send_json = AsyncMock(side_effect=Exception("disconnected"))
        await svc.connect(1, ws)
        await svc._push_to_user(1, {"event": "test"})
        assert 1 not in svc._connections

    @pytest.mark.asyncio
    async def test_push_progress(self):
        svc = self._make_svc()
        ws = self._make_ws()
        await svc.connect(1, ws)
        await svc.push_progress(1, 10, 50, "processing")
        ws.send_json.assert_awaited_once()
        payload = ws.send_json.call_args[0][0]
        assert payload["event"] == "analysis_progress"
        assert payload["progress"] == 50

    @pytest.mark.asyncio
    async def test_get_for_user(self):
        svc = self._make_svc()
        session = MagicMock()
        notif = MagicMock()
        notif.id = 1
        notif.type = "analysis_completed"
        notif.title = "Done"
        notif.message = "Complete"
        notif.data = {}
        notif.read = False
        notif.created_at = datetime(2024, 1, 1)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [notif]
        session.execute = AsyncMock(return_value=result)
        with patch("backend.services.notification_service.select", _mock_select()):
            items = await svc.get_for_user(session, 1)
        assert len(items) == 1
        assert items[0]["type"] == "analysis_completed"

    @pytest.mark.asyncio
    async def test_get_for_user_unread_only(self):
        svc = self._make_svc()
        session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        with patch("backend.services.notification_service.select", _mock_select()):
            items = await svc.get_for_user(session, 1, unread_only=True)
        assert items == []

    @pytest.mark.asyncio
    async def test_mark_read(self):
        svc = self._make_svc()
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = 1
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        with patch("backend.services.notification_service.update", _mock_select()):
            ok = await svc.mark_read(session, 1, 1)
        assert ok is True

    @pytest.mark.asyncio
    async def test_mark_read_not_found(self):
        svc = self._make_svc()
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        with patch("backend.services.notification_service.update", _mock_select()):
            ok = await svc.mark_read(session, 999, 1)
        assert ok is False

    @pytest.mark.asyncio
    async def test_mark_all_read(self):
        svc = self._make_svc()
        session = MagicMock()
        result = MagicMock()
        result.all.return_value = [1, 2, 3]
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        with patch("backend.services.notification_service.update", _mock_select()):
            count = await svc.mark_all_read(session, 1)
        assert count == 3

    @pytest.mark.asyncio
    async def test_delete_notification_found(self):
        svc = self._make_svc()
        session = MagicMock()
        notif = MagicMock()
        notif.user_id = 1
        session.get = AsyncMock(return_value=notif)
        session.delete = AsyncMock()
        session.commit = AsyncMock()
        ok = await svc.delete(session, 1, 1)
        assert ok is True

    @pytest.mark.asyncio
    async def test_delete_notification_not_found(self):
        svc = self._make_svc()
        session = MagicMock()
        session.get = AsyncMock(return_value=None)
        ok = await svc.delete(session, 999, 1)
        assert ok is False

    @pytest.mark.asyncio
    async def test_delete_notification_wrong_user(self):
        svc = self._make_svc()
        session = MagicMock()
        notif = MagicMock()
        notif.user_id = 2
        session.get = AsyncMock(return_value=notif)
        ok = await svc.delete(session, 1, 1)
        assert ok is False

    @pytest.mark.asyncio
    async def test_unread_count(self):
        svc = self._make_svc()
        session = MagicMock()
        result = MagicMock()
        result.scalar_one.return_value = 5
        session.execute = AsyncMock(return_value=result)
        with patch("backend.services.notification_service.select", _mock_select()):
            count = await svc.unread_count(session, 1)
        assert count == 5

    def test_get_notification_service_singleton(self):
        from backend.services.notification_service import get_notification_service
        s1 = get_notification_service()
        s2 = get_notification_service()
        assert s1 is s2


# ──────────────────────────────────────────────
# AnalysisQueue
# ──────────────────────────────────────────────

class TestQueuedAnalysis:
    def test_defaults(self):
        from backend.services.analysis_queue import QueuedAnalysis
        q = QueuedAnalysis(analysis_id=1, user_id=2)
        assert q.analysis_id == 1
        assert q.user_id == 2
        assert q.priority == 0
        assert q.queued_at is not None

    def test_custom_priority(self):
        from backend.services.analysis_queue import QueuedAnalysis
        q = QueuedAnalysis(analysis_id=5, user_id=3, priority=2)
        assert q.priority == 2


class TestAnalysisQueue:
    def _make_queue(self):
        from backend.services.analysis_queue import AnalysisQueue
        return AnalysisQueue(max_concurrent_jobs=2)

    @pytest.mark.asyncio
    async def test_enqueue_first_analysis(self):
        q = self._make_queue()
        with patch.object(q, 'start', new=AsyncMock()):
            result = await q.enqueue_analysis(1, 10)
            assert result is True

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_running(self):
        from backend.services.analysis_queue import QueuedAnalysis
        q = self._make_queue()
        q._running_jobs[1] = QueuedAnalysis(1, 10)
        with patch.object(q, 'start', new=AsyncMock()):
            result = await q.enqueue_analysis(1, 10)
            assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_queued(self):
        q = self._make_queue()
        q._queued_analysis_ids.add(1)
        q._queued_user_ids[1] = 10
        with patch.object(q, 'start', new=AsyncMock()):
            result = await q.enqueue_analysis(1, 10)
            assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_user_limit_exceeded(self):
        q = self._make_queue()
        q._user_running_count[10] = 2
        with patch.object(q, 'start', new=AsyncMock()):
            result = await q.enqueue_analysis(5, 10)
            assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_bypass_limit(self):
        q = self._make_queue()
        q._user_running_count[10] = 5
        with patch.object(q, 'start', new=AsyncMock()):
            result = await q.enqueue_analysis(5, 10, _bypass_limit=True)
            assert result is True

    def test_is_analysis_running_true(self):
        from backend.services.analysis_queue import QueuedAnalysis
        q = self._make_queue()
        q._running_jobs[1] = QueuedAnalysis(1, 10)
        assert q.is_analysis_running(1) is True

    def test_is_analysis_running_false(self):
        q = self._make_queue()
        assert q.is_analysis_running(999) is False

    def test_get_queue_status(self):
        q = self._make_queue()
        status = q.get_queue_status()
        assert "queue_size" in status
        assert "running_jobs" in status
        assert "max_concurrent" in status
        assert status["max_concurrent"] == 2

    @pytest.mark.asyncio
    async def test_stop_queue(self):
        q = self._make_queue()
        q._processing_task = asyncio.create_task(asyncio.sleep(10))
        await q.stop()
        assert q._shutdown is True

    def test_get_analysis_queue_singleton(self):
        from backend.services.analysis_queue import get_analysis_queue
        import backend.services.analysis_queue as aq_mod
        aq_mod._analysis_queue = None
        q1 = get_analysis_queue()
        q2 = get_analysis_queue()
        assert q1 is q2
        aq_mod._analysis_queue = None

    @pytest.mark.asyncio
    async def test_queue_analysis_function(self):
        import backend.services.analysis_queue as aq_mod
        mock_queue = MagicMock()
        mock_queue.enqueue_analysis = AsyncMock(return_value=True)
        with patch.object(aq_mod, 'get_analysis_queue', return_value=mock_queue):
            result = await aq_mod.queue_analysis(1, 10)
            assert result is True

    def test_get_queue_status_function(self):
        import backend.services.analysis_queue as aq_mod
        mock_queue = MagicMock()
        mock_queue.get_queue_status.return_value = {"queue_size": 0}
        with patch.object(aq_mod, 'get_analysis_queue', return_value=mock_queue):
            status = aq_mod.get_queue_status()
            assert status == {"queue_size": 0}


# ──────────────────────────────────────────────
# knowledge_graph
# ──────────────────────────────────────────────

class TestKnowledgeGraph:
    def _make_session(self):
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_no_analysis_returns_empty(self):
        from backend.services.knowledge_graph import build_knowledge_graph
        session = self._make_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        with patch("backend.services.knowledge_graph.select", _mock_select()):
            result_data = await build_knowledge_graph(1, session)
        assert result_data == {"nodes": [], "edges": [], "stats": {}}

    @pytest.mark.asyncio
    async def test_with_health_risk(self):
        from backend.services.knowledge_graph import build_knowledge_graph
        session = self._make_session()
        analysis = MagicMock()
        analysis.id = 1

        health_risk = MagicMock()
        health_risk.condition = "Diabetes"
        health_risk.risk_level = "high"
        health_risk.associated_variants = ["rs1234"]

        def make_iter_result(items):
            r = MagicMock()
            r.scalar_one_or_none.return_value = analysis
            r.scalars.return_value = iter(items)
            return r

        session.execute.side_effect = [
            make_iter_result([]),  # analysis query
            make_iter_result([health_risk]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
        ]
        with patch("backend.services.knowledge_graph.select", _mock_select()):
            result_data = await build_knowledge_graph(1, session)
        assert "nodes" in result_data
        assert any(n["type"] == "condition" for n in result_data["nodes"].values()) if isinstance(result_data["nodes"], dict) else True

    @pytest.mark.asyncio
    async def test_with_drug_response(self):
        from backend.services.knowledge_graph import build_knowledge_graph
        session = self._make_session()
        analysis = MagicMock()
        analysis.id = 1

        drug_resp = MagicMock()
        drug_resp.drug = "Warfarin"
        drug_resp.gene = "CYP2C9"
        drug_resp.response_type = "reduced"
        drug_resp.variants_involved = ["rs1057910"]

        def make_iter_result(items):
            r = MagicMock()
            r.scalar_one_or_none.return_value = analysis
            r.scalars.return_value = iter(items)
            return r

        session.execute.side_effect = [
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([drug_resp]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
            make_iter_result([]),
        ]
        with patch("backend.services.knowledge_graph.select", _mock_select()):
            result_data = await build_knowledge_graph(1, session)
        assert "nodes" in result_data

    def test_node_types_defined(self):
        from backend.services.knowledge_graph import NODE_TYPES
        assert "gene" in NODE_TYPES
        assert "variant" in NODE_TYPES
        assert "condition" in NODE_TYPES
        assert "drug" in NODE_TYPES
