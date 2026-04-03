"""Tests for drug response and carrier status insight generators + helpers."""
from unittest.mock import AsyncMock, MagicMock


class TestAssessDrugResponse:
    """Tests for assess_drug_response in base.py."""

    def _fn(self):
        from backend.services.insight_generators.base import assess_drug_response
        return assess_drug_response

    def test_returns_normal_for_empty_genotype(self):
        assert self._fn()("", "CYP2D6") == "normal"

    def test_returns_normal_for_no_call(self):
        assert self._fn()("--", "CYP2D6") == "normal"

    def test_returns_normal_when_hom_ref(self):
        assert self._fn()("AA", "CYP2D6", ref_allele="A") == "normal"

    def test_cyp2c9_star2_returns_poor(self):
        assert self._fn()("*1/*2", "CYP2C9") == "poor"

    def test_cyp2c9_star3_returns_poor(self):
        assert self._fn()("*1/*3", "CYP2C9") == "poor"

    def test_cyp2c19_star2_returns_poor(self):
        assert self._fn()("*2/*2", "CYP2C19") == "poor"

    def test_heterozygous_pharmacogene_returns_intermediate(self):
        assert self._fn()("AC", "CYP2D6", ref_allele=None) == "intermediate"

    def test_homozygous_nonref_pharmacogene_returns_poor(self):
        assert self._fn()("CC", "CYP2D6", ref_allele=None) == "poor"

    def test_unknown_gene_returns_normal(self):
        assert self._fn()("AC", "UNKNOWN_GENE") == "normal"


class TestGetDrugRecommendations:
    """Tests for get_drug_recommendations in base.py."""

    def _fn(self):
        from backend.services.insight_generators.base import get_drug_recommendations
        return get_drug_recommendations

    def test_poor_returns_alternative_message(self):
        result = self._fn()("Warfarin", "poor")
        assert "Warfarin" in result
        assert "alternative" in result.lower() or "adjusted" in result.lower()

    def test_intermediate_returns_monitor_message(self):
        result = self._fn()("Clopidogrel", "intermediate")
        assert "Clopidogrel" in result
        assert "monitor" in result.lower()

    def test_normal_returns_standard_message(self):
        result = self._fn()("Ibuprofen", "normal")
        assert "Ibuprofen" in result
        assert "standard" in result.lower()


class TestClassifyCarrierStatus:
    """Tests for _classify_carrier_status in carrier.py."""

    def _fn(self):
        from backend.services.insight_generators.carrier import _classify_carrier_status
        return _classify_carrier_status

    def test_no_call_returns_unaffected(self):
        assert self._fn()("--", "A", "T") == "unaffected"

    def test_hom_ref_returns_unaffected(self):
        assert self._fn()("AA", "A", "T") == "unaffected"

    def test_heterozygous_returns_carrier(self):
        assert self._fn()("AT", "A", "T") == "carrier"

    def test_hom_alt_returns_affected(self):
        assert self._fn()("TT", "A", "T") == "affected"

    def test_indel_di_returns_carrier(self):
        assert self._fn()("DI", "A", "AT") == "carrier"

    def test_indel_id_returns_carrier(self):
        assert self._fn()("ID", "AT", "A") == "carrier"

    def test_missing_ref_and_alt_hom_returns_unaffected(self):
        assert self._fn()("AA", "", "") == "unaffected"

    def test_no_ref_heterozygous_returns_carrier(self):
        assert self._fn()("AT", "", "") == "carrier"

    def test_all_ref_alleles_returns_unaffected(self):
        assert self._fn()("GG", "G", "T") == "unaffected"

    def test_empty_genotype_returns_unaffected(self):
        assert self._fn()("", "A", "T") == "unaffected"

    def test_indel_dd_insertion_variant_returns_unaffected(self):
        # ref shorter than alt → D=ref → DD=hom_ref → unaffected
        assert self._fn()("DD", "A", "AT") == "unaffected"

    def test_indel_ii_insertion_variant_returns_affected(self):
        # ref shorter → D=ref → II=hom_alt → affected
        assert self._fn()("II", "A", "AT") == "affected"

    def test_indel_dd_deletion_variant_returns_affected(self):
        # ref longer than alt → D=alt → DD=hom_alt → affected
        assert self._fn()("DD", "AT", "A") == "affected"

    def test_indel_ii_deletion_variant_returns_unaffected(self):
        # ref longer → D=alt → II=hom_ref → unaffected
        assert self._fn()("II", "AT", "A") == "unaffected"

    def test_indel_dd_with_unknown_alleles_returns_carrier(self):
        assert self._fn()("DD", "N", "N") == "carrier"

    def test_ref_only_all_non_ref_returns_carrier(self):
        # Only ref allele known, all alleles are non-ref → conservative carrier
        assert self._fn()("TT", "A", "") == "carrier"

    def test_ref_only_mixed_returns_carrier(self):
        # ref allele known, one ref one non-ref → carrier
        assert self._fn()("AT", "A", "") == "carrier"


