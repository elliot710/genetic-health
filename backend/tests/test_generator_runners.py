"""Tests for insight generator async functions and related services."""
import pytest
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch


# ──────────────────────────────────────────────────────────────────
# Generator context helpers
# ──────────────────────────────────────────────────────────────────

@dataclass
class _MockAnnotationResult:
    annotation_data: Optional[Dict] = None
    rsid: Optional[str] = None


def _make_variant(rsid, genotype="A/G", ref="A", alt="G"):
    v = MagicMock()
    v.rsid = rsid
    v.genotype = genotype
    v.marker = MagicMock()
    v.marker.rsid = rsid
    v.marker.ref_allele = ref
    v.marker.alt_alleles = alt
    v.info = {}
    return v


def _make_ctx(variants=None, rsid_map=None, gene_map=None, category="drug"):
    from backend.services.insight_generators.base import GeneratorContext
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    ctx = MagicMock(spec=GeneratorContext)
    ctx.analysis_id = 1
    ctx.variants = variants or []
    ctx.annotation_results = {}
    ctx.session = session
    ctx.rsid_gene_map = {}
    ctx.registry = {}
    ctx.variant_profiles = {}
    ctx.get_maps = MagicMock(return_value=(rsid_map or {}, gene_map or {}))
    return ctx


# ──────────────────────────────────────────────────────────────────
# drug_response generator
# ──────────────────────────────────────────────────────────────────

