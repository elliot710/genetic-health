"""HealthRisk provenance: the user's own result vs. the gene's reputation.

A finding built from the gene map says "this gene is associated with condition
X". A finding built from the rsid map says "your genotype at this position
carries risk for X". Rendering the first as the second is what put a gene's
worst known disease on a user's dashboard as their own.
"""
import asyncio
from unittest.mock import MagicMock

from backend.services.insight_generators.base import GeneratorContext
from backend.services.insight_generators.health import generate_health_risks
from backend.services.dashboard_serializers import serialize_health_risks

CONDITION = "Heart Disease"
GENE = "GNB1"


def _make_variant(rsid, genotype="AG", ref="A", alt="G"):
    variant = MagicMock()
    variant.rsid = rsid
    variant.genotype = genotype
    variant.chromosome = "1"
    variant.marker = MagicMock()
    variant.marker.ref_allele = ref
    variant.marker.alt_alleles = alt
    variant.marker.gene_symbol = GENE
    return variant


def _make_annotation(rsid, ref="A", alt="G"):
    annotation = MagicMock()
    annotation.rsid = rsid
    annotation.annotation_data = {
        "annotations": {
            "ensembl": {
                "data": [{
                    "allele_string": f"{ref}/{alt}",
                    "most_severe_consequence": "missense_variant",
                    "transcript_consequences": [
                        {"gene_symbol": GENE, "consequence_terms": ["missense_variant"],
                         "impact": "HIGH"},
                    ],
                }],
            },
        }
    }
    return annotation


def _make_ctx(rsid_map=None, gene_map=None):
    rsid = "rs4321"
    ctx = MagicMock(spec=GeneratorContext)
    ctx.analysis_id = 7
    ctx.variants = [_make_variant(rsid)]
    ctx.annotation_results = {rsid: _make_annotation(rsid)}
    ctx.rsid_gene_map = {rsid: GENE}
    ctx.variant_profiles = {}
    ctx.inferred_sex = None
    ctx.session = MagicMock()
    ctx.get_maps = MagicMock(return_value=(rsid_map or {}, gene_map or {}))
    return ctx


_RSID_MAP = {"rs4321": {
    "condition": CONDITION, "gene": GENE, "risk_multiplier": 1.5,
    "clinical_significance": "Pathogenic",
    "recommendations": ["Discuss with your clinician"],
}}

_GENE_MAP = {GENE: {
    "condition": CONDITION, "gene": GENE, "risk_level": "moderate",
    "clinical_significance": "Pathogenic",
    "recommendations": ["Discuss with your clinician"],
}}


def _emitted(rsid_map=None, gene_map=None):
    ctx = _make_ctx(rsid_map, gene_map)
    asyncio.run(generate_health_risks(ctx))
    return [call[0][0] for call in ctx.session.add.call_args_list]


class TestProvenanceTagging:
    def test_rsid_derived_finding_is_variant_provenance(self):
        assert _emitted(rsid_map=_RSID_MAP)[0].provenance == "variant"

    def test_gene_derived_finding_is_gene_provenance(self):
        assert _emitted(gene_map=_GENE_MAP)[0].provenance == "gene"


class TestDedupSpansBothProvenances:
    def test_same_condition_from_both_maps_yields_one_finding(self):
        assert len(_emitted(rsid_map=_RSID_MAP, gene_map=_GENE_MAP)) == 1

    def test_the_surviving_finding_is_the_users_own_variant_result(self):
        emitted = _emitted(rsid_map=_RSID_MAP, gene_map=_GENE_MAP)
        assert emitted[0].provenance == "variant"


class TestSerializationOfLegacyRows:
    def _row(self, **overrides):
        row = MagicMock(spec=[
            "condition", "risk_level", "risk_score", "associated_variants",
            "recommendations", "gene", "review_status",
            "pathogenicity_classification", *overrides.keys(),
        ])
        row.condition = CONDITION
        row.risk_level = "moderate"
        row.risk_score = 0.5
        row.associated_variants = ["rs4321"]
        row.recommendations = []
        row.gene = GENE
        row.review_status = None
        row.pathogenicity_classification = None
        for key, value in overrides.items():
            setattr(row, key, value)
        return row

    def test_row_predating_the_migration_reads_as_variant(self):
        assert serialize_health_risks([self._row()])[0]["provenance"] == "variant"

    def test_gene_provenance_survives_serialization(self):
        row = self._row(provenance="gene")
        assert serialize_health_risks([row])[0]["provenance"] == "gene"
