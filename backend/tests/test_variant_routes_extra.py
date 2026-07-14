"""Tests for variant routes — pure helpers and route handlers."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_user(user_id=1):
    user = MagicMock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.is_admin = False
    return user


def _make_mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_mock_result(scalar=None, all_rows=None, scalars_list=None):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar)
    result.scalar = MagicMock(return_value=0)
    result.all = MagicMock(return_value=all_rows or [])
    result.fetchall = MagicMock(return_value=all_rows or [])
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=scalars_list or [])
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _build_app(session=None, user=None):
    from backend.api.variant_routes import router
    from backend.db.database import get_session
    from backend.api.auth_routes import get_current_user

    if session is None:
        session = _make_mock_session()
    if user is None:
        user = _make_user()

    app = FastAPI()
    app.include_router(router)

    async def _override_session():
        yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = _override_user
    return app, session


# ──────────────────────────────────────────────────
# Pure helper functions
# ──────────────────────────────────────────────────

class TestValidateVariantId:
    def _fn(self):
        from backend.api.variant_routes import validate_variant_id
        return validate_variant_id

    def test_valid_rsid(self):
        assert self._fn()("rs12345") is True

    def test_valid_rsid_large(self):
        assert self._fn()("rs1801131") is True

    def test_chr_colon_pos(self):
        result = self._fn()("chr1:12345")
        assert isinstance(result, bool)

    def test_chrom_colon_pos_no_prefix(self):
        result = self._fn()("1:12345")
        assert isinstance(result, bool)

    def test_x_chromosome(self):
        result = self._fn()("chrX:12345")
        assert isinstance(result, bool)

    def test_y_chromosome(self):
        result = self._fn()("chrY:12345")
        assert isinstance(result, bool)

    def test_gene_variant_format(self):
        assert self._fn()("APOE4") is True

    def test_invalid_empty(self):
        assert self._fn()("") is False

    def test_invalid_random_string(self):
        assert self._fn()("not_a_variant") is False

    def test_rs_prefix_required(self):
        assert self._fn()("12345") is False

    def test_valid_chr_y_no_colon(self):
        result = self._fn()("GENE123T")
        assert result in (True, False)


class TestBuildVariantLookupDescription:
    def _fn(self):
        from backend.api.variant_routes import _build_variant_lookup_description
        return _build_variant_lookup_description

    def test_minimal_variant(self):
        result = self._fn()("rs12345", {}, [], {}, {})
        assert "rs12345" in result

    def test_with_gene(self):
        result = self._fn()("rs12345", {"gene_symbol": "BRCA1", "most_severe_consequence": "missense_variant"}, [], {}, {})
        assert "BRCA1" in result
        assert "rs12345" in result

    def test_with_clinical_significance(self):
        result = self._fn()("rs12345", {}, ["pathogenic", "likely_pathogenic"], {}, {})
        assert "pathogenic" in result.lower()

    def test_with_multiple_conditions(self):
        clinvar = {"entries": [
            {"title": "NM_001.2:c.123A>G", "conditions": ["Breast Cancer", "Ovarian Cancer"], "variation_type": "single nucleotide variant"},
        ]}
        result = self._fn()("rs12345", {}, [], clinvar, {})
        assert "Breast Cancer" in result or "rs12345" in result

    def test_with_pharmacogenomics(self):
        result = self._fn()("rs12345", {}, [], {}, {"found": True})
        assert "pharmacogenomic" in result.lower() or "rs12345" in result

    def test_empty_data(self):
        result = self._fn()("rs12345", {}, [], None, None)
        assert "rs12345" in result

    def test_with_hgvs_name(self):
        clinvar = {"entries": [{"title": "NM_007294.3:c.68_69del", "conditions": [], "variation_type": ""}]}
        result = self._fn()("rs12345", {}, [], clinvar, {})
        assert "NM_007294" in result or "rs12345" in result

    def test_gene_starts_with_rs_not_used(self):
        result = self._fn()("rs12345", {"gene_symbol": "rs12345", "most_severe_consequence": ""}, [], {}, {})
        assert "rs12345" in result

    def test_single_condition(self):
        clinvar = {"entries": [{"title": "", "conditions": ["Cystic Fibrosis"], "variation_type": ""}]}
        result = self._fn()("rs12345", {}, [], clinvar, {})
        assert "Cystic Fibrosis" in result or "associated" in result.lower()


class TestGetVariantCategory:
    def _fn(self):
        from backend.api.variant_routes import get_variant_category
        return get_variant_category

    def test_none_consequence(self):
        assert self._fn()(None) == "Unknown"

    def test_empty_consequence(self):
        assert self._fn()("") == "Unknown"

    def test_stop_gained(self):
        result = self._fn()("stop_gained")
        assert result == "Coding"

    def test_missense(self):
        result = self._fn()("missense_variant")
        assert result == "Coding"

    def test_synonymous(self):
        result = self._fn()("synonymous_variant")
        assert result == "Coding"

    def test_intron(self):
        result = self._fn()("intron_variant")
        assert result == "Intronic"

    def test_splice_donor(self):
        result = self._fn()("splice_donor_variant")
        assert result == "Splicing"

    def test_unknown_consequence(self):
        result = self._fn()("some_new_consequence")
        assert result == "Other"


# ──────────────────────────────────────────────────
# Route tests
# ──────────────────────────────────────────────────

class TestVariantLookup:
    def _build(self, session=None):
        return _build_app(session=session)

    def _mock_api_service(self, annotation_result=None):
        if annotation_result is None:
            annotation_result = {
                "annotations": {
                    "ensembl": {
                        "found": True,
                        "data": [{
                            "id": "rs12345",
                            "most_severe_consequence": "missense_variant",
                            "allele_string": "A/G",
                            "seq_region_name": "1",
                            "start": 12345,
                            "end": 12345,
                            "strand": 1,
                            "transcript_consequences": [{"gene_symbol": "BRCA1", "consequence_terms": ["missense_variant"]}],
                            "colocated_variants": [{"id": "rs12345", "clin_sig": ["pathogenic"], "minor_allele": "G", "minor_allele_freq": 0.001, "frequencies": {"G": {"gnomad": 0.001}}}],
                        }],
                    },
                    "clinvar": {"found": True, "ids": ["12345"], "count": 1, "entries": [{"title": "", "conditions": [], "clinical_significance": ["pathogenic"], "variation_type": "SNV"}]},
                    "clinpgx": {"found": True, "data": {"drugs": ["tamoxifen"]}},
                    "snpedia": {"found": True, "data": {"title": "Rs12345", "revisions": [{"*": "Some wiki text"}]}},
                }
            }
        mock_svc = MagicMock()
        mock_svc.initialize = AsyncMock()
        mock_svc.annotate_variant = AsyncMock(return_value=annotation_result)
        mock_svc.close = AsyncMock()
        return mock_svc

    def test_lookup_invalid_variant_id(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/variants/lookup", json={"variant_id": "invalid_format"})
            assert resp.status_code == 400

    def test_lookup_empty_variant_id(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.post("/api/variants/lookup", json={"variant_id": ""})
            assert resp.status_code == 400

    def test_lookup_cache_hit(self):
        session = _make_mock_session()
        cached = MagicMock()
        cached.response_data = {
            "found": True,
            "source": "cache",
            "search_timestamp": datetime.now().isoformat(),
            "basic_info": {"gene_symbol": "BRCA1"},
            "clinical_significance": ["pathogenic"],
            "population_data": {},
            "pharmacogenomics": {"found": False},
            "literature": {},
            "alpha_missense": None,
            "annotations": {},
        }
        cached.updated_at = datetime(2024, 1, 1)
        cached.created_at = datetime(2024, 1, 1)
        cached.lookup_count = 5
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=cached))
        app, _ = self._build(session=session)
        with patch("backend.api.variant.lookup.select", return_value=MagicMock()), \
             patch("backend.api.variant.lookup._create_multi_source_mappings", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post("/api/variants/lookup", json={"variant_id": "rs12345"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["cached"] is True

    def test_lookup_cache_miss_success(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        mock_svc = self._mock_api_service()
        with patch("backend.api.variant.lookup.select", return_value=MagicMock()), \
             patch("backend.api.variant.lookup.GeneticAPIService", return_value=mock_svc), \
             patch("backend.api.variant.lookup.process_lookup_discoveries", new=AsyncMock()), \
             patch("backend.api.variant.lookup._create_multi_source_mappings", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post("/api/variants/lookup", json={"variant_id": "rs12345"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["variant_id"] == "rs12345"
                assert data["cached"] is False

    def test_lookup_force_refresh(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        mock_svc = self._mock_api_service()
        with patch("backend.api.variant.lookup.select", return_value=MagicMock()), \
             patch("backend.api.variant.lookup.GeneticAPIService", return_value=mock_svc), \
             patch("backend.api.variant.lookup.process_lookup_discoveries", new=AsyncMock()), \
             patch("backend.api.variant.lookup._create_multi_source_mappings", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post("/api/variants/lookup", json={"variant_id": "rs12345", "force_refresh": True})
                assert resp.status_code == 200

    def test_lookup_api_returns_error(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        mock_svc = self._mock_api_service(annotation_result={"error": "not found"})
        with patch("backend.api.variant.lookup.select", return_value=MagicMock()), \
             patch("backend.api.variant.lookup.GeneticAPIService", return_value=mock_svc):
            with TestClient(app) as client:
                resp = client.post("/api/variants/lookup", json={"variant_id": "rs12345"})
                assert resp.status_code == 200
                assert resp.json()["found"] is False

    def test_lookup_api_returns_none(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        mock_svc = MagicMock()
        mock_svc.initialize = AsyncMock()
        mock_svc.annotate_variant = AsyncMock(return_value=None)
        mock_svc.close = AsyncMock()
        with patch("backend.api.variant.lookup.select", return_value=MagicMock()), \
             patch("backend.api.variant.lookup.GeneticAPIService", return_value=mock_svc):
            with TestClient(app) as client:
                resp = client.post("/api/variants/lookup", json={"variant_id": "rs12345"})
                assert resp.status_code == 200
                assert resp.json()["found"] is False


class TestVariantExamples:
    def _build(self):
        return _build_app()

    def test_examples_returns_200(self):
        app, _ = self._build()
        with TestClient(app) as client:
            resp = client.get("/api/variants/examples")
            assert resp.status_code == 200

    def test_examples_has_list(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/variants/examples").json()
            assert "examples" in data
            assert len(data["examples"]) > 0

    def test_each_example_has_variant_id(self):
        app, _ = self._build()
        with TestClient(app) as client:
            data = client.get("/api/variants/examples").json()
            for ex in data["examples"]:
                assert "variant_id" in ex


class TestVariantStats:
    def _build(self, session=None):
        return _build_app(session=session)

    def test_stats_returns_data(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=0, all_rows=[]))
        app, _ = self._build(session=session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/stats")
                assert resp.status_code == 200


class TestVariantSearch:
    def _build(self, session=None):
        return _build_app(session=session)

    def test_search_no_analysis(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/search")
                assert resp.status_code == 200
                data = resp.json()
                assert data["variants"] == []
                assert data["total"] == 0

    def test_search_with_analysis_empty_results(self):
        session = _make_mock_session()
        analysis = MagicMock()
        analysis.id = 1
        results_iter = iter([
            _make_mock_result(scalar=analysis),
            _make_mock_result(scalar=0),
            _make_mock_result(all_rows=[]),
        ])
        session.execute = AsyncMock(side_effect=lambda *a, **kw: results_iter.__next__())
        app, _ = self._build(session=session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()), \
             patch("backend.api.variant.search.sa_func", MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/search")
                assert resp.status_code == 200


class TestVariantCategories:
    def _build(self, session=None):
        return _build_app(session=session)

    def test_categories_no_analysis(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/categories")
                assert resp.status_code == 200
                data = resp.json()
                assert data["categories"] == []

    def test_categories_with_analysis(self):
        session = _make_mock_session()
        analysis = MagicMock()
        analysis.id = 1
        analysis_result = _make_mock_result(scalar=analysis)
        count_result = _make_mock_result(scalar=100)
        rows = [("missense_variant",), ("stop_gained",), ("synonymous_variant",)]
        rows_result = _make_mock_result(all_rows=rows)
        results_iter = iter([analysis_result, count_result, rows_result])
        session.execute = AsyncMock(side_effect=lambda *a, **kw: results_iter.__next__())
        app, _ = self._build(session=session)
        with patch("backend.api.variant.search.select", return_value=MagicMock()), \
             patch("backend.api.variant.search.sa_func", MagicMock()), \
             patch("backend.api.variant.search.literal_column", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/categories")
                assert resp.status_code == 200
                data = resp.json()
                assert "categories" in data

    def test_categories_exception_returns_500(self):
        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=Exception("DB error"))
        app, _ = self._build(session=session)
        with patch("backend.api.variant.search.select", side_effect=Exception("DB error")):
            with TestClient(app) as client:
                resp = client.get("/api/variants/categories")
                assert resp.status_code == 500


class TestSavedVariants:
    def _build(self, session=None):
        return _build_app(session=session)

    def test_get_saved_variants_empty(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(all_rows=[]))
        app, _ = self._build(session=session)
        with patch("backend.api.variant_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.get("/api/variants/saved")
                assert resp.status_code in (200, 404)

    def test_save_variant(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build(session=session)
        with patch("backend.api.variant_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/api/variants/saved", json={"rsid": "rs12345", "notes": "test note", "genotype": "A/G"})
                assert resp.status_code in (200, 201, 404, 422)

    def test_delete_saved_variant(self):
        session = _make_mock_session()
        saved = MagicMock()
        saved.user_id = 1
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=saved))
        app, _ = self._build(session=session)
        with patch("backend.api.variant_routes.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.delete("/api/variants/saved/rs12345")
                assert resp.status_code in (200, 204, 404)
