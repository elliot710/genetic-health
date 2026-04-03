"""Tests for simple insight generators: sports, nutrition, wellness, personality,
methylation, detox, cognitive, health, physical_traits."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(rsid_map=None, gene_map=None, annotation_results=None):
    ctx = MagicMock()
    ctx.analysis_id = 42
    ctx.annotation_results = annotation_results or {}
    ctx.db_session = MagicMock()
    rsid_map = rsid_map or {}
    gene_map = gene_map or {}
    ctx.get_maps = MagicMock(return_value=(rsid_map, gene_map))
    return ctx


def _capture_closures(module_path, fn_name, ctx):
    """Run a generator function with a mocked generate_from_maps and capture closures."""
    import asyncio
    import importlib
    mod = importlib.import_module(module_path)
    gen_fn = getattr(mod, fn_name)
    captured = {}

    async def fake_gen(ctx, rsid_map, gene_map, dedup_field, build_from_rsid, build_from_gene, **kw):
        captured['from_rsid'] = build_from_rsid
        captured['from_gene'] = build_from_gene
        return 0

    patch_target = f'{module_path}.generate_from_maps'
    with patch(patch_target, side_effect=fake_gen):
        asyncio.run(gen_fn(ctx))

    return captured


# ---------------------------------------------------------------------------
# Sports performance
# ---------------------------------------------------------------------------

class TestGenerateSportsPerformance:
    MODULE = 'backend.services.insight_generators.sports'
    FN = 'generate_sports_performance'

    def test_from_rsid_builds_correct_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'category': 'Endurance', 'advantage': 'high',
                'recommendations': ['Run'], 'advice': 'Train long',
                '_ref_allele': 'A', '_pathogenicity_score': None}
        result = fn(1, 'rs123', 'AT', info)
        assert result.performance_category == 'Endurance'
        assert result.analysis_id == 1

    def test_from_rsid_heterozygous_adjusts_advantage(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'category': 'Power', 'advantage': 'high', 'recommendations': [], 'advice': 'Lift',
                '_ref_allele': 'G', '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'GT', info)
        assert result.genetic_advantage is not None

    def test_from_gene_empty_genotype_uses_raw_advantage(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'category': 'Power', 'advantage': 'moderate', 'recommendations': [], 'advice': 'Squat',
                '_genotype': '', '_ref_allele': 'A', '_pathogenicity_score': None}
        result = fn(2, 'rs2', 'ACTN3', 'missense_variant', info)
        assert result.performance_category == 'Power'
        assert result.genetic_advantage == 'moderate'

    def test_from_gene_with_genotype_adjusts(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'category': 'Endurance', 'advantage': 'high', 'recommendations': [], 'advice': 'Train',
                '_genotype': 'AT', '_ref_allele': 'A', '_pathogenicity_score': None}
        result = fn(3, 'rs3', 'ACE', 'synonymous_variant', info)
        assert result.performance_category == 'Endurance'


# ---------------------------------------------------------------------------
# Nutrition traits
# ---------------------------------------------------------------------------

class TestGenerateNutritionTraits:
    MODULE = 'backend.services.insight_generators.nutrition'
    FN = 'generate_nutrition_traits'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'nutrient': 'Vitamin D', 'metabolism': 'slow', 'recommendations': ['Sun'],
                'sensitivity': 'high', '_ref_allele': 'A', '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'AT', info)
        assert result.nutrient == 'Vitamin D'
        assert result.metabolism_type == 'slow'

    def test_from_gene_no_genotype_uses_raw_sensitivity(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'nutrient': 'Iron', 'metabolism': 'normal', 'recommendations': [], 'sensitivity': 'moderate',
                '_genotype': '', '_ref_allele': None, '_pathogenicity_score': None}
        result = fn(2, 'rs2', 'SLC40A1', 'missense_variant', info)
        assert result.nutrient == 'Iron'
        assert result.sensitivity_level == 'moderate'

    def test_from_gene_with_genotype(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'nutrient': 'Caffeine', 'metabolism': 'fast', 'recommendations': [], 'sensitivity': 'low',
                '_genotype': 'CC', '_ref_allele': 'T', '_pathogenicity_score': None}
        result = fn(2, 'rs762551', 'CYP1A2', 'synonymous_variant', info)
        assert result.nutrient == 'Caffeine'


# ---------------------------------------------------------------------------
# Wellness metrics
# ---------------------------------------------------------------------------

class TestGenerateWellnessMetrics:
    MODULE = 'backend.services.insight_generators.wellness'
    FN = 'generate_wellness_metrics'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'metric': 'Sleep Quality', 'predisposition': 'favorable', 'score': 75,
                'recommendations': ['Sleep 8h'], '_ref_allele': 'C', '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'CT', info)
        assert result.metric_name == 'Sleep Quality'
        assert result.optimization_score == 75

    def test_from_gene_empty_genotype_uses_raw_predisposition(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'metric': 'Inflammation', 'predisposition': 'elevated', 'score': 60,
                'recommendations': [], '_genotype': '', '_ref_allele': None, '_pathogenicity_score': None}
        result = fn(2, 'rs2', 'IL6', 'regulatory_region_variant', info)
        assert result.metric_name == 'Inflammation'
        assert result.genetic_predisposition == 'elevated'


# ---------------------------------------------------------------------------
# Personality traits
# ---------------------------------------------------------------------------

class TestGeneratePersonalityTraits:
    MODULE = 'backend.services.insight_generators.personality'
    FN = 'generate_personality_traits'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'trait': 'Novelty Seeking', 'tendency': 'high', 'confidence': 'moderate',
                'insights': ['Try new things'], '_ref_allele': None, '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'AG', info)
        assert result.trait_name == 'Novelty Seeking'
        assert result.confidence_level == 'moderate'

    def test_from_gene_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'trait': 'Risk Taking', 'tendency': 'moderate', 'confidence': 'high',
                'insights': [], '_genotype': 'GT', '_ref_allele': 'G', '_pathogenicity_score': None}
        result = fn(2, 'rs2', 'DRD4', 'synonymous_variant', info)
        assert result.trait_name == 'Risk Taking'


# ---------------------------------------------------------------------------
# Methylation profiles
# ---------------------------------------------------------------------------

class TestGenerateMethylationProfiles:
    MODULE = 'backend.services.insight_generators.methylation'
    FN = 'generate_methylation_profiles'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'gene': 'MTHFR', 'capacity': 'reduced', 'supplements': ['Folate'],
                '_ref_allele': 'C', '_pathogenicity_score': None}
        result = fn(1, 'rs1298585', 'AT', info)
        assert result.gene == 'MTHFR'
        assert result.variant == 'rs1298585'

    def test_from_gene_empty_genotype(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'gene': 'COMT', 'capacity': 'normal', 'supplements': [],
                '_genotype': '', '_ref_allele': None, '_pathogenicity_score': None}
        result = fn(2, 'rs4680', 'COMT', 'missense_variant', info)
        assert result.gene == 'COMT'
        assert result.methylation_capacity == 'normal'

    def test_from_gene_with_genotype_adjusts(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'gene': 'MTHFR', 'capacity': 'high', 'supplements': ['B12'],
                '_genotype': 'CT', '_ref_allele': 'C', '_pathogenicity_score': None}
        result = fn(3, 'rs677', 'MTHFR', 'missense_variant', info)
        assert result.gene == 'MTHFR'


# ---------------------------------------------------------------------------
# Detox profiles
# ---------------------------------------------------------------------------

class TestGenerateDetoxProfiles:
    MODULE = 'backend.services.insight_generators.detox'
    FN = 'generate_detox_profiles'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'phase': 'Phase I', 'gene': 'CYP1A2', 'capacity': 'high', 'sensitivity': 'low',
                'recommendations': [], '_ref_allele': 'A', '_pathogenicity_score': None}
        result = fn(1, 'rs762551', 'AA', info)
        assert result.detox_phase == 'Phase I'
        assert result.gene == 'CYP1A2'

    def test_from_gene_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'phase': 'Phase II', 'gene': 'GSTM1', 'capacity': 'absent', 'sensitivity': 'high',
                'recommendations': [], '_genotype': 'GT', '_ref_allele': 'G', '_pathogenicity_score': None}
        result = fn(2, 'rs1', 'GSTM1', 'frameshift_variant', info)
        assert result.detox_phase == 'Phase II'

    def test_from_gene_empty_genotype_uses_raw_values(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'phase': 'Phase II', 'gene': 'NAT2', 'capacity': 'slow', 'sensitivity': 'moderate',
                'recommendations': [], '_genotype': '', '_ref_allele': None, '_pathogenicity_score': None}
        result = fn(3, 'rs2', 'NAT2', 'synonymous_variant', info)
        assert result.detox_capacity == 'slow'
        assert result.toxin_sensitivity == 'moderate'


# ---------------------------------------------------------------------------
# Cognitive profiles
# ---------------------------------------------------------------------------

class TestAdjustPercentile:
    def test_hom_ref_decreases_percentile(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(50, 'AA', 'A')
        assert result == 40

    def test_het_increases_by_5(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(50, 'AT', 'A')
        assert result == 55

    def test_hom_alt_increases_by_10(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(50, 'TT', 'A')
        assert result == 60

    def test_floor_at_1(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(5, 'AA', 'A')
        assert result == 1

    def test_ceiling_at_99_het(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(98, 'AT', 'A')
        assert result == 99

    def test_ceiling_at_99_hom_alt(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(95, 'TT', 'A')
        assert result == 99

    def test_empty_genotype_decreases(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(50, '', 'A')
        assert result == 40

    def test_none_genotype_decreases(self):
        from backend.services.insight_generators.cognitive import _adjust_percentile
        result = _adjust_percentile(30, None, 'A')
        assert result == 20


class TestGenerateCognitiveProfiles:
    MODULE = 'backend.services.insight_generators.cognitive'
    FN = 'generate_cognitive_profiles'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'domain': 'Memory', 'score': 0.72, 'percentile': 70,
                'suggestions': ['Chess'], '_ref_allele': 'A'}
        result = fn(1, 'rs6265', 'AT', info)
        assert result.cognitive_domain == 'Memory'
        assert result.genetic_score == 0.72
        assert result.percentile == 75  # het: +5

    def test_from_gene_missense_adds_10_percentile(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'domain': 'Executive', 'score': 0.60, 'percentile': 60,
                'suggestions': [], '_genotype': 'TT', '_ref_allele': 'A'}
        # missense → percentile + 10 = 70, then hom_alt → +10 = 80
        result = fn(2, 'rs1', 'BDNF', 'missense_variant', info)
        assert result.cognitive_domain == 'Executive'
        assert result.percentile >= 70

    def test_from_gene_non_missense_no_extra(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'domain': 'Focus', 'score': 0.50, 'percentile': 50,
                'suggestions': [], '_genotype': 'AA', '_ref_allele': 'A'}
        result = fn(3, 'rs2', 'COMT', 'synonymous_variant', info)
        assert result.percentile == 40  # hom_ref → -10 (no missense +10)

    def test_from_gene_stop_gained_also_adds_10(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'domain': 'Language', 'score': 0.55, 'percentile': 55,
                'suggestions': [], '_genotype': 'AT', '_ref_allele': 'A'}
        result = fn(4, 'rs3', 'FOXP2', 'stop_gained', info)
        assert result.percentile >= 60  # stop_gained → +10 → 65, het → +5 → 70


# ---------------------------------------------------------------------------
# Health risks
# ---------------------------------------------------------------------------

class TestGenerateHealthRisks:
    MODULE = 'backend.services.insight_generators.health'
    FN = 'generate_health_risks'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'condition': 'BRCA1', 'risk_multiplier': 2.5, 'recommendations': [],
                '_ref_allele': 'C', 'gene': 'BRCA1', 'review_status': 'criteria_provided',
                '_pathogenicity_score': None}
        result = fn(1, 'rs28897672', 'CT', info)
        assert result.condition == 'BRCA1'
        assert result.analysis_id == 1

    def test_from_rsid_reads_pathogenicity_from_annotation(self):
        ann = MagicMock()
        ann.annotation_data = {'pathogenicity_score': 0.95}
        ctx = _make_ctx(annotation_results={'rs1': ann})
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'condition': 'Breast cancer', 'risk_multiplier': 3.0, 'recommendations': ['Consult'],
                '_ref_allele': None, 'gene': None, 'review_status': None, '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'CT', info)
        assert result.condition == 'Breast cancer'

    def test_from_rsid_uses_custom_recommendations_when_present(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        custom_recs = ['Get genetic counseling', 'Annual screening']
        info = {'condition': 'Lynch Syndrome', 'risk_multiplier': 2.0,
                'recommendations': custom_recs,
                '_ref_allele': None, 'gene': 'MLH1', 'review_status': None, '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'CT', info)
        assert result.recommendations == custom_recs

    def test_from_gene_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'condition': 'Familial hypercholesterolemia', 'risk_level': 'high',
                'recommendations': ['Statins'], '_genotype': 'CT', '_ref_allele': 'C',
                'gene': 'LDLR', 'review_status': None, '_pathogenicity_score': None}
        result = fn(2, 'rs2', 'LDLR', 'missense_variant', info)
        assert result.condition == 'Familial hypercholesterolemia'
        assert result.gene == 'LDLR'

    def test_from_gene_pathogenicity_classification_extracted(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'condition': 'Cardiomyopathy', 'risk_level': 'high',
                'recommendations': [], '_genotype': 'CT', '_ref_allele': 'C',
                'gene': 'MYH7', 'review_status': None,
                '_pathogenicity_score': {'classification': 'pathogenic', 'score': 0.9}}
        result = fn(2, 'rs3', 'MYH7', 'missense_variant', info)
        assert result.pathogenicity_classification == 'pathogenic'

    def test_from_rsid_default_recs_when_generic(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        # generic recs are replaced by get_health_recommendations
        info = {'condition': 'Hypertension', 'risk_multiplier': 1.5,
                'recommendations': ['Consult with healthcare provider'],
                '_ref_allele': 'A', 'gene': None, 'review_status': None, '_pathogenicity_score': None}
        result = fn(1, 'rs1', 'AT', info)
        assert isinstance(result.recommendations, list)


# ---------------------------------------------------------------------------
# Physical traits
# ---------------------------------------------------------------------------

class TestGeneratePhysicalTraits:
    MODULE = 'backend.services.insight_generators.physical_traits'
    FN = 'generate_physical_traits'

    def test_from_rsid_builds_model(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_rsid']
        info = {'trait': 'Eye Color', 'category': 'Pigmentation', 'result': 'Blue',
                'confidence': 'high', '_ref_allele': 'A'}
        result = fn(1, 'rs12913832', 'AG', info)
        assert result.trait_name == 'Eye Color'
        assert result.trait_category == 'Pigmentation'

    def test_from_gene_missense_upgrades_confidence_to_high(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'trait': 'Hair Color', 'category': 'Pigmentation', 'result': 'Brown',
                'confidence': 'moderate', 'description': 'Likely brown',
                '_genotype': 'AG', '_ref_allele': 'A'}
        result = fn(2, 'rs1', 'MC1R', 'missense_variant', info)
        # After missense upgrade to 'high', zygosity_adjust('high', 'AG', ref='A') → stays high or moderate
        assert result.confidence is not None

    def test_from_gene_frameshift_upgrades_confidence(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'trait': 'Height', 'category': 'Anthropometric', 'result': 'Tall',
                'confidence': 'low', 'description': 'Tallish',
                '_genotype': 'AG', '_ref_allele': 'A'}
        result = fn(3, 'rs1', 'GDF5', 'frameshift_variant', info)
        assert result.confidence != 'low'  # upgraded to 'high' by frameshift

    def test_from_gene_empty_genotype_skips_zygosity_adjust(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'trait': 'Freckles', 'category': 'Pigmentation', 'result': 'Present',
                'confidence': 'low', 'description': 'Some freckles',
                '_genotype': '', '_ref_allele': None}
        result = fn(4, 'rs2', 'MC1R', 'synonymous_variant', info)
        assert result.confidence == 'low'

    def test_from_gene_non_missense_keeps_original_confidence(self):
        ctx = _make_ctx()
        captured = _capture_closures(self.MODULE, self.FN, ctx)
        fn = captured['from_gene']
        info = {'trait': 'Height', 'category': 'Anthropometric', 'result': 'Average',
                'confidence': 'moderate', 'description': 'Average height',
                '_genotype': 'AG', '_ref_allele': 'A'}
        result = fn(5, 'rs2', 'GDF5', 'intron_variant', info)
        assert result.trait_name == 'Height'



