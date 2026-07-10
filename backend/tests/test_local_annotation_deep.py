"""Deep tests for local_annotation module."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_variant(rsid, chrom="1", pos=12345, ref="A", alt="G"):
    v = MagicMock()
    v.rsid = rsid
    marker = MagicMock()
    marker.chromosome = chrom
    marker.position = pos
    marker.ref_allele = ref
    marker.alt_alleles = alt
    v.marker = marker
    return v


class TestCountFound:
    def _fn(self):
        from backend.services.local_annotation import _count_found
        return _count_found

    def test_empty_dict(self):
        assert self._fn()({}) == 0

    def test_all_found(self):
        d = {
            "rs1": {"found": True},
            "rs2": {"found": True},
        }
        assert self._fn()(d) == 2

    def test_mixed(self):
        d = {
            "rs1": {"found": True},
            "rs2": {"found": False},
            "rs3": None,
            "rs4": {},
        }
        assert self._fn()(d) == 1

    def test_none_values(self):
        d = {"rs1": None, "rs2": None}
        assert self._fn()(d) == 0

    def test_found_false(self):
        d = {"rs1": {"found": False}}
        assert self._fn()(d) == 0


class TestRsidsFor:
    def _fn(self):
        from backend.services.local_annotation import _rsids_for
        return _rsids_for

    def test_no_per_source(self):
        rsids = ["rs1", "rs2", "rs3"]
        result = self._fn()("clinvar_local", rsids, None)
        assert result == rsids

    def test_per_source_with_key(self):
        per_source = {"clinvar_local": ["rs1", "rs2"], "gnomad": ["rs3"]}
        result = self._fn()("clinvar_local", ["rs1", "rs2", "rs3"], per_source)
        assert result == ["rs1", "rs2"]

    def test_per_source_missing_key(self):
        per_source = {"gnomad": ["rs3"]}
        result = self._fn()("clinvar_local", ["rs1", "rs2"], per_source)
        assert result == []

    def test_per_source_empty_list(self):
        per_source = {"clinvar_local": []}
        result = self._fn()("clinvar_local", ["rs1", "rs2"], per_source)
        assert result == []


class TestBuildPosTuples:
    def _fn(self):
        from backend.services.local_annotation import _build_pos_tuples
        return _build_pos_tuples

    def test_empty_rsids(self):
        result = self._fn()([], {})
        assert result == []

    def test_rsid_not_in_map(self):
        result = self._fn()(["rs1"], {})
        assert result == []

    def test_variant_with_no_marker(self):
        v = MagicMock()
        v.marker = None
        result = self._fn()(["rs1"], {"rs1": v})
        assert result == []

    def test_variant_with_marker(self):
        v = _make_variant("rs1", chrom="1", pos=12345, ref="A", alt="G")
        result = self._fn()(["rs1"], {"rs1": v})
        assert len(result) == 1
        assert result[0][0] == "rs1"

    def test_multiple_variants(self):
        v1 = _make_variant("rs1", chrom="1", pos=100, ref="A", alt="G")
        v2 = _make_variant("rs2", chrom="2", pos=200, ref="C", alt="T")
        result = self._fn()(["rs1", "rs2"], {"rs1": v1, "rs2": v2})
        assert len(result) == 2


class TestBuildRsidVariantMap:
    def _fn(self):
        from backend.services.local_annotation import build_rsid_variant_map
        return build_rsid_variant_map

    def test_empty_list(self):
        assert self._fn()([]) == {}

    def test_single_variant(self):
        v = MagicMock()
        v.rsid = "rs12345"
        result = self._fn()([v])
        assert "rs12345" in result
        assert result["rs12345"] is v

    def test_filters_none_rsid(self):
        v1 = MagicMock()
        v1.rsid = "rs1"
        v2 = MagicMock()
        v2.rsid = None
        result = self._fn()([v1, v2])
        assert len(result) == 1
        assert "rs1" in result

    def test_deduplicates_rsids(self):
        v1 = MagicMock()
        v1.rsid = "rs1"
        v2 = MagicMock()
        v2.rsid = "rs1"
        result = self._fn()([v1, v2])
        assert len(result) == 1


class TestBuildGnomadPosTuples:
    def _fn(self):
        from backend.services.local_annotation import build_gnomad_pos_tuples
        return build_gnomad_pos_tuples

    def test_delegates_to_build_pos_tuples(self):
        v = _make_variant("rs1")
        result = self._fn()(["rs1"], {"rs1": v})
        assert isinstance(result, list)

    def test_empty(self):
        assert self._fn()([], {}) == []


class TestBuildAmBatch:
    def _fn(self):
        from backend.services.local_annotation import build_am_batch
        return build_am_batch

    def test_empty(self):
        result = self._fn()([], {})
        assert result == []

    def test_with_variant(self):
        v = _make_variant("rs1", chrom="1", pos=100, ref="A", alt="G")
        result = self._fn()(["rs1"], {"rs1": v})
        assert isinstance(result, list)


class TestApplyPositionFallback:
    @pytest.mark.asyncio
    async def test_no_position_fallback_method(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock(spec=[])
        result_dict = {"rs1": None}
        await _apply_position_fallback(svc, ["rs1"], result_dict, {})

    @pytest.mark.asyncio
    async def test_no_misses(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock()
        svc.lookup_batch_by_position = AsyncMock(return_value={})
        result_dict = {"rs1": {"found": True}}
        await _apply_position_fallback(svc, ["rs1"], result_dict, {})
        svc.lookup_batch_by_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_miss_no_pos_tuples(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock()
        svc.lookup_batch_by_position = AsyncMock(return_value={})
        result_dict = {"rs1": None}
        rsid_to_variant = {"rs1": MagicMock(marker=None)}
        await _apply_position_fallback(svc, ["rs1"], result_dict, rsid_to_variant)

    @pytest.mark.asyncio
    async def test_with_miss_and_pos_result(self):
        from backend.services.local_annotation import _apply_position_fallback
        svc = MagicMock()
        svc.lookup_batch_by_position = AsyncMock(return_value={"rs1": {"found": True, "af": 0.01}})
        result_dict = {"rs1": None}
        v = _make_variant("rs1")
        rsid_to_variant = {"rs1": v}
        await _apply_position_fallback(svc, ["rs1"], result_dict, rsid_to_variant)
        assert result_dict["rs1"]["found"] is True


class TestRunAllLookups:
    def _make_mock_service(self, batch_return=None):
        svc = MagicMock()
        svc.is_loaded = True
        svc.available = True
        svc.has_pg_data = False
        svc.indexed_count = 0
        svc.lookup_batch_uses_tabix = False
        svc.lookup_batch = AsyncMock(return_value=batch_return or {})
        svc.lookup_batch_by_position = AsyncMock(return_value={})
        return svc

    @pytest.mark.asyncio
    async def test_empty_rsids(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        result = await run_all_lookups(sources, [], {})
        assert hasattr(result, 'clinvar')

    @pytest.mark.asyncio
    async def test_with_clinvar_source(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        clinvar_svc = self._make_mock_service({"rs1": {"found": True, "genes": ["BRCA1"]}})
        sources.clinvar = clinvar_svc
        v = _make_variant("rs1")
        result = await run_all_lookups(sources, ["rs1"], {"rs1": v})
        clinvar_svc.lookup_batch.assert_called_once_with(["rs1"])
        assert result.clinvar.get("rs1", {}).get("found") is True

    @pytest.mark.asyncio
    async def test_with_gnomad_source(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        gnomad_svc = self._make_mock_service({"rs1": {"found": True, "af": 0.01}})
        sources.gnomad = gnomad_svc
        v = _make_variant("rs1")
        result = await run_all_lookups(sources, ["rs1"], {"rs1": v})
        gnomad_svc.lookup_batch.assert_called_once_with(["rs1"])

    @pytest.mark.asyncio
    async def test_with_gnomad_v2_source_not_found(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        gnomad_svc = self._make_mock_service({"rs1": {"found": False}})
        sources.gnomad = gnomad_svc
        gnomad_v2_svc = self._make_mock_service()
        gnomad_v2_svc.has_pg_data = True
        gnomad_v2_svc.batch_lookup_pg = AsyncMock(return_value={"rs1": {"af_nfe": 0.01}})
        sources.gnomad_v2 = gnomad_v2_svc
        v = _make_variant("rs1")
        result = await run_all_lookups(sources, ["rs1"], {"rs1": v})
        assert result.gnomad["rs1"]["found"] is True
        assert result.gnomad["rs1"]["source"] == "gnomad_v2_exome"
        assert result.gnomad["rs1"]["af"] == 0.01

    @pytest.mark.asyncio
    async def test_with_ensembl_source(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        ensembl_svc = self._make_mock_service({"rs1": {"found": True, "data": []}})
        sources.ensembl_vep = ensembl_svc
        v = _make_variant("rs1")
        result = await run_all_lookups(sources, ["rs1"], {"rs1": v})
        ensembl_svc.lookup_batch.assert_called_once_with(["rs1"])

    @pytest.mark.asyncio
    async def test_with_all_sources(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        sources.clinvar = self._make_mock_service({"rs1": {"found": True}})
        sources.gnomad = self._make_mock_service({"rs1": {"found": True, "af": 0.01}})
        sources.ensembl_vep = self._make_mock_service({"rs1": {"found": True}})
        sources.thousand_genomes = self._make_mock_service({"rs1": {"found": True}})
        am_svc = MagicMock()
        am_svc.available = True
        am_svc.lookup = MagicMock(return_value={"found": True, "am_class": "benign"})
        sources.alpha_missense = am_svc
        gtx_svc = MagicMock()
        gtx_svc.available = True
        gtx_svc.lookup_batch = AsyncMock(return_value={"rs1": {"found": True}})
        sources.gnomad_tx = gtx_svc
        v = _make_variant("rs1")
        result = await run_all_lookups(sources, ["rs1"], {"rs1": v})
        assert result is not None

    @pytest.mark.asyncio
    async def test_with_per_source_rsids(self):
        from backend.services.local_annotation import run_all_lookups, LoadedSources
        sources = LoadedSources()
        clinvar_svc = self._make_mock_service()
        sources.clinvar = clinvar_svc
        per_source = {"clinvar_local": ["rs1"], "gnomad": []}
        v = _make_variant("rs1")
        result = await run_all_lookups(sources, ["rs1"], {"rs1": v}, per_source_rsids=per_source)
        clinvar_svc.lookup_batch.assert_called_once_with(["rs1"])


class TestLoadLocalSources:
    @pytest.mark.asyncio
    async def test_load_empty_enabled(self):
        with patch("backend.services.local_annotation.get_clinvar_direct_service", create=True) as m1, \
             patch("backend.services.local_annotation.get_gnomad_service", create=True) as m2, \
             patch("backend.services.local_annotation.get_ensembl_vep_service", create=True) as m3, \
             patch("backend.services.local_annotation.get_thousand_genomes_direct_service", create=True) as m4, \
             patch("backend.services.local_annotation.get_alpha_missense_service", create=True) as m5, \
             patch("backend.services.local_annotation.get_gnomad_tx_service", create=True) as m6, \
             patch("backend.services.local_annotation.get_gnomad_v2_service", create=True) as m7, \
             patch("backend.services.local_annotation.get_alphafold_local_service", create=True) as m8:

            for mock in [m1, m2, m3, m4, m7]:
                svc = MagicMock()
                svc.is_loaded = False
                svc.ensure_loaded = AsyncMock()
                svc.is_loaded = False
                mock.return_value = svc

            for mock in [m5, m6]:
                svc = MagicMock()
                svc.available = False
                mock.return_value = svc

            m8_svc = MagicMock()
            m8_svc.available = False
            m8.return_value = m8_svc

            from backend.services.local_annotation import load_local_sources
            sources = await load_local_sources([])
            assert sources is not None

    @pytest.mark.asyncio
    async def test_load_with_specific_sources(self):
        with patch("backend.services.local_annotation.get_clinvar_direct_service", create=True) as m1, \
             patch("backend.services.local_annotation.get_gnomad_service", create=True) as m2, \
             patch("backend.services.local_annotation.get_gnomad_v2_service", create=True) as m3:

            for mock in [m1, m2, m3]:
                svc = MagicMock()
                svc.is_loaded = True
                svc.ensure_loaded = AsyncMock()
                svc.has_pg_data = False
                svc.indexed_count = 10
                mock.return_value = svc

            from backend.services.local_annotation import load_local_sources
            sources = await load_local_sources(["clinvar_local", "gnomad"])
            assert sources is not None


class TestLoadedSources:
    def test_active_names_empty(self):
        from backend.services.local_annotation import LoadedSources
        sources = LoadedSources()
        names = sources.active_names
        assert isinstance(names, list)
        assert len(names) == 0

    def test_active_names_with_clinvar(self):
        from backend.services.local_annotation import LoadedSources
        sources = LoadedSources()
        sources.clinvar = MagicMock()
        names = sources.active_names
        assert "clinvar_local" in names

    def test_active_names_with_all(self):
        from backend.services.local_annotation import LoadedSources
        sources = LoadedSources()
        sources.clinvar = MagicMock()
        sources.gnomad = MagicMock()
        sources.ensembl_vep = MagicMock()
        sources.thousand_genomes = MagicMock()
        sources.alpha_missense = MagicMock()
        sources.gnomad_tx = MagicMock()
        sources.alphafold = MagicMock()
        names = sources.active_names
        assert "clinvar_local" in names
        assert "gnomad" in names
        assert "ensembl" in names
        assert "thousand_genomes" in names
        assert "alpha_missense" in names
        assert "gnomad_tx" in names
        assert "alphafold" in names
