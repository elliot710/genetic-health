"""Tests for sex-linked filtering, GWAS enrichment, and ClinGen validation."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.insight_generators.base import (
    should_skip_sex_linked,
    classify_gwas_trait,
    extract_gwas_insights,
    get_clingen_validity,
    VariantProfile,
)


class TestSexLinkedFiltering:
    def test_skip_rett_for_male(self):
        assert should_skip_sex_linked(
            'rs267608531', 'Rett syndrome', 'MECP2', 'X', 'male'
        ) is True

    def test_skip_atypical_rett_for_male(self):
        assert should_skip_sex_linked(
            'rs123', 'Atypical Rett syndrome', 'CDKL5', 'X', 'male'
        ) is True

    def test_allow_rett_for_female(self):
        assert should_skip_sex_linked(
            'rs267608531', 'Rett syndrome', 'MECP2', 'X', 'female'
        ) is False

    def test_allow_non_x_condition(self):
        assert should_skip_sex_linked(
            'rs123', 'Type 2 diabetes', 'TCF7L2', '10', 'male'
        ) is False

    def test_allow_unknown_sex(self):
        assert should_skip_sex_linked(
            'rs267608531', 'Rett syndrome', 'MECP2', 'X', 'unknown'
        ) is False

    def test_allow_no_sex(self):
        assert should_skip_sex_linked(
            'rs267608531', 'Rett syndrome', 'MECP2', 'X', None
        ) is False

    def test_allow_x_non_rett_for_male(self):
        assert should_skip_sex_linked(
            'rs123', 'Hemophilia A', 'F8', 'X', 'male'
        ) is False

    def test_no_chromosome(self):
        assert should_skip_sex_linked(
            'rs123', 'Rett syndrome', 'MECP2', None, 'male'
        ) is False

    def test_case_insensitive_condition(self):
        assert should_skip_sex_linked(
            'rs123', 'RETT SYNDROME', 'MECP2', 'X', 'male'
        ) is True


class TestClassifyGwasTrait:
    def test_intelligence(self):
        assert classify_gwas_trait('Intelligence') == 'cognitive'

    def test_educational_attainment(self):
        assert classify_gwas_trait('Educational attainment (years of education)') == 'cognitive'

    def test_neuroticism(self):
        assert classify_gwas_trait('Neuroticism') == 'personality'

    def test_adventurousness(self):
        assert classify_gwas_trait('Adventurousness') == 'personality'

    def test_risk_taking(self):
        assert classify_gwas_trait('Risk-taking behavior (multivariate analysis)') == 'personality'

    def test_grip_strength(self):
        assert classify_gwas_trait('Hand grip strength (baseline)') == 'sports'

    def test_height(self):
        assert classify_gwas_trait('Height') == 'physical'

    def test_hair_color(self):
        assert classify_gwas_trait('Hair color') == 'physical'

    def test_caffeine(self):
        assert classify_gwas_trait('Caffeine metabolism') == 'nutrition'

    def test_omega_fatty(self):
        assert classify_gwas_trait('Omega-3 fatty acid levels') == 'nutrition'

    def test_sleep_duration(self):
        assert classify_gwas_trait('Sleep duration') == 'wellness'

    def test_insomnia(self):
        assert classify_gwas_trait('Insomnia') == 'wellness'

    def test_unrecognized(self):
        assert classify_gwas_trait('Platelet count') is None

    def test_type2_diabetes(self):
        assert classify_gwas_trait('Type 2 diabetes') is None

    def test_cognitive_performance(self):
        assert classify_gwas_trait('Cognitive performance (MTAG)') == 'cognitive'

    def test_well_being(self):
        assert classify_gwas_trait('Well-being spectrum (multivariate analysis)') == 'personality'


class TestExtractGwasInsights:
    def _make_ar(self, associations):
        ar = MagicMock()
        ar.annotation_data = {
            'annotations': {
                'gwas_catalog': {
                    'found': True,
                    'associations': associations,
                    'genome_wide_significant': True,
                }
            }
        }
        return ar

    def test_extracts_gws_associations(self):
        ar = self._make_ar([
            {'trait': 'Adventurousness', 'p_value': 2e-8, 'p_value_mlog': 7.7, 'study_accession': 'GCST001'},
            {'trait': 'Intelligence', 'p_value': 1e-15, 'p_value_mlog': 15.0, 'study_accession': 'GCST002'},
        ])
        insights = extract_gwas_insights(ar)
        assert len(insights) == 2
        categories = {i['category'] for i in insights}
        assert 'personality' in categories
        assert 'cognitive' in categories

    def test_skips_non_significant(self):
        ar = self._make_ar([
            {'trait': 'Adventurousness', 'p_value': 1e-5, 'p_value_mlog': 5.0},
        ])
        insights = extract_gwas_insights(ar)
        assert len(insights) == 0

    def test_skips_unrecognized_traits(self):
        ar = self._make_ar([
            {'trait': 'Platelet count', 'p_value': 1e-30, 'p_value_mlog': 30.0},
        ])
        insights = extract_gwas_insights(ar)
        assert len(insights) == 0

    def test_deduplicates_per_category(self):
        ar = self._make_ar([
            {'trait': 'Intelligence', 'p_value': 1e-15, 'p_value_mlog': 15.0},
            {'trait': 'Cognitive performance', 'p_value': 1e-10, 'p_value_mlog': 10.0},
        ])
        insights = extract_gwas_insights(ar)
        assert len(insights) == 1

    def test_no_annotations(self):
        ar = MagicMock()
        ar.annotation_data = None
        assert extract_gwas_insights(ar) == []

    def test_no_gwas(self):
        ar = MagicMock()
        ar.annotation_data = {'annotations': {}}
        assert extract_gwas_insights(ar) == []


class TestGetClingenValidity:
    def test_returns_definitive(self):
        ar = MagicMock()
        ar.annotation_data = {
            'annotations': {
                'clingen': {
                    'found': True,
                    'strongest_classification': 'Definitive',
                }
            }
        }
        assert get_clingen_validity(ar) == 'Definitive'

    def test_returns_disputed(self):
        ar = MagicMock()
        ar.annotation_data = {
            'annotations': {
                'clingen': {
                    'found': True,
                    'strongest_classification': 'Disputed',
                }
            }
        }
        assert get_clingen_validity(ar) == 'Disputed'

    def test_returns_none_no_clingen(self):
        ar = MagicMock()
        ar.annotation_data = {'annotations': {}}
        assert get_clingen_validity(ar) is None

    def test_returns_none_not_found(self):
        ar = MagicMock()
        ar.annotation_data = {
            'annotations': {
                'clingen': {'found': False}
            }
        }
        assert get_clingen_validity(ar) is None


class TestHealthClingenSkip:
    def _make_variant(self, rsid, genotype='AG', chromosome='1'):
        v = MagicMock()
        v.rsid = rsid
        v.chromosome = chromosome
        v.genotype = genotype
        v.marker = MagicMock()
        v.marker.rsid = rsid
        v.marker.ref_allele = 'A'
        v.marker.alt_alleles = 'G'
        v.marker.chromosome = chromosome
        v.info = None
        return v

    def _make_annotation_result(self, clingen_classification=None, clinvar_sig='pathogenic'):
        ar = MagicMock()
        annotations = {
            'clinvar_local': {
                'found': True,
                'clinical_significances': [clinvar_sig],
                'ref_allele': 'A',
            },
            'ensembl': {
                'data': [{'allele_string': 'A/G', 'transcript_consequences': [
                    {'gene_symbol': 'TEST', 'consequence_terms': ['missense_variant'], 'impact': 'MODERATE'}
                ]}]
            },
        }
        if clingen_classification:
            annotations['clingen'] = {
                'found': True,
                'strongest_classification': clingen_classification,
            }
        ar.annotation_data = {
            'annotations': annotations,
            'pathogenicity_score': {'composite_score': 0.8, 'classification': 'pathogenic'},
        }
        ar.rsid = 'rs123'
        return ar

    @pytest.mark.asyncio
    async def test_disputed_clingen_skips_health_risk(self):
        from backend.services.insight_generators.health import generate_health_risks
        from backend.services.insight_generators.base import GeneratorContext, VariantProfile

        variant = self._make_variant('rs123')
        ar = self._make_annotation_result(clingen_classification='Disputed')

        profile = VariantProfile(
            rsid='rs123', genotype='AG', effective_ref='A', gene='TEST',
            consequence='missense_variant', impact='MODERATE', chromosome='1',
            population_frequency=0.001, clinical_significance='pathogenic',
            is_benign=False, is_hom_ref=False, is_het=True, is_no_call=False,
            composite_score=0.8,
            pathogenicity_score={'composite_score': 0.8, 'classification': 'pathogenic', 'evidence_count': 3},
            annotation_result=ar, variant=variant,
        )

        session = AsyncMock()
        ctx = GeneratorContext(
            analysis_id=1,
            variants=[variant],
            annotation_results={'rs123': ar},
            session=session,
            rsid_gene_map={'rs123': 'TEST'},
            registry={
                'health': {
                    'rsid': {
                        'rs123': {
                            'condition': 'Test condition',
                            'gene': 'TEST',
                            'risk_multiplier': 1.5,
                            'clinical_significance': 'pathogenic',
                        }
                    },
                    'gene': {},
                }
            },
            variant_profiles={'rs123': profile},
        )

        count = await generate_health_risks(ctx)
        assert count == 0

    @pytest.mark.asyncio
    async def test_definitive_clingen_allows_health_risk(self):
        from backend.services.insight_generators.health import generate_health_risks
        from backend.services.insight_generators.base import GeneratorContext, VariantProfile

        variant = self._make_variant('rs123')
        ar = self._make_annotation_result(clingen_classification='Definitive')

        profile = VariantProfile(
            rsid='rs123', genotype='AG', effective_ref='A', gene='TEST',
            consequence='missense_variant', impact='MODERATE', chromosome='1',
            population_frequency=0.001, clinical_significance='pathogenic',
            is_benign=False, is_hom_ref=False, is_het=True, is_no_call=False,
            composite_score=0.8,
            pathogenicity_score={'composite_score': 0.8, 'classification': 'pathogenic', 'evidence_count': 3},
            annotation_result=ar, variant=variant,
        )

        session = AsyncMock()
        ctx = GeneratorContext(
            analysis_id=1,
            variants=[variant],
            annotation_results={'rs123': ar},
            session=session,
            rsid_gene_map={'rs123': 'TEST'},
            registry={
                'health': {
                    'rsid': {
                        'rs123': {
                            'condition': 'Test condition',
                            'gene': 'TEST',
                            'risk_multiplier': 1.5,
                            'clinical_significance': 'pathogenic',
                        }
                    },
                    'gene': {},
                }
            },
            variant_profiles={'rs123': profile},
        )

        count = await generate_health_risks(ctx)
        assert count == 1


class TestGwasEnrichment:
    def _make_variant(self, rsid, genotype='AG', chromosome='1'):
        v = MagicMock()
        v.rsid = rsid
        v.chromosome = chromosome
        v.genotype = genotype
        v.marker = MagicMock()
        v.marker.rsid = rsid
        v.marker.ref_allele = 'A'
        v.marker.alt_alleles = 'G'
        v.marker.chromosome = chromosome
        v.info = None
        return v

    def _make_ar_with_gwas(self, traits_with_pvalues):
        ar = MagicMock()
        associations = []
        for trait, p_val in traits_with_pvalues:
            associations.append({
                'trait': trait,
                'p_value': p_val,
                'p_value_mlog': -1,
                'study_accession': 'GCST001',
                'risk_allele_frequency': 0.3,
            })
        ar.annotation_data = {
            'annotations': {
                'gwas_catalog': {
                    'found': True,
                    'associations': associations,
                    'genome_wide_significant': True,
                },
                'ensembl': {
                    'data': [{'allele_string': 'A/G', 'transcript_consequences': [
                        {'gene_symbol': 'TEST', 'consequence_terms': ['missense_variant'], 'impact': 'MODERATE'}
                    ]}]
                },
            },
        }
        ar.rsid = 'rs999'
        return ar

    @pytest.mark.asyncio
    async def test_generates_personality_from_gwas(self):
        from backend.services.insight_generators.gwas_enrichment import generate_gwas_enrichment
        from backend.services.insight_generators.base import GeneratorContext, VariantProfile

        variant = self._make_variant('rs999')
        ar = self._make_ar_with_gwas([('Adventurousness', 2e-8)])

        profile = VariantProfile(
            rsid='rs999', genotype='AG', effective_ref='A', gene='TEST',
            consequence='missense_variant', impact='MODERATE', chromosome='1',
            population_frequency=0.3, clinical_significance=None,
            is_benign=False, is_hom_ref=False, is_het=True, is_no_call=False,
            composite_score=0.3, pathogenicity_score=None,
            annotation_result=ar, variant=variant,
        )

        session = AsyncMock()
        ctx = GeneratorContext(
            analysis_id=1,
            variants=[variant],
            annotation_results={'rs999': ar},
            session=session,
            rsid_gene_map={},
            registry={'personality': {'rsid': {}, 'gene': {}}},
            variant_profiles={'rs999': profile},
        )

        count = await generate_gwas_enrichment(ctx, {})
        assert count == 1
        session.add.assert_called_once()
        item = session.add.call_args[0][0]
        assert item.trait_name == 'Adventurousness'

    @pytest.mark.asyncio
    async def test_skips_existing_dedup_key(self):
        from backend.services.insight_generators.gwas_enrichment import generate_gwas_enrichment
        from backend.services.insight_generators.base import GeneratorContext, VariantProfile

        variant = self._make_variant('rs999')
        ar = self._make_ar_with_gwas([('Adventurousness', 2e-8)])

        profile = VariantProfile(
            rsid='rs999', genotype='AG', effective_ref='A', gene='TEST',
            consequence='missense_variant', impact='MODERATE', chromosome='1',
            population_frequency=0.3, clinical_significance=None,
            is_benign=False, is_hom_ref=False, is_het=True, is_no_call=False,
            composite_score=0.3, pathogenicity_score=None,
            annotation_result=ar, variant=variant,
        )

        session = AsyncMock()
        ctx = GeneratorContext(
            analysis_id=1,
            variants=[variant],
            annotation_results={'rs999': ar},
            session=session,
            rsid_gene_map={},
            registry={},
            variant_profiles={'rs999': profile},
        )

        count = await generate_gwas_enrichment(ctx, {'personality': {'Adventurousness'}})
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_categories(self):
        from backend.services.insight_generators.gwas_enrichment import generate_gwas_enrichment
        from backend.services.insight_generators.base import GeneratorContext, VariantProfile

        variant = self._make_variant('rs999')
        ar = self._make_ar_with_gwas([
            ('Adventurousness', 2e-8),
            ('Intelligence', 1e-15),
            ('Sleep duration', 3e-9),
        ])

        profile = VariantProfile(
            rsid='rs999', genotype='AG', effective_ref='A', gene='TEST',
            consequence='missense_variant', impact='MODERATE', chromosome='1',
            population_frequency=0.3, clinical_significance=None,
            is_benign=False, is_hom_ref=False, is_het=True, is_no_call=False,
            composite_score=0.3, pathogenicity_score=None,
            annotation_result=ar, variant=variant,
        )

        session = AsyncMock()
        ctx = GeneratorContext(
            analysis_id=1,
            variants=[variant],
            annotation_results={'rs999': ar},
            session=session,
            rsid_gene_map={},
            registry={},
            variant_profiles={'rs999': profile},
        )

        count = await generate_gwas_enrichment(ctx, {})
        assert count == 3

    @pytest.mark.asyncio
    async def test_skips_hom_ref(self):
        from backend.services.insight_generators.gwas_enrichment import generate_gwas_enrichment
        from backend.services.insight_generators.base import GeneratorContext, VariantProfile

        variant = self._make_variant('rs999', genotype='AA')
        ar = self._make_ar_with_gwas([('Adventurousness', 2e-8)])

        profile = VariantProfile(
            rsid='rs999', genotype='AA', effective_ref='A', gene='TEST',
            consequence='missense_variant', impact='MODERATE', chromosome='1',
            population_frequency=0.3, clinical_significance=None,
            is_benign=False, is_hom_ref=True, is_het=False, is_no_call=False,
            composite_score=0.3, pathogenicity_score=None,
            annotation_result=ar, variant=variant,
        )

        session = AsyncMock()
        ctx = GeneratorContext(
            analysis_id=1,
            variants=[variant],
            annotation_results={'rs999': ar},
            session=session,
            rsid_gene_map={},
            registry={},
            variant_profiles={'rs999': profile},
        )

        count = await generate_gwas_enrichment(ctx, {})
        assert count == 0


class TestPValueDisplay:
    def test_normal_p_value(self):
        from backend.services.insight_generators.gwas_enrichment import _p_value_display
        result = _p_value_display(2e-8)
        assert "e-8" in result

    def test_zero_p_value(self):
        from backend.services.insight_generators.gwas_enrichment import _p_value_display
        assert _p_value_display(0) == "< 1e-300"

    def test_subnormal_p_value(self):
        from backend.services.insight_generators.gwas_enrichment import _p_value_display
        assert _p_value_display(5e-324) == "< 1e-300"

    def test_very_small_but_normal(self):
        from backend.services.insight_generators.gwas_enrichment import _p_value_display
        result = _p_value_display(1e-200)
        assert "e-200" in result
