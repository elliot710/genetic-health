"""Tests for pure helper functions in annotation_coordinator.py."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# _truthy_data
# ---------------------------------------------------------------------------

class TestTruthyData:
    def _fn(self):
        from backend.services.annotation_coordinator import _truthy_data
        return _truthy_data

    def test_returns_dict_when_found_true(self):
        fn = self._fn()
        d = {'found': True, 'data': 'x'}
        assert fn(d) is d

    def test_returns_none_when_found_false(self):
        fn = self._fn()
        assert fn({'found': False}) is None

    def test_returns_none_when_none_input(self):
        fn = self._fn()
        assert fn(None) is None

    def test_returns_none_when_empty_dict(self):
        fn = self._fn()
        assert fn({}) is None

    def test_returns_none_when_found_missing(self):
        fn = self._fn()
        assert fn({'data': 'x'}) is None

    def test_returns_none_when_falsy_list(self):
        fn = self._fn()
        assert fn([]) is None

    def test_truthy_dict_without_found_key_returns_none(self):
        fn = self._fn()
        assert fn({'rsid': 'rs1', 'score': 0.9}) is None


# ---------------------------------------------------------------------------
# _build_annotation_link_values
# ---------------------------------------------------------------------------

class TestBuildAnnotationLinkValues:
    def _fn(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        return _build_annotation_link_values

    def _make_variant(self, vid):
        v = MagicMock()
        v.id = vid
        return v

    def test_builds_one_link_per_variant(self):
        fn = self._fn()
        v1 = self._make_variant(101)
        rsid_to_variants = {'rs1': [v1]}
        rsid_to_shared_id = {'rs1': 55}
        result = fn(rsid_to_variants, ['rs1'], rsid_to_shared_id, analysis_id=7)
        assert len(result) == 1
        link = result[0]
        assert link['analysis_id'] == 7
        assert link['analysis_variant_id'] == 101
        assert link['shared_annotation_id'] == 55
        assert link['rsid'] == 'rs1'

    def test_builds_multiple_links_for_multiple_variants(self):
        fn = self._fn()
        v1 = self._make_variant(10)
        v2 = self._make_variant(11)
        rsid_to_variants = {'rs1': [v1, v2]}
        rsid_to_shared_id = {'rs1': 99}
        result = fn(rsid_to_variants, ['rs1'], rsid_to_shared_id, analysis_id=1)
        assert len(result) == 2
        ids = {r['analysis_variant_id'] for r in result}
        assert ids == {10, 11}

    def test_skips_rsid_missing_from_shared_id_map(self):
        fn = self._fn()
        v1 = self._make_variant(1)
        rsid_to_variants = {'rs_missing': [v1]}
        rsid_to_shared_id = {}
        result = fn(rsid_to_variants, ['rs_missing'], rsid_to_shared_id, analysis_id=1)
        assert result == []

    def test_only_processes_chunk_rsids(self):
        fn = self._fn()
        v1 = self._make_variant(1)
        v2 = self._make_variant(2)
        rsid_to_variants = {'rs1': [v1], 'rs2': [v2]}
        rsid_to_shared_id = {'rs1': 10, 'rs2': 20}
        result = fn(rsid_to_variants, ['rs1'], rsid_to_shared_id, analysis_id=5)
        assert len(result) == 1
        assert result[0]['rsid'] == 'rs1'

    def test_empty_chunk_rsids_returns_empty(self):
        fn = self._fn()
        rsid_to_variants = {'rs1': [self._make_variant(1)]}
        rsid_to_shared_id = {'rs1': 10}
        result = fn(rsid_to_variants, [], rsid_to_shared_id, analysis_id=1)
        assert result == []

    def test_multiple_rsids_multiple_variants(self):
        fn = self._fn()
        rsid_to_variants = {
            'rs1': [self._make_variant(1), self._make_variant(2)],
            'rs2': [self._make_variant(3)],
        }
        rsid_to_shared_id = {'rs1': 10, 'rs2': 20}
        result = fn(rsid_to_variants, ['rs1', 'rs2'], rsid_to_shared_id, analysis_id=3)
        assert len(result) == 3
        rsids = [r['rsid'] for r in result]
        assert rsids.count('rs1') == 2
        assert rsids.count('rs2') == 1


# ---------------------------------------------------------------------------
# _insert_annotation_links (async)
# ---------------------------------------------------------------------------

class TestInsertAnnotationLinks:
    @pytest.mark.asyncio
    async def test_skips_when_empty_links(self):
        from backend.services.annotation_coordinator import _insert_annotation_links
        session = AsyncMock()
        await _insert_annotation_links(session, [])
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_with_link_values(self):
        from backend.services.annotation_coordinator import _insert_annotation_links
        session = AsyncMock()
        links = [{'analysis_id': 1, 'analysis_variant_id': 10,
                  'shared_annotation_id': 5, 'rsid': 'rs1'}]
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
        with patch('sqlalchemy.dialects.postgresql.insert', return_value=mock_stmt):
            await _insert_annotation_links(session, links)
        session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# _fetch_remote_api_data (async)
# ---------------------------------------------------------------------------

class TestFetchRemoteApiData:
    @pytest.mark.asyncio
    async def test_empty_rsids_returns_empty(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data
        result = await _fetch_remote_api_data([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_maps_clinvar_to_clinvar_key(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data

        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            'rs1', {'sig': 'Pathogenic'}, None, None, None
        ][i]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row])))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch('backend.services.annotation_coordinator.async_session_factory', return_value=mock_ctx):
            result = await _fetch_remote_api_data(['rs1'])

        assert 'rs1' in result
        assert 'clinvar' in result['rs1']

    @pytest.mark.asyncio
    async def test_maps_pharmgkb_to_clinpgx_key(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data

        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            'rs2', None, {'drug': 'warfarin'}, None, None
        ][i]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row])))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch('backend.services.annotation_coordinator.async_session_factory', return_value=mock_ctx):
            result = await _fetch_remote_api_data(['rs2'])

        assert 'rs2' in result
        assert 'clinpgx' in result['rs2']

    @pytest.mark.asyncio
    async def test_excludes_row_with_all_null_columns(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data

        # Row with nothing non-null → should not appear in result_map
        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            'rs3', None, None, None, None
        ][i]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row])))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch('backend.services.annotation_coordinator.async_session_factory', return_value=mock_ctx):
            result = await _fetch_remote_api_data(['rs3'])

        # row has all-null remote cols → not included
        assert 'rs3' not in result

    @pytest.mark.asyncio
    async def test_maps_snpedia_key(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data

        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            'rs4', None, None, {'summary': 'text'}, None
        ][i]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row])))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch('backend.services.annotation_coordinator.async_session_factory', return_value=mock_ctx):
            result = await _fetch_remote_api_data(['rs4'])

        assert 'rs4' in result
        assert 'snpedia' in result['rs4']

    @pytest.mark.asyncio
    async def test_maps_litvar_key(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data

        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            'rs5', None, None, None, {'count': 3}
        ][i]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[row])))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch('backend.services.annotation_coordinator.async_session_factory', return_value=mock_ctx):
            result = await _fetch_remote_api_data(['rs5'])

        assert 'rs5' in result
        assert 'litvar' in result['rs5']