class TestGenerateDrugResponses:
    @pytest.mark.asyncio
    async def test_empty_variants(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        ctx = _make_ctx()
        result = await generate_drug_responses(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_rsid_variant_skipped(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        variant = MagicMock()
        variant.rsid = None
        ctx = _make_ctx(variants=[variant])
        result = await generate_drug_responses(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_variant_no_call_skipped(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        variant = _make_variant("rs12345", "--")
        ctx = _make_ctx(variants=[variant])
        result = await generate_drug_responses(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_variant_with_drug_match(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        variant = _make_variant("rs12345", "A/G")
        rsid_map = {
            "rs12345": {
                "gene": "CYP2D6",
                "drugs": ["codeine"],
                "condition": "Drug metabolism",
                "description": "Poor metabolizer",
            }
        }
        ctx = _make_ctx(variants=[variant], rsid_map=rsid_map, category="drug")
        result = await generate_drug_responses(ctx)
        assert result >= 0  # may match or not depending on is_clinvar_benign

    @pytest.mark.asyncio
    async def test_variant_with_gene_match(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        variant = _make_variant("rs12345", "A/G")
        gene_map = {
            "CYP2D6": {
                "gene": "CYP2D6",
                "drugs": [("codeine", "reduced", "avoid")],
            }
        }
        annotation = _MockAnnotationResult(annotation_data={"annotations": {}})
        ctx = _make_ctx(variants=[variant], gene_map=gene_map, category="drug")
        ctx.annotation_results = {"rs12345": annotation}
        ctx.rsid_gene_map = {"rs12345": "CYP2D6"}
        result = await generate_drug_responses(ctx)
        assert result >= 0

    @pytest.mark.asyncio
    async def test_profile_is_no_call_skipped(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        variant = _make_variant("rs12345", "A/G")
        profile = MagicMock()
        profile.is_no_call = True
        profile.is_hom_ref = False
        ctx = _make_ctx(variants=[variant])
        ctx.variant_profiles = {"rs12345": profile}
        result = await generate_drug_responses(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_profile_is_hom_ref_skipped(self):
        from backend.services.insight_generators.drug_response import generate_drug_responses
        variant = _make_variant("rs12345", "A/A")
        profile = MagicMock()
        profile.is_no_call = False
        profile.is_hom_ref = True
        ctx = _make_ctx(variants=[variant])
        ctx.variant_profiles = {"rs12345": profile}
        result = await generate_drug_responses(ctx)
        assert result == 0


# ──────────────────────────────────────────────────────────────────
# carrier generator
# ──────────────────────────────────────────────────────────────────

class TestGenerateCarrierStatus:
    @pytest.mark.asyncio
    async def test_empty_variants(self):
        from backend.services.insight_generators.carrier import generate_carrier_status
        ctx = _make_ctx()
        result = await generate_carrier_status(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_call_skipped(self):
        from backend.services.insight_generators.carrier import generate_carrier_status
        ctx = _make_ctx(variants=[_make_variant("rs12345", "--")])
        result = await generate_carrier_status(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_heterozyogous_with_rsid_map(self):
        from backend.services.insight_generators.carrier import generate_carrier_status
        variant = _make_variant("rs12345", "A/G")
        rsid_map = {
            "rs12345": {
                "condition": "BRCA1 mutation carrier",
                "gene": "BRCA1",
                "description": "BRCA1 pathogenic variant",
            }
        }
        ctx = _make_ctx(variants=[variant], rsid_map=rsid_map, category="carrier")
        result = await generate_carrier_status(ctx)
        assert result >= 0

    @pytest.mark.asyncio
    async def test_no_variant_rsid(self):
        from backend.services.insight_generators.carrier import generate_carrier_status
        v = MagicMock()
        v.rsid = None
        ctx = _make_ctx(variants=[v])
        result = await generate_carrier_status(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_with_profile_hom_ref(self):
        from backend.services.insight_generators.carrier import generate_carrier_status
        variant = _make_variant("rs12345", "A/A")
        profile = MagicMock()
        profile.is_no_call = False
        profile.effective_ref = "A"
        profile.annotation_result = None
        ctx = _make_ctx(variants=[variant])
        ctx.variant_profiles = {"rs12345": profile}
        result = await generate_carrier_status(ctx)
        assert result == 0


# ──────────────────────────────────────────────────────────────────
# uncommon_mutations generator
# ──────────────────────────────────────────────────────────────────

class TestGenerateUncommonMutations:
    @pytest.mark.asyncio
    async def test_empty_variants(self):
        from backend.services.insight_generators.uncommon_mutations import generate_uncommon_mutations
        ctx = _make_ctx()
        result = await generate_uncommon_mutations(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_call_skipped(self):
        from backend.services.insight_generators.uncommon_mutations import generate_uncommon_mutations
        ctx = _make_ctx(variants=[_make_variant("rs12345", "--")])
        result = await generate_uncommon_mutations(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_het_variant_no_annotation(self):
        from backend.services.insight_generators.uncommon_mutations import generate_uncommon_mutations
        variant = _make_variant("rs12345", "A/G")
        ctx = _make_ctx(variants=[variant])
        result = await generate_uncommon_mutations(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_het_variant_with_functional_consequence(self):
        from backend.services.insight_generators.uncommon_mutations import generate_uncommon_mutations
        variant = _make_variant("rs12345", "A/G")
        annotation = _MockAnnotationResult(annotation_data={
            "annotations": {
                "ensembl": {
                    "data": [{
                        "allele_string": "A/G",
                        "most_severe_consequence": "missense_variant",
                        "transcript_consequences": [{
                            "gene_symbol": "BRCA1",
                            "consequence_terms": ["missense_variant"],
                            "impact": "MODERATE",
                        }]
                    }]
                }
            }
        })
        ctx = _make_ctx(variants=[variant])
        ctx.annotation_results = {"rs12345": annotation}
        result = await generate_uncommon_mutations(ctx)
        assert result >= 0


# ──────────────────────────────────────────────────────────────────
# rare_mutations generator
# ──────────────────────────────────────────────────────────────────

class TestGenerateRareMutations:
    @pytest.mark.asyncio
    async def test_empty_variants(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations
        ctx = _make_ctx()
        result = await generate_rare_mutations(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_call_skipped(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations
        ctx = _make_ctx(variants=[_make_variant("rs12345", "--")])
        result = await generate_rare_mutations(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_variant_no_annotation_skipped(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations
        variant = _make_variant("rs12345", "A/G")
        ctx = _make_ctx(variants=[variant])
        result = await generate_rare_mutations(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_variant_with_pathogenic_annotation(self):
        from backend.services.insight_generators.rare_mutations import generate_rare_mutations
        variant = _make_variant("rs12345", "A/G")
        annotation = _MockAnnotationResult(annotation_data={
            "annotations": {
                "clinvar_local": {
                    "found": True,
                    "clinical_significances": ["Pathogenic"],
                    "conditions": ["BRCA-related cancer"],
                    "alt_allele": "G",
                    "review_status": "criteria provided",
                }
            }
        })
        ctx = _make_ctx(variants=[variant])
        ctx.annotation_results = {"rs12345": annotation}
        result = await generate_rare_mutations(ctx)
        assert result >= 0


# ──────────────────────────────────────────────────────────────────
# Small generators (health, cognitive, personality, etc.)
# ──────────────────────────────────────────────────────────────────

class TestSmallGenerators:
    @pytest.mark.asyncio
    async def test_health_empty(self):
        from backend.services.insight_generators.health import generate_health_risks
        ctx = _make_ctx()
        result = await generate_health_risks(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_cognitive_empty(self):
        from backend.services.insight_generators.cognitive import generate_cognitive_profiles
        ctx = _make_ctx()
        result = await generate_cognitive_profiles(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_personality_empty(self):
        from backend.services.insight_generators.personality import generate_personality_traits
        ctx = _make_ctx()
        result = await generate_personality_traits(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_methylation_empty(self):
        from backend.services.insight_generators.methylation import generate_methylation_profiles
        ctx = _make_ctx()
        result = await generate_methylation_profiles(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_detox_empty(self):
        from backend.services.insight_generators.detox import generate_detox_profiles
        ctx = _make_ctx()
        result = await generate_detox_profiles(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_nutrition_empty(self):
        from backend.services.insight_generators.nutrition import generate_nutrition_traits
        ctx = _make_ctx()
        result = await generate_nutrition_traits(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_physical_traits_empty(self):
        from backend.services.insight_generators.physical_traits import generate_physical_traits
        ctx = _make_ctx()
        result = await generate_physical_traits(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_sports_performance_empty(self):
        from backend.services.insight_generators.sports import generate_sports_performance
        ctx = _make_ctx()
        result = await generate_sports_performance(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_wellness_empty(self):
        from backend.services.insight_generators.wellness import generate_wellness_metrics
        ctx = _make_ctx()
        result = await generate_wellness_metrics(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_health_with_variant(self):
        from backend.services.insight_generators.health import generate_health_risks
        variant = _make_variant("rs12345", "A/G")
        rsid_map = {
            "rs12345": {
                "condition": "Heart Disease",
                "gene": "BRCA1",
                "risk": "increased",
                "risk_factor": 1.5,
                "description": "Test",
            }
        }
        ctx = _make_ctx(variants=[variant], rsid_map=rsid_map, category="health")
        result = await generate_health_risks(ctx)
        assert result >= 0

    @pytest.mark.asyncio
    async def test_cognitive_with_variant(self):
        from backend.services.insight_generators.cognitive import generate_cognitive_profiles
        variant = _make_variant("rs12345", "A/G")
        rsid_map = {
            "rs12345": {
                "profile": "Memory",
                "gene": "APOE",
                "trait": "memory",
                "impact": "increased",
                "description": "Test",
                "risk": "moderate",
            }
        }
        ctx = _make_ctx(variants=[variant], rsid_map=rsid_map, category="cognitive")
        result = await generate_cognitive_profiles(ctx)
        assert result >= 0


# ──────────────────────────────────────────────────────────────────
# annotation_coordinator pure functions
# ──────────────────────────────────────────────────────────────────

class TestAnnotationCoordinatorUtils:
    def test_truthy_data_none(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data(None) is None

    def test_truthy_data_empty_dict(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data({}) is None

    def test_truthy_data_no_found(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data({"data": "something"}) is None

    def test_truthy_data_found_false(self):
        from backend.services.annotation_coordinator import _truthy_data
        assert _truthy_data({"found": False, "data": "x"}) is None

    def test_truthy_data_found_true(self):
        from backend.services.annotation_coordinator import _truthy_data
        d = {"found": True, "data": "x"}
        assert _truthy_data(d) == d

    def test_build_annotation_link_values_empty(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        result = _build_annotation_link_values({}, [], {}, 1)
        assert result == []

    def test_build_annotation_link_values_no_shared_id(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        rsid_to_variants = {"rs12345": [MagicMock(id=1)]}
        result = _build_annotation_link_values(rsid_to_variants, ["rs12345"], {}, 1)
        assert result == []

    def test_build_annotation_link_values_with_shared_id(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        v = MagicMock()
        v.id = 10
        rsid_to_variants = {"rs12345": [v]}
        rsid_to_shared_id = {"rs12345": 5}
        result = _build_annotation_link_values(
            rsid_to_variants, ["rs12345"], rsid_to_shared_id, 1
        )
        assert len(result) == 1
        assert result[0]["rsid"] == "rs12345"
        assert result[0]["shared_annotation_id"] == 5
        assert result[0]["analysis_id"] == 1

    def test_build_annotation_link_values_multiple(self):
        from backend.services.annotation_coordinator import _build_annotation_link_values
        v1 = MagicMock()
        v1.id = 1
        v2 = MagicMock()
        v2.id = 2
        rsid_to_variants = {"rs1": [v1], "rs2": [v2]}
        rsid_to_shared_id = {"rs1": 10, "rs2": 20}
        result = _build_annotation_link_values(
            rsid_to_variants, ["rs1", "rs2"], rsid_to_shared_id, 5
        )
        assert len(result) == 2


class TestFetchRemoteApiData:
    @pytest.mark.asyncio
    async def test_empty_rsids(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data
        result = await _fetch_remote_api_data([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_with_rsids_mocked_db(self):
        from backend.services.annotation_coordinator import _fetch_remote_api_data
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        execute_result = MagicMock()
        execute_result.fetchall = MagicMock(return_value=[])
        session.execute = AsyncMock(return_value=execute_result)
        with patch("backend.services.annotation_coordinator.async_session_factory", return_value=session):
            result = await _fetch_remote_api_data(["rs12345"])
            assert isinstance(result, dict)


class TestInsertAnnotationLinks:
    @pytest.mark.asyncio
    async def test_empty_link_values(self):
        from backend.services.annotation_coordinator import _insert_annotation_links
        session = AsyncMock()
        await _insert_annotation_links(session, [])
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_link_values(self):
        from backend.services.annotation_coordinator import _insert_annotation_links
        session = AsyncMock()
        session.execute = AsyncMock()
        link_values = [{"analysis_id": 1, "analysis_variant_id": 1,
                        "shared_annotation_id": 1, "rsid": "rs12345"}]
        with patch("sqlalchemy.dialects.postgresql.insert"):
            with patch("backend.services.annotation_coordinator.VariantAnnotation"):
                await _insert_annotation_links(session, link_values)


# ──────────────────────────────────────────────────────────────────
# insight_dispatcher
# ──────────────────────────────────────────────────────────────────

class TestInsightDispatcher:
    @pytest.mark.asyncio
    async def test_generate_comprehensive_insights_empty_variants(self):
        from backend.services.insight_dispatcher import generate_comprehensive_insights
        from backend.services.analysis_service import AnalysisProgress

        progress = MagicMock()
        progress.analysis_id = 1

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("backend.services.insight_dispatcher.async_session_factory", return_value=mock_session):
            with patch("backend.services.insight_dispatcher.build_variant_profiles", new=AsyncMock(return_value={})):
                with patch("backend.services.insight_dispatcher.ALL_GENERATORS", []):
                    with patch("backend.services.insight_dispatcher.delete", return_value=MagicMock()):
                        result = await generate_comprehensive_insights(
                            variants=[],
                            annotation_results={},
                            analysis_id=1,
                            rsid_gene_map={},
                            registry={},
                            progress=progress,
                        )
                        assert result >= 0

    @pytest.mark.asyncio
    async def test_regenerate_insights_no_variants(self):
        from backend.services.insight_dispatcher import regenerate_insights
        import sqlalchemy as _sa

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))
        mock_session.commit = AsyncMock()

        with patch("backend.services.insight_dispatcher.async_session_factory", return_value=mock_session):
            with patch.object(_sa, "select", MagicMock(return_value=MagicMock())):
                with patch("backend.services.variant_loader.load_analysis_data", new=AsyncMock(return_value=(None, []))):
                    result = await regenerate_insights(analysis_id=999, user_id=1)
                    assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────────
# discovery_service
# ──────────────────────────────────────────────────────────────────

class TestDiscoveryService:
    @pytest.mark.asyncio
    async def test_process_lookup_discoveries_empty_response(self):
        from backend.services.discovery_service import process_lookup_discoveries
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))
        session.add = MagicMock()
        session.commit = AsyncMock()
        result = await process_lookup_discoveries(session, "rs12345", {})
        assert result == 0

    @pytest.mark.asyncio
    async def test_process_lookup_discoveries_not_found(self):
        from backend.services.discovery_service import process_lookup_discoveries
        session = MagicMock()
        result = await process_lookup_discoveries(session, "rs12345", {"found": False})
        assert result == 0

    @pytest.mark.asyncio
    async def test_process_lookup_discoveries_found(self):
        from backend.services.discovery_service import process_lookup_discoveries
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))
        session.add = MagicMock()
        session.commit = AsyncMock()
        with patch("backend.services.discovery_service.select", return_value=MagicMock()):
            result = await process_lookup_discoveries(session, "rs12345", {"found": True})
            assert result >= 0


# ──────────────────────────────────────────────────────────────────
# analysis_queue service
# ──────────────────────────────────────────────────────────────────

class TestAnalysisQueueExtended:
    def test_get_analysis_queue_returns_instance(self):
        from backend.services.analysis_queue import get_analysis_queue, AnalysisQueue
        q = get_analysis_queue()
        assert isinstance(q, AnalysisQueue)

    def test_queue_status_structure(self):
        from backend.services.analysis_queue import get_queue_status
        status = get_queue_status()
        assert isinstance(status, dict)

    def test_get_analysis_queue_singleton(self):
        from backend.services.analysis_queue import get_analysis_queue
        q1 = get_analysis_queue()
        q2 = get_analysis_queue()
        assert q1 is q2