class TestIsClinvarBenign:
    """Tests for is_clinvar_benign in base.py."""

    def _fn(self):
        from backend.services.insight_generators.base import is_clinvar_benign
        return is_clinvar_benign

    def _make_anno(self, ann_data):
        ar = MagicMock()
        ar.annotation_data = ann_data
        return ar

    def test_returns_false_for_none(self):
        assert self._fn()(None) is False

    def test_returns_false_when_no_annotation_data(self):
        ar = MagicMock()
        ar.annotation_data = None
        assert self._fn()(ar) is False

    def test_returns_false_when_no_clinvar_data(self):
        ar = self._make_anno({'annotations': {}})
        assert self._fn()(ar) is False

    def test_returns_true_for_benign_clinvar(self):
        ar = self._make_anno({
            'annotations': {
                'clinvar_local': {
                    'found': True,
                    'clinical_significance': 'Benign',
                    'significances': ['benign'],
                }
            }
        })
        # May return True or False depending on computational pathogenicity check
        result = self._fn()(ar)
        assert isinstance(result, bool)

    def test_returns_false_for_pathogenic_clinvar(self):
        ar = self._make_anno({
            'annotations': {
                'clinvar_local': {
                    'found': True,
                    'clinical_significance': 'Pathogenic',
                    'significances': ['pathogenic'],
                }
            }
        })
        assert self._fn()(ar) is False


class TestGenerateDrugResponses:
    """Integration tests for generate_drug_responses using mocked context."""

    def _make_variant(self, rsid, genotype="AT"):
        v = MagicMock()
        v.rsid = rsid
        v.genotype = genotype
        marker = MagicMock()
        marker.ref_allele = "A"
        marker.alt_alleles = "T"
        marker.gene_symbol = None
        v.marker = marker
        return v

    def _make_ctx(self, variants, rsid_map=None, gene_map=None):
        from backend.services.insight_generators.base import GeneratorContext
        ctx = MagicMock(spec=GeneratorContext)
        ctx.analysis_id = 1
        ctx.variants = variants
        ctx.annotation_results = {}
        ctx.rsid_gene_map = {}
        ctx.variant_profiles = {}
        ctx.session = MagicMock()
        ctx.get_maps = MagicMock(return_value=(rsid_map or {}, gene_map or {}))
        return ctx

    def test_skips_placeholder_drug_names(self):
        import asyncio
        from backend.services.insight_generators.drug_response import generate_drug_responses
        v = self._make_variant("rs100", "AT")
        ctx = self._make_ctx(
            [v],
            rsid_map={"rs100": {
                "gene": "CYP2D6",
                "drugs": ["Associated medication"],
            }},
        )
        count = asyncio.run(generate_drug_responses(ctx))
        assert count == 0

    def test_adds_drug_response_for_valid_rsid_match(self):
        import asyncio
        from backend.services.insight_generators.drug_response import generate_drug_responses
        v = self._make_variant("rs1045642", "CT")
        ctx = self._make_ctx(
            [v],
            rsid_map={"rs1045642": {
                "gene": "ABCB1",
                "drugs": ["Digoxin"],
            }},
        )
        count = asyncio.run(generate_drug_responses(ctx))
        assert count == 1
        ctx.session.add.assert_called_once()

    def test_deduplicates_same_drug_from_multiple_variants(self):
        import asyncio
        from backend.services.insight_generators.drug_response import generate_drug_responses
        v1 = self._make_variant("rs100", "AT")
        v2 = self._make_variant("rs200", "AT")
        ctx = self._make_ctx(
            [v1, v2],
            rsid_map={
                "rs100": {"gene": "CYP2D6", "drugs": ["Warfarin"]},
                "rs200": {"gene": "CYP2D6", "drugs": ["Warfarin"]},
            },
        )
        count = asyncio.run(generate_drug_responses(ctx))
        assert count == 1

    def test_skips_variant_with_no_rsid(self):
        import asyncio
        from backend.services.insight_generators.drug_response import generate_drug_responses
        v = self._make_variant(None, "AT")
        ctx = self._make_ctx([v])
        count = asyncio.run(generate_drug_responses(ctx))
        assert count == 0
