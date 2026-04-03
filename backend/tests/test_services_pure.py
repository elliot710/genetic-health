"""Tests for discovery_service, variant_loader, annotation_constants, and small generators."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.services.discovery_service import (
    _determine_variant_mappings,
    _infer_condition,
    CLINICAL_PANEL_MAP,
    CONSEQUENCE_PANEL_MAP,
)
from backend.services.variant_loader import _find_gene_at_position
from backend.services.annotation_constants import (
    source_status,
    ALL_SOURCES,
    SOURCE_TO_COLUMN,
    REMOTE_API_SOURCES,
    LOCAL_SOURCES,
)


# ===========================================================================
# discovery_service
# ===========================================================================

class TestDetermineVariantMappings:
    def test_pathogenic_sig_creates_health_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="BRCA1",
            consequence="missense_variant",
            clinical_sigs=["Pathogenic"],
            pharmacogenomics={},
        )
        assert "health" in result
        assert result["health"]["map_type"] == "rsid"
        assert result["health"]["key"] == "rs12345"

    def test_likely_pathogenic_creates_health_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="TP53",
            consequence="",
            clinical_sigs=["Likely pathogenic"],
            pharmacogenomics={},
        )
        assert "health" in result

    def test_risk_factor_creates_health_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="APOE",
            consequence="",
            clinical_sigs=["Risk_factor"],
            pharmacogenomics={},
        )
        assert "health" in result

    def test_high_impact_consequence_creates_health_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene=None,
            consequence="stop_gained",
            clinical_sigs=[],
            pharmacogenomics={},
        )
        assert "health" in result

    def test_drug_response_sig_creates_drug_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="CYP2C9",
            consequence="",
            clinical_sigs=["Drug_response"],
            pharmacogenomics={},
        )
        assert "drug" in result

    def test_pharmacogenomics_found_creates_drug_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="CYP2D6",
            consequence="",
            clinical_sigs=[],
            pharmacogenomics={"found": True, "data": {}},
        )
        assert "drug" in result

    def test_benign_sig_no_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="GENE1",
            consequence="synonymous_variant",
            clinical_sigs=["Benign"],
            pharmacogenomics={},
        )
        assert "health" not in result

    def test_empty_inputs_no_mapping(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene=None,
            consequence="",
            clinical_sigs=[],
            pharmacogenomics={},
        )
        assert result == {}

    def test_health_data_has_condition(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="BRCA1",
            consequence="",
            clinical_sigs=["Pathogenic"],
            pharmacogenomics={},
        )
        assert "condition" in result["health"]["data"]

    def test_drug_mapping_includes_gene(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="CYP2C9",
            consequence="",
            clinical_sigs=["drug_response"],
            pharmacogenomics={},
        )
        assert result["drug"]["data"]["gene"] == "CYP2C9"

    def test_pharmacogenomics_with_related_chemicals(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="CYP2D6",
            consequence="",
            clinical_sigs=[],
            pharmacogenomics={
                "found": True,
                "data": {"relatedChemicals": [{"name": "Warfarin"}, {"name": "Aspirin"}]}
            },
        )
        assert "Warfarin" in result["drug"]["data"]["drugs"]

    def test_risk_multiplier_higher_for_pathogenic(self):
        result = _determine_variant_mappings(
            rsid="rs12345",
            gene="BRCA1",
            consequence="",
            clinical_sigs=["Pathogenic"],
            pharmacogenomics={},
        )
        assert result["health"]["data"]["risk_multiplier"] > 1.0


class TestInferCondition:
    def test_pathogenic_with_gene(self):
        result = _infer_condition(["Pathogenic"], "BRCA1")
        assert "BRCA1" in result

    def test_risk_with_gene(self):
        result = _infer_condition(["Risk factor"], "APOE")
        assert "APOE" in result

    def test_benign_returns_none(self):
        result = _infer_condition(["Benign"], "GENE1")
        assert result is None

    def test_no_gene_pathogenic_returns_none(self):
        result = _infer_condition(["Pathogenic"], None)
        assert result is None

    def test_empty_sigs_returns_none(self):
        result = _infer_condition([], "BRCA1")
        assert result is None


class TestClinicalPanelConstants:
    def test_pathogenic_maps_to_health(self):
        assert CLINICAL_PANEL_MAP["pathogenic"] == "health"

    def test_drug_response_maps_to_drug(self):
        assert CLINICAL_PANEL_MAP["drug_response"] == "drug"

    def test_consequence_maps_exist(self):
        assert "stop_gained" in CONSEQUENCE_PANEL_MAP
        assert "frameshift_variant" in CONSEQUENCE_PANEL_MAP
        assert "missense_variant" in CONSEQUENCE_PANEL_MAP


# ===========================================================================
# variant_loader - pure function
# ===========================================================================

class TestFindGeneAtPosition:
    def _make_table(self, genes):
        """genes = list of (start, end, symbol, biotype)"""
        return {"1": sorted(genes)}

    def test_basic_overlap(self):
        table = self._make_table([(1000, 5000, "GENE1", "protein_coding")])
        assert _find_gene_at_position(table, "1", 3000) == "GENE1"

    def test_no_overlap_returns_none(self):
        table = self._make_table([(1000, 5000, "GENE1", "protein_coding")])
        assert _find_gene_at_position(table, "1", 6000) is None

    def test_before_gene_returns_none(self):
        table = self._make_table([(1000, 5000, "GENE1", "protein_coding")])
        assert _find_gene_at_position(table, "1", 500) is None

    def test_prefers_protein_coding(self):
        table = self._make_table([
            (1000, 5000, "NONCODING", "lncRNA"),
            (2000, 4000, "CODING", "protein_coding"),
        ])
        result = _find_gene_at_position(table, "1", 3000)
        assert result == "CODING"

    def test_prefers_smaller_gene_when_same_biotype(self):
        table = self._make_table([
            (1000, 10000, "BIGGENE", "protein_coding"),
            (2000, 4000, "SMALLGENE", "protein_coding"),
        ])
        result = _find_gene_at_position(table, "1", 3000)
        assert result == "SMALLGENE"

    def test_chromosome_not_in_table_returns_none(self):
        table = self._make_table([(1000, 5000, "GENE1", "protein_coding")])
        assert _find_gene_at_position(table, "X", 3000) is None

    def test_empty_table_returns_none(self):
        assert _find_gene_at_position({}, "1", 3000) is None

    def test_at_start_boundary(self):
        table = self._make_table([(1000, 5000, "GENE1", "protein_coding")])
        assert _find_gene_at_position(table, "1", 1000) == "GENE1"

    def test_at_end_boundary(self):
        table = self._make_table([(1000, 5000, "GENE1", "protein_coding")])
        assert _find_gene_at_position(table, "1", 5000) == "GENE1"


# ===========================================================================
# annotation_constants
# ===========================================================================

class TestSourceStatus:
    def test_none_returns_missing(self):
        assert source_status(None) == "missing"

    def test_found_data_returns_found(self):
        assert source_status({"found": True}) == "found"

    def test_not_found_returns_no_data(self):
        assert source_status({"found": False}) == "no_data"

    def test_empty_dict_returns_no_data(self):
        assert source_status({}) == "no_data"

    def test_non_dict_returns_missing(self):
        assert source_status("some_string") == "missing"


class TestAnnotationConstants:
    def test_all_sources_is_list(self):
        assert isinstance(ALL_SOURCES, list)
        assert "ensembl" in ALL_SOURCES
        assert "clinvar" in ALL_SOURCES

    def test_source_to_column_mapping(self):
        assert SOURCE_TO_COLUMN["clinpgx"] == "pharmgkb"
        assert SOURCE_TO_COLUMN["ensembl_vep"] == "ensembl"

    def test_remote_api_sources_set(self):
        assert "ensembl" in REMOTE_API_SOURCES
        assert "gnomad" not in REMOTE_API_SOURCES

    def test_local_sources_set(self):
        assert "clinvar_local" in LOCAL_SOURCES
        assert "gnomad" in LOCAL_SOURCES


# ===========================================================================
# Small insight generators (tested via mocking generate_from_maps)
# ===========================================================================

@pytest.mark.asyncio
async def test_generate_wellness_metrics_calls_generate():
    with patch("backend.services.insight_generators.wellness.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 3
        from backend.services.insight_generators.wellness import generate_wellness_metrics
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_wellness_metrics(ctx)
        assert mock_gen.called
        assert result == 3


@pytest.mark.asyncio
async def test_generate_sports_calls_generate():
    with patch("backend.services.insight_generators.sports.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 2
        from backend.services.insight_generators.sports import generate_sports_performance
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_sports_performance(ctx)
        assert mock_gen.called
        assert result == 2


@pytest.mark.asyncio
async def test_generate_physical_traits_calls_generate():
    with patch("backend.services.insight_generators.physical_traits.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 1
        from backend.services.insight_generators.physical_traits import generate_physical_traits
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_physical_traits(ctx)
        assert mock_gen.called


@pytest.mark.asyncio
async def test_generate_personality_calls_generate():
    with patch("backend.services.insight_generators.personality.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 0
        from backend.services.insight_generators.personality import generate_personality_traits
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_personality_traits(ctx)
        assert mock_gen.called


@pytest.mark.asyncio
async def test_generate_nutrition_calls_generate():
    with patch("backend.services.insight_generators.nutrition.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 4
        from backend.services.insight_generators.nutrition import generate_nutrition_traits
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_nutrition_traits(ctx)
        assert mock_gen.called


@pytest.mark.asyncio
async def test_generate_methylation_calls_generate():
    with patch("backend.services.insight_generators.methylation.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 2
        from backend.services.insight_generators.methylation import generate_methylation_profiles
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_methylation_profiles(ctx)
        assert mock_gen.called


@pytest.mark.asyncio
async def test_generate_cognitive_calls_generate():
    with patch("backend.services.insight_generators.cognitive.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 1
        from backend.services.insight_generators.cognitive import generate_cognitive_profiles
        ctx = MagicMock()
        ctx.get_maps.return_value = ({}, {})
        result = await generate_cognitive_profiles(ctx)
        assert mock_gen.called


@pytest.mark.asyncio
async def test_generate_health_calls_generate():
    with patch("backend.services.insight_generators.health.generate_from_maps", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 5
        from backend.services.insight_generators.health import generate_health_risks
        ctx = MagicMock()
        ctx.annotation_results = {}
        ctx.get_maps.return_value = ({}, {})
        result = await generate_health_risks(ctx)
        assert mock_gen.called
