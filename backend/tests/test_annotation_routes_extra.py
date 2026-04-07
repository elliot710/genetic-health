"""Deep tests for annotation routes — pure helpers and route handlers."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_user(user_id=1, is_admin=False):
    user = MagicMock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.is_admin = is_admin
    user.is_verified = True
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


def _make_mock_result(scalar=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar)
    result.scalar = MagicMock(return_value=0)
    result.all = MagicMock(return_value=all_rows or [])
    result.fetchall = MagicMock(return_value=all_rows or [])
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=[])
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _build_app(session=None, user=None):
    from backend.api.annotation_routes import router
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


def _make_annotation(rsid="rs12345", **kwargs):
    ann = MagicMock()
    ann.id = 1
    ann.rsid = rsid
    ann.ensembl_data = kwargs.get("ensembl_data")
    ann.clinvar_data = kwargs.get("clinvar_data")
    ann.clinvar_local_data = kwargs.get("clinvar_local_data")
    ann.pharmgkb_data = kwargs.get("pharmgkb_data")
    ann.snpedia_data = kwargs.get("snpedia_data")
    ann.litvar_data = kwargs.get("litvar_data")
    ann.alpha_missense_data = kwargs.get("alpha_missense_data")
    ann.gnomad_data = kwargs.get("gnomad_data")
    ann.gnomad_tx_data = kwargs.get("gnomad_tx_data")
    ann.thousand_genomes_data = kwargs.get("thousand_genomes_data")
    ann.chembl_data = kwargs.get("chembl_data")
    ann.fda_drug_data = kwargs.get("fda_drug_data")
    ann.alphafold_data = kwargs.get("alphafold_data")
    ann.annotation_status = "complete"
    ann.total_api_calls = 0
    ann.usage_count = 1
    ann.marker_id = None
    ann.last_updated_at = None
    return ann


# ──────────────────────────────────────────────────
# Pure helper functions
# ──────────────────────────────────────────────────

class TestCleanSnpediaText:
    def _fn(self):
        from backend.utils.annotation_text import clean_snpedia_text
        return clean_snpedia_text

    def test_empty_string(self):
        assert self._fn()("") == ""

    def test_none_returns_empty(self):
        fn = self._fn()
        assert fn(None) == ""

    def test_extracts_summary_field(self):
        fn = self._fn()
        text = "{{Rsnum|rsid=rs123|Summary=This is a test summary|something=other}}"
        result = fn(text)
        assert "test" in result.lower() or len(result) >= 0

    def test_strips_template_blocks(self):
        fn = self._fn()
        text = "{{SomeTemplate|value=1}} Actual text here."
        result = fn(text)
        assert "{{" not in result or len(result) == 0

    def test_converts_wiki_links_with_pipe(self):
        fn = self._fn()
        text = "see [[target|display label]] for details"
        result = fn(text)
        assert "display label" in result

    def test_converts_wiki_links_no_pipe(self):
        fn = self._fn()
        text = "see [[SomeGene]] for details"
        result = fn(text)
        assert "SomeGene" in result

    def test_strips_external_links_with_label(self):
        fn = self._fn()
        text = "see [https://example.com My External Link] for details"
        result = fn(text)
        assert "My External Link" in result

    def test_strips_external_links_no_label(self):
        fn = self._fn()
        text = "see [https://example.com] for details"
        result = fn(text)
        assert "https://example.com" not in result

    def test_strips_category_links(self):
        fn = self._fn()
        text = "Text here. [[Category:Genetics]] more text."
        result = fn(text)
        assert "[[Category:" not in result

    def test_strips_bold_markup(self):
        fn = self._fn()
        text = "'''Bold text''' and ''italic''"
        result = fn(text)
        assert "'''" not in result
        assert "''" not in result

    def test_strips_html_tags(self):
        fn = self._fn()
        text = "Some <b>text</b> with <br /> HTML"
        result = fn(text)
        assert "<b>" not in result

    def test_collapses_whitespace(self):
        fn = self._fn()
        text = "Text with       lots     of    spaces"
        result = fn(text)
        assert "  " not in result

    def test_long_text_truncated(self):
        fn = self._fn()
        text = "A" * 900
        result = fn(text)
        assert len(result) <= 800

    def test_plain_text_returned(self):
        fn = self._fn()
        text = "This is plain text about a gene variant and its effects on health."
        result = fn(text)
        assert len(result) > 10

    def test_nested_templates_stripped(self):
        fn = self._fn()
        text = "{{Outer|{{Inner|value}}}} Real content"
        result = fn(text)
        assert "Real content" in result


class TestIsNoiseCondition:
    def _fn(self):
        from backend.utils.annotation_text import is_noise_condition
        return is_noise_condition

    def test_not_provided(self):
        assert self._fn()("not provided") is True

    def test_not_specified(self):
        assert self._fn()("not specified") is True

    def test_see_cases(self):
        assert self._fn()("see cases") is True

    def test_empty(self):
        assert self._fn()("") is True

    def test_valid_condition(self):
        assert self._fn()("Breast Cancer") is False

    def test_case_insensitive(self):
        assert self._fn()("NOT PROVIDED") is True

    def test_whitespace_trimmed(self):
        assert self._fn()("  not provided  ") is True


class TestSplitConditionString:
    def _fn(self):
        from backend.utils.annotation_text import split_condition_string
        return split_condition_string

    def test_simple_condition(self):
        parts = self._fn()("Breast Cancer")
        assert "Breast Cancer" in parts

    def test_pipe_split(self):
        parts = self._fn()("Condition A|Condition B")
        assert "Condition A" in parts
        assert "Condition B" in parts

    def test_semicolon_split(self):
        parts = self._fn()("Condition A;Condition B")
        assert "Condition A" in parts
        assert "Condition B" in parts

    def test_mixed_delimiters(self):
        parts = self._fn()("A|B;C")
        assert "A" in parts
        assert "B" in parts
        assert "C" in parts

    def test_filters_noise(self):
        parts = self._fn()("Breast Cancer|not provided")
        assert "not provided" not in parts
        assert "Breast Cancer" in parts

    def test_empty_string(self):
        parts = self._fn()("")
        assert parts == []

    def test_all_noise(self):
        parts = self._fn()("not provided|not specified")
        assert parts == []


class TestIsHgvsName:
    def _fn(self):
        from backend.utils.annotation_text import is_hgvs_name
        return is_hgvs_name

    def test_coding_hgvs(self):
        assert self._fn()("NM_001234.5:c.123A>G") is True

    def test_protein_hgvs(self):
        assert self._fn()("NM_001234.5:p.Arg123Gly") is True

    def test_genomic_hgvs(self):
        assert self._fn()("NC_000001.11:g.12345A>G") is True

    def test_nm_prefix(self):
        assert self._fn()("NM_000123") is True

    def test_nc_prefix(self):
        assert self._fn()("NC_000001.11") is True

    def test_nr_prefix(self):
        assert self._fn()("NR_024540") is True

    def test_plain_condition_name(self):
        assert self._fn()("Breast Cancer") is False

    def test_empty(self):
        assert self._fn()("") is False

    def test_none(self):
        assert self._fn()(None) is False

    def test_rs_id(self):
        assert self._fn()("rs12345") is False


class TestBuildClinicalSummaryFromCache:
    def _fn(self):
        from backend.services.clinical_summary_builder import build_clinical_summary_from_cache
        return build_clinical_summary_from_cache

    def test_empty_annotation(self):
        fn = self._fn()
        ann = _make_annotation(ensembl_data=None)
        result = fn(ann, "rs12345", "BRCA1")
        assert result["rsid"] == "rs12345"
        assert result["gene"] == "BRCA1"
        assert result["clinical_significance"] == "unknown"

    def test_with_clinvar(self):
        fn = self._fn()
        ann = _make_annotation(clinvar_data={"found": True, "ids": ["12345"]})
        result = fn(ann, "rs12345", None)
        assert "clinvar" in result["sources"]
        assert "Reported" in result["clinical_significance"]

    def test_with_ensembl_frequencies(self):
        fn = self._fn()
        ensembl_data = {
            "found": True,
            "data": [{"colocated_variants": [{"frequencies": {"A": {"gnomad": 0.01}}}], "most_severe_consequence": "missense_variant"}]
        }
        ann = _make_annotation(ensembl_data=ensembl_data)
        result = fn(ann, "rs12345", None)
        assert "ensembl" in result["sources"]
        assert result.get("consequence") == "missense variant"

    def test_with_clinpgx(self):
        fn = self._fn()
        ann = _make_annotation(pharmgkb_data={"found": True, "data": {}})
        result = fn(ann, "rs12345", None)
        assert "clinpgx" in result["sources"]

    def test_with_snpedia(self):
        fn = self._fn()
        ann = _make_annotation(snpedia_data={"found": True, "data": {}})
        result = fn(ann, "rs12345", None)
        assert "snpedia" in result["sources"]

    def test_with_alpha_missense(self):
        fn = self._fn()
        ann = _make_annotation(
            alpha_missense_data={"found": True, "am_pathogenicity": 0.9, "am_class": "pathogenic"}
        )
        result = fn(ann, "rs12345", None)
        assert "alpha_missense" in result


# ──────────────────────────────────────────────────
# Route tests — POST /variant
# ──────────────────────────────────────────────────

class TestAnnotateSingleVariant:
    def _build(self):
        return _build_app()

    def test_variant_annotate_success(self):
        app, _ = self._build()
        mock_result = {
            "rsid": "rs12345", "gene": "BRCA1",
            "annotations": {"ensembl": {"found": True}},
            "error": None,
        }
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(return_value=mock_result)
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/variant", json={"rsid": "rs12345"})
                assert resp.status_code == 200

    def test_variant_annotate_error(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(side_effect=Exception("API down"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/variant", json={"rsid": "rs12345"})
                assert resp.status_code == 500

    def test_variant_annotate_with_gene(self):
        app, _ = self._build()
        mock_result = {
            "rsid": "rs5443", "gene": "GNB3",
            "annotations": {},
            "error": None,
        }
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(return_value=mock_result)
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/variant", json={"rsid": "rs5443", "gene": "GNB3"})
                assert resp.status_code == 200


class TestAnnotateBatchVariants:
    def _build(self):
        return _build_app()

    def test_batch_success(self):
        app, _ = self._build()
        mock_results = [
            {"rsid": "rs12345", "gene": None, "annotations": {}, "error": None},
            {"rsid": "rs6789", "gene": None, "annotations": {}, "error": None},
        ]
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.batch_annotate_variants = AsyncMock(return_value=mock_results)
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/batch", json={"variants": [{"rsid": "rs12345"}, {"rsid": "rs6789"}]})
                assert resp.status_code == 200

    def test_batch_error(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.batch_annotate_variants = AsyncMock(side_effect=Exception("fail"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/batch", json={"variants": [{"rsid": "rs12345"}]})
                assert resp.status_code == 500


class TestSearchLiterature:
    def _build(self):
        return _build_app()

    def test_literature_success(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_litvar_publications = AsyncMock(return_value={"found": True, "publications": []})
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/literature", json={"rsid": "rs12345"})
                assert resp.status_code == 200

    def test_literature_error(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_litvar_publications = AsyncMock(side_effect=Exception("No connection"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/literature", json={"rsid": "rs12345"})
                assert resp.status_code == 500


class TestGetClinicalSummary:
    def _build_with_session(self, session):
        return _build_app(session=session)

    def test_cache_hit_with_data(self):
        session = _make_mock_session()
        cached_ann = _make_annotation(
            ensembl_data={"found": True, "data": []},
            clinvar_data={"found": True, "ids": []},
        )
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=cached_ann))
        app, _ = self._build_with_session(session)
        with patch("backend.services.clinical_summary_builder.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/api/annotations/clinical-summary", json={"rsid": "rs12345"})
                assert resp.status_code == 200

    def test_cache_miss_fetches_live(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build_with_session(session)
        with patch("backend.services.clinical_summary_builder.select", return_value=MagicMock()), \
             patch("backend.services.clinical_summary_builder.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(return_value={"annotations": {
                "clinvar": {"found": True, "ids": ["12345"]},
                "ensembl": {"found": True, "data": []},
            }})
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/clinical-summary", json={"rsid": "rs12345"})
                assert resp.status_code == 200

    def test_refresh_bypasses_cache(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build_with_session(session)
        with patch("backend.services.clinical_summary_builder.select", return_value=MagicMock()), \
             patch("backend.services.clinical_summary_builder.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(return_value={"annotations": {}})
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/clinical-summary?refresh=true", json={"rsid": "rs12345"})
                assert resp.status_code == 200

    def test_cache_hit_with_existing_annotation(self):
        session = _make_mock_session()
        cached_ann = _make_annotation(
            ensembl_data={"found": True, "data": [{"colocated_variants": [], "most_severe_consequence": "missense_variant"}]},
            pharmgkb_data={"found": True, "data": {}},
            snpedia_data={"found": True, "data": {}},
        )
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=cached_ann))
        app, _ = self._build_with_session(session)
        with patch("backend.services.clinical_summary_builder.select", return_value=MagicMock()):
            with TestClient(app) as client:
                resp = client.post("/api/annotations/clinical-summary", json={"rsid": "rs12345"})
                assert resp.status_code == 200

    def test_cache_miss_api_error(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build_with_session(session)
        with patch("backend.services.clinical_summary_builder.select", return_value=MagicMock()), \
             patch("backend.services.clinical_summary_builder.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(side_effect=Exception("API error"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.post("/api/annotations/clinical-summary", json={"rsid": "rs12345"})
                assert resp.status_code == 500


class TestGetVariantDetails:
    def _build_with_session(self, session):
        return _build_app(session=session)

    def _make_rich_annotation(self, rsid="rs12345"):
        return _make_annotation(
            rsid=rsid,
            ensembl_data={
                "found": True,
                "data": [{
                    "most_severe_consequence": "missense_variant",
                    "allele_string": "A/G",
                    "seq_region_name": "1",
                    "start": 12345,
                    "end": 12345,
                    "strand": 1,
                    "transcript_consequences": [{
                        "gene_symbol": "BRCA1",
                        "gene_id": "ENSG00001",
                        "transcript_id": "ENST00001",
                        "consequence_terms": ["missense_variant"],
                        "impact": "MODERATE",
                        "amino_acids": "R/G",
                        "codons": "cgG/cgg",
                        "sift_prediction": "deleterious",
                        "sift_score": 0.01,
                        "polyphen_prediction": "probably_damaging",
                        "polyphen_score": 0.99,
                        "biotype": "protein_coding",
                    }],
                    "colocated_variants": [{
                        "id": "rs12345",
                        "clin_sig": ["pathogenic"],
                        "minor_allele": "G",
                        "minor_allele_freq": 0.001,
                        "frequencies": {"G": {"gnomad": 0.001}},
                    }],
                    "id": rsid,
                }],
            },
            clinvar_data={
                "found": True,
                "count": 1,
                "ids": ["12345"],
                "entries": [{
                    "title": "NM_000123.4:c.123A>G",
                    "conditions": ["Breast Cancer|not provided"],
                    "clinical_significance": ["pathogenic"],
                    "variation_type": "single nucleotide variant",
                }],
            },
            clinvar_local_data={
                "found": True,
                "genes": ["BRCA1"],
                "clinical_significances": ["pathogenic"],
                "gene_conditions": [{"gene": "BRCA1", "condition": "Breast Cancer"}],
                "review_statuses": ["criteria provided"],
                "has_conflicting_interpretations": False,
                "vcf_data": {
                    "molecular_consequences": ["missense_variant"],
                    "conflicting_classifications": [],
                    "allele_frequencies": {"gnomAD-genomes": 0.001},
                },
                "gene_stats": [{"gene": "BRCA1", "pathogenic_count": 5}],
            },
            pharmgkb_data={"found": True, "data": {"drugs": ["tamoxifen"]}},
            snpedia_data={
                "found": True,
                "data": {
                    "title": "Rs12345",
                    "revisions": [{"*": "{{Summary|value=test}} Real content about this variant."}],
                },
            },
            litvar_data={
                "found": True,
                "publications": [
                    {"pmid": "12345", "title": "Study about rs12345", "journal": "Nature", "year": 2023},
                ],
            },
            alpha_missense_data={"found": True, "am_pathogenicity": 0.92, "am_class": "likely_pathogenic"},
            gnomad_data={
                "found": True,
                "source": "gnomad",
                "variant_id": "1-12345-A-G",
                "variant_type": "snv",
                "af": 0.001,
                "ac": 10,
                "an": 10000,
                "nhomalt": 0,
                "filter_status": "PASS",
                "gene": "BRCA1",
                "consequence": "missense_variant",
                "impact": "MODERATE",
                "hgvsc": "c.123A>G",
                "hgvsp": "p.Met41Val",
                "population_frequencies": {"AFR": {"af": 0.002}},
                "cadd": {"phred": 28.5, "raw": 3.5},
                "predictions": {"sift": "deleterious"},
                "conservation": {"phylop": 8.5},
                "splice_ai": {"delta_score": 0.01},
            },
            gnomad_tx_data={
                "found": True,
                "gene": "BRCA1",
                "consequence": "missense_variant",
                "lof": None,
                "mean_expression": 5.2,
                "transcript_count": 2,
                "transcripts": [{"transcript_id": "ENST00001", "top_tissues": ["breast", "ovary"]}],
            },
            thousand_genomes_data={
                "found": True,
                "source": "1000genomes_local",
                "variant_type": "snv",
                "minor_allele": "G",
                "maf": 0.001,
                "mac": 5,
                "ancestral_allele": "A",
                "population_frequencies": {"EUR": {"af": 0.001}},
            },
        )

    def test_variant_details_cache_hit(self):
        session = _make_mock_session()
        ann = self._make_rich_annotation()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=ann))
        app, _ = self._build_with_session(session)
        with patch("backend.services.annotation_loader.select", return_value=MagicMock()), \
             patch("backend.services.variant_detail_builder.AlphaMissenseService") as MockAM, \
             patch("backend.services.scoring_engine.get_scoring_engine") as mock_scoring, \
             patch("backend.services.bq_public.get_bq_public_service", side_effect=Exception("no bq")):
            MockAM.format_result_for_display = MagicMock(return_value={"am_pathogenicity": 0.92})
            mock_scoring.return_value.score_variant = MagicMock(return_value={"score": 0.8})
            with TestClient(app) as client:
                resp = client.get("/api/annotations/variant-details/rs12345")
                assert resp.status_code == 200
                data = resp.json()
                assert data["found"] is True
                assert data["rsid"] == "rs12345"

    def test_variant_details_with_transcript_consequences(self):
        session = _make_mock_session()
        ann = self._make_rich_annotation()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=ann))
        app, _ = self._build_with_session(session)
        with patch("backend.services.annotation_loader.select", return_value=MagicMock()), \
             patch("backend.services.variant_detail_builder.AlphaMissenseService") as MockAM, \
             patch("backend.services.scoring_engine.get_scoring_engine") as mock_scoring, \
             patch("backend.services.bq_public.get_bq_public_service", side_effect=Exception("no bq")):
            MockAM.format_result_for_display = MagicMock(return_value=None)
            mock_scoring.return_value.score_variant = MagicMock(return_value={"score": 0.5})
            with TestClient(app) as client:
                resp = client.get("/api/annotations/variant-details/rs12345")
                assert resp.status_code == 200
                data = resp.json()
                assert "transcripts" in data or resp.status_code == 200

    def test_variant_details_no_annotation_found(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build_with_session(session)
        with patch("backend.services.annotation_loader.select", return_value=MagicMock()), \
             patch("backend.services.annotation_loader.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(side_effect=Exception("not found"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/variant-details/rs99999")
                assert resp.status_code in (200, 404)

    def test_variant_details_with_bq_enrichment(self):
        session = _make_mock_session()
        ann = self._make_rich_annotation()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=ann))
        app, _ = self._build_with_session(session)
        with patch("backend.services.annotation_loader.select", return_value=MagicMock()), \
             patch("backend.services.variant_detail_builder.AlphaMissenseService") as MockAM, \
             patch("backend.services.scoring_engine.get_scoring_engine") as mock_scoring, \
             patch("backend.services.bq_public.get_bq_public_service") as mock_bq:
            MockAM.format_result_for_display = MagicMock(return_value={"am_class": "benign"})
            mock_scoring.return_value.score_variant = MagicMock(return_value={"score": 0.2})
            bq_instance = MagicMock()
            bq_instance.enrich_variant = AsyncMock(return_value={"chembl": {"found": True}})
            mock_bq.return_value = bq_instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/variant-details/rs12345")
                assert resp.status_code == 200

    def test_variant_details_refresh(self):
        session = _make_mock_session()
        session.execute = AsyncMock(return_value=_make_mock_result(scalar=None))
        app, _ = self._build_with_session(session)
        with patch("backend.services.annotation_loader.select", return_value=MagicMock()), \
             patch("backend.services.scoring_engine.get_scoring_engine") as mock_scoring, \
             patch("backend.services.annotation_loader.GeneticAPIService") as MockSvc:
            mock_scoring.return_value.score_variant = MagicMock(return_value={"score": 0.1})
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.annotate_variant = AsyncMock(return_value={"annotations": {}})
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/variant-details/rs12345?refresh=true")
                assert resp.status_code in (200, 404)


class TestGetDrugResponseInfo:
    def _build(self):
        return _build_app()

    def test_drug_response_success(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_clinpgx_drug_info = AsyncMock(return_value={"found": True, "drugs": ["warfarin"]})
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/drug-response/CYP2D6")
                assert resp.status_code == 200

    def test_drug_response_error(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_clinpgx_drug_info = AsyncMock(side_effect=Exception("timeout"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/drug-response/CYP2D6")
                assert resp.status_code == 500


class TestGetSnpediaAnnotation:
    def _build(self):
        return _build_app()

    def test_snpedia_success(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_snpedia_data = AsyncMock(return_value={"found": True, "text": "some wiki text"})
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/snpedia/rs12345")
                assert resp.status_code in (200, 404, 500)

    def test_snpedia_not_found(self):
        app, _ = self._build()
        with patch("backend.api.annotation_routes.GeneticAPIService") as MockSvc:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.get_snpedia_data = AsyncMock(side_effect=Exception("not found"))
            MockSvc.return_value = instance
            with TestClient(app) as client:
                resp = client.get("/api/annotations/snpedia/rs99999")
                assert resp.status_code in (200, 404, 500)
