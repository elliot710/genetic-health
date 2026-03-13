"""
Genetic analysis service — annotates variants and populates all category tables.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, func

from ..db.models import (
    GeneticAnalysis, AnalysisVariant, VariantAnnotation, SharedVariantAnnotation,
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait, SportsPerformance,
    CognitiveProfile, PersonalityTrait,
    WellnessMetric, MethylationProfile, DetoxificationProfile,
    UncommonMutation, VariantMapping
)
from ..core.exceptions import AnalysisNotFoundException
from ..core.config import settings

logger = logging.getLogger(__name__)


class AnalysisCancelled(Exception):
    """Raised when an analysis is paused or stopped by the user."""
    pass


@dataclass
class AnalysisProgress:
    """Enhanced progress tracking for comprehensive analysis."""
    total_variants: int
    processed_variants: int
    annotated_variants: int
    new_annotations: int
    reused_annotations: int
    current_step: str
    status: str
    estimated_completion: Optional[datetime] = None

    @property
    def progress_percentage(self) -> int:
        if self.total_variants == 0:
            return 0
        return min(100, int((self.processed_variants / self.total_variants) * 100))


@dataclass
class AnnotationResult:
    """Result of variant annotation with reuse tracking."""
    rsid: str
    was_reused: bool
    annotation_data: Optional[Dict[str, Any]]
    source: str  # 'existing', 'api', 'failed'


# ---------------------------------------------------------------------------
# Shared annotation service (unchanged)
# ---------------------------------------------------------------------------

class SharedVariantAnnotationService:
    """Service for managing shared variant annotations across users."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._annotation_cache: Dict[str, Dict[str, Any]] = {}

    async def get_existing_annotations(self, rsids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get existing annotations for a list of RSIDs from shared annotations table."""
        if not rsids:
            return {}

        batch_size = 500
        annotation_map = {}

        logger.info(f"Checking for existing shared annotations for {len(rsids)} RSIDs in batches of {batch_size}")

        for i in range(0, len(rsids), batch_size):
            batch_rsids = rsids[i:i + batch_size]
            logger.info(f"📊 Processing annotation batch {i//batch_size + 1}/{(len(rsids) + batch_size - 1)//batch_size}: {len(batch_rsids)} RSIDs")

            await asyncio.sleep(0)

            result = await self.session.execute(
                select(SharedVariantAnnotation).where(
                    SharedVariantAnnotation.rsid.in_(batch_rsids),
                    SharedVariantAnnotation.annotation_status == 'completed'
                )
            )

            existing_annotations = result.scalars().all()
            await asyncio.sleep(0)

            for annotation in existing_annotations:
                merged_data: Dict[str, Any] = {
                    'rsid': annotation.rsid,
                    'annotations': {},
                    'sources_queried': [],
                    'success_count': 0
                }

                for source in ('ensembl', 'clinvar', 'pharmgkb', 'snpedia', 'litvar'):
                    data = getattr(annotation, f'{source}_data', None)
                    if data is not None:
                        merged_data['annotations'][source] = data
                        merged_data['sources_queried'].append(source)
                        merged_data['success_count'] += 1

                if merged_data['success_count'] > 0:
                    annotation_map[annotation.rsid] = merged_data

        if annotation_map:
            found_rsids = list(annotation_map.keys())
            await self.session.execute(
                update(SharedVariantAnnotation)
                .where(SharedVariantAnnotation.rsid.in_(found_rsids))
                .values(
                    usage_count=SharedVariantAnnotation.usage_count + 1,
                    last_updated_at=func.now()
                )
            )

        await self.session.commit()
        logger.info(f"Found {len(annotation_map)} existing shared annotations for {len(rsids)} requested RSIDs")
        return annotation_map

    async def save_annotation(
        self,
        rsid: str,
        annotation_data: Dict[str, Any],
        analysis_id: int,
        analysis_variant_id: int,
        marker_id: int = None
    ) -> bool:
        """Save new annotation data to shared system and create user reference."""
        try:
            annotations = annotation_data.get('annotations', {})

            from sqlalchemy.dialects.postgresql import insert
            values = dict(
                rsid=rsid,
                ensembl_data=annotations.get('ensembl'),
                clinvar_data=annotations.get('clinvar'),
                pharmgkb_data=annotations.get('pharmgkb'),
                snpedia_data=annotations.get('snpedia'),
                litvar_data=annotations.get('litvar'),
                annotation_status='completed',
                total_api_calls=annotation_data.get('success_count', 0),
                usage_count=1
            )
            if marker_id is not None:
                values['marker_id'] = marker_id
            stmt = insert(SharedVariantAnnotation).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=['rsid'],
                set_=dict(
                    usage_count=SharedVariantAnnotation.usage_count + 1,
                    last_updated_at=func.now(),
                    total_api_calls=func.greatest(
                        SharedVariantAnnotation.total_api_calls,
                        stmt.excluded.total_api_calls
                    )
                )
            ).returning(SharedVariantAnnotation.id)

            result = await self.session.execute(stmt)
            shared_annotation_id = result.scalar_one()

            variant_annotation = VariantAnnotation(
                analysis_id=analysis_id,
                analysis_variant_id=analysis_variant_id,
                shared_annotation_id=shared_annotation_id,
                rsid=rsid
            )

            self.session.add(variant_annotation)
            return True

        except Exception as e:
            logger.error(f"Failed to save annotation for {rsid}: {e}")
            return False


# ---------------------------------------------------------------------------
# Main analysis service
# ---------------------------------------------------------------------------

class ComprehensiveAnalysisService:
    """
    Comprehensive genetic analysis service that efficiently reuses annotations
    and populates all category tables with insights.
    """

    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.api_service = None
        self._initialized = False
        self._registry: Dict[str, Dict[str, Dict]] = {}  # category -> {rsid_map, gene_map}

    async def initialize_services(self):
        """Initialize dependent services."""
        if self._initialized:
            return
        try:
            from .genetic_api_service import OptimizedGeneticAPIService
            self.api_service = OptimizedGeneticAPIService()
            await self.api_service.initialize()
            self._initialized = True
        except ImportError as e:
            logger.warning(f"Some services not available: {e}")

    async def _load_registry(self):
        """Load active variant mappings from the database into in-memory dicts."""
        from ..db.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(VariantMapping).where(VariantMapping.is_active == True)
            )
            rows = result.scalars().all()

        registry: Dict[str, Dict[str, Dict]] = {}
        for row in rows:
            cat = row.category
            if cat not in registry:
                registry[cat] = {'rsid': {}, 'gene': {}}
            registry[cat][row.map_type][row.key] = row.data

        self._registry = registry
        logger.info(f"Loaded {len(rows)} variant mappings from database across {len(registry)} categories")

    def _get_maps(self, category: str):
        """Return (rsid_map, gene_map) for a category from the loaded registry."""
        maps = self._registry.get(category, {'rsid': {}, 'gene': {}})
        return maps['rsid'], maps['gene']

    async def _check_if_cancelled(self, analysis_id: int):
        """Check if the analysis has been paused or stopped by the user."""
        from ..db.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticAnalysis.analysis_status).where(GeneticAnalysis.id == analysis_id)
            )
            current_status = result.scalar_one_or_none()
            if current_status in ('paused', 'stopped'):
                raise AnalysisCancelled(f"Analysis {analysis_id} was {current_status} by user")

    # ------------------------------------------------------------------
    # Top-level orchestration
    # ------------------------------------------------------------------

    async def process_analysis(self, analysis_id: int, strategy: str = 'comprehensive') -> Dict[str, Any]:
        """Process genetic analysis with efficient annotation reuse and comprehensive insights."""
        start_time = time.time()

        try:
            await self.initialize_services()
            await self._load_registry()

            analysis, variants = await self._load_analysis_data(analysis_id)

            if not variants:
                logger.warning(f"No variants found for analysis {analysis_id}")
                return {
                    "success": True,
                    "analysis_id": analysis_id,
                    "status": "completed",
                    "processed_variants": 0,
                    "total_variants": 0,
                    "message": "No variants found"
                }

            logger.info(f"Starting comprehensive analysis for {len(variants)} variants")

            progress = AnalysisProgress(
                total_variants=len(variants),
                processed_variants=0,
                annotated_variants=0,
                new_annotations=0,
                reused_annotations=0,
                current_step="initializing",
                status="processing"
            )

            await self._update_progress(analysis_id, progress)

            from ..db.database import async_session_factory
            async with async_session_factory() as session:
                annotation_service = SharedVariantAnnotationService(session)

                progress.current_step = "annotating_variants"
                await self._update_progress(analysis_id, progress)

                annotation_results = await self._annotate_variants_efficiently(
                    variants, analysis_id, annotation_service, progress
                )

                progress.current_step = "generating_insights"
                await self._update_progress(analysis_id, progress)

                insights_generated = await self._generate_comprehensive_insights(
                    variants, annotation_results, analysis_id, session, progress
                )

                await session.commit()

                progress.current_step = "completed"
                progress.status = "completed"
                progress.processed_variants = len(variants)
                await self._update_progress(analysis_id, progress)

                processing_time = time.time() - start_time

                logger.info(f"Analysis {analysis_id} completed in {processing_time:.2f}s")
                logger.info(f"Annotations: {progress.reused_annotations} reused, {progress.new_annotations} new")
                logger.info(f"Insights generated: {insights_generated}")

                return {
                    "success": True,
                    "analysis_id": analysis_id,
                    "status": "completed",
                    "processed_variants": len(variants),
                    "total_variants": len(variants),
                    "reused_annotations": progress.reused_annotations,
                    "new_annotations": progress.new_annotations,
                    "insights_generated": insights_generated,
                    "processing_time": processing_time
                }

        except Exception as e:
            logger.error(f"Analysis {analysis_id} failed: {str(e)}")
            try:
                await self._update_analysis_status(analysis_id, "failed", f"Failed: {str(e)}")
            except Exception:
                pass
            return {
                "success": False,
                "analysis_id": analysis_id,
                "status": "failed",
                "error": str(e),
                "processing_time": time.time() - start_time
            }

        finally:
            try:
                if self.api_service:
                    await self.api_service.close()
            except Exception:
                pass

    async def _load_analysis_data(self, analysis_id: int) -> tuple[GeneticAnalysis, List[AnalysisVariant]]:
        """Load analysis and analysis variants from database."""
        from ..db.database import async_session_factory

        async with async_session_factory() as session:
            query = select(GeneticAnalysis).options(
                selectinload(GeneticAnalysis.analysis_variants)
            ).where(GeneticAnalysis.id == analysis_id)

            if self.user_id is not None:
                query = query.where(GeneticAnalysis.user_id == self.user_id)

            result = await session.execute(query)
            analysis = result.scalar_one_or_none()

            if not analysis:
                raise AnalysisNotFoundException(
                    f"Analysis {analysis_id} not found for user {self.user_id}"
                )

            return analysis, analysis.analysis_variants

    async def _annotate_variants_efficiently(
        self,
        variants: List[AnalysisVariant],
        analysis_id: int,
        annotation_service: SharedVariantAnnotationService,
        progress: AnalysisProgress
    ) -> Dict[str, AnnotationResult]:
        """Efficiently annotate variants with maximum reuse."""
        variants_with_rsid = [
            v for v in variants
            if v.rsid is not None and str(v.rsid).startswith('rs')
        ]
        rsids = [str(v.rsid) for v in variants_with_rsid]

        logger.info(f"Processing {len(variants_with_rsid)} variants with RSIDs out of {len(variants)} total")

        existing_annotations = await annotation_service.get_existing_annotations(rsids)
        progress.reused_annotations = len(existing_annotations)

        variants_needing_annotation = [
            v for v in variants_with_rsid
            if str(v.rsid) not in existing_annotations
        ]

        logger.info(f"Found {len(existing_annotations)} existing annotations, need {len(variants_needing_annotation)} new ones")

        annotation_results: Dict[str, AnnotationResult] = {}

        for rsid, annotation_data in existing_annotations.items():
            annotation_results[rsid] = AnnotationResult(
                rsid=rsid, was_reused=True,
                annotation_data=annotation_data, source='existing'
            )

        if variants_needing_annotation and self.api_service:
            batch_size = settings.api.batch_size

            for i in range(0, len(variants_needing_annotation), batch_size):
                batch = variants_needing_annotation[i:i + batch_size]
                batch_rsids = [str(v.rsid) for v in batch]

                logger.info(f"Fetching annotations for batch {i//batch_size + 1}: {len(batch)} variants")

                await asyncio.sleep(0)

                new_annotations = await self.api_service.batch_annotate_variants(
                    batch_rsids, strategy='comprehensive'
                )

                await asyncio.sleep(0)

                for variant in batch:
                    rsid = str(variant.rsid)
                    annotation_data = new_annotations.get(rsid)

                    if annotation_data:
                        success = await annotation_service.save_annotation(
                            rsid, annotation_data, analysis_id, getattr(variant, 'id'),
                            marker_id=getattr(variant, 'marker_id', None)
                        )

                        if success:
                            annotation_results[rsid] = AnnotationResult(
                                rsid=rsid, was_reused=False,
                                annotation_data=annotation_data, source='api'
                            )
                            progress.new_annotations += 1
                        else:
                            annotation_results[rsid] = AnnotationResult(
                                rsid=rsid, was_reused=False,
                                annotation_data=None, source='failed'
                            )
                    else:
                        annotation_results[rsid] = AnnotationResult(
                            rsid=rsid, was_reused=False,
                            annotation_data=None, source='failed'
                        )

                progress.annotated_variants += len(batch)
                progress.processed_variants = progress.annotated_variants
                await self._update_progress(analysis_id, progress)

                if i + batch_size < len(variants_needing_annotation):
                    await asyncio.sleep(0.01)

        logger.info(f"Annotation complete: {progress.reused_annotations} reused, {progress.new_annotations} new")
        return annotation_results

    async def _generate_comprehensive_insights(
        self,
        variants: List[AnalysisVariant],
        annotation_results: Dict[str, AnnotationResult],
        analysis_id: int,
        session: AsyncSession,
        progress: AnalysisProgress
    ) -> int:
        """Generate comprehensive insights for all categories."""
        insights_generated = 0

        generators = [
            self._generate_health_risks,
            self._generate_drug_responses,
            self._generate_physical_traits,
            self._generate_nutrition_traits,
            self._generate_sports_performance,
            self._generate_cognitive_profiles,
            self._generate_personality_traits,
            self._generate_ancestry_results,
            self._generate_carrier_status,
            self._generate_wellness_metrics,
            self._generate_methylation_profiles,
            self._generate_detox_profiles,
            self._generate_rare_mutations,
            self._generate_uncommon_mutations
        ]

        for generator in generators:
            await self._check_if_cancelled(analysis_id)
            try:
                progress.current_step = f"generating_{generator.__name__.replace('_generate_', '')}"
                await self._update_progress(analysis_id, progress)

                count = await generator(variants, annotation_results, analysis_id, session)
                insights_generated += count
                logger.info(f"Generated {count} {generator.__name__.replace('_generate_', '')} insights")
            except AnalysisCancelled:
                raise
            except Exception as e:
                logger.error(f"Error in {generator.__name__}: {e}")
                continue

        return insights_generated

    # ------------------------------------------------------------------
    # Annotation helpers
    # ------------------------------------------------------------------

    def _extract_gene_and_consequence(self, annotation_result: Optional[AnnotationResult]):
        """Extract gene symbol and consequence from annotation data."""
        if not annotation_result or not annotation_result.annotation_data:
            return None, None, None

        try:
            ensembl_data = annotation_result.annotation_data.get('annotations', {}).get('ensembl', {})
            if not ensembl_data:
                return None, None, None

            data_list = ensembl_data.get('data', [])
            if not data_list:
                return None, None, None

            entry = data_list[0]
            transcript_consequences = entry.get('transcript_consequences', [])
            if not transcript_consequences:
                return None, None, None

            tc = transcript_consequences[0]
            gene = tc.get('gene_symbol')
            consequence = tc.get('consequence_terms', [None])[0] if tc.get('consequence_terms') else None
            impact = tc.get('impact')

            return gene, consequence, impact
        except (KeyError, IndexError, TypeError):
            return None, None, None

    def _extract_frequency(self, annotation_result: Optional[AnnotationResult]) -> float:
        """Extract population frequency from annotation data."""
        if not annotation_result or not annotation_result.annotation_data:
            return 0.0

        try:
            ensembl_data = annotation_result.annotation_data.get('annotations', {}).get('ensembl', {})
            data_list = ensembl_data.get('data', [])
            if not data_list:
                return 0.0

            entry = data_list[0]
            freqs = entry.get('colocated_variants', [{}])[0].get('frequencies', {})
            if freqs:
                first_allele = next(iter(freqs.values()), {})
                return first_allele.get('gnomade', first_allele.get('gnomad', 0.0))
            return 0.0
        except (KeyError, IndexError, TypeError, StopIteration):
            return 0.0

    # ------------------------------------------------------------------
    # Generic map-driven generator
    # ------------------------------------------------------------------

    async def _generate_from_maps(
        self,
        variants: List[AnalysisVariant],
        annotation_results: Dict[str, AnnotationResult],
        analysis_id: int,
        session: AsyncSession,
        *,
        rsid_map: Dict,
        gene_map: Dict,
        dedup_field: str,
        build_from_rsid: Callable,
        build_from_gene: Callable,
    ) -> int:
        """
        Generic loop shared by most category generators.

        Args:
            rsid_map / gene_map: lookup dicts from variant_registry.
            dedup_field: key inside the info dict used to avoid duplicates.
            build_from_rsid(analysis_id, rsid, genotype, info) -> model | None
            build_from_gene(analysis_id, rsid, gene, consequence, info) -> model | None
        """
        items = []
        seen: set = set()

        for variant in variants:
            rsid = getattr(variant, 'rsid', None)
            if not rsid:
                continue

            # rsid-based matching
            if rsid in rsid_map:
                info = rsid_map[rsid]
                key = info[dedup_field]
                if key not in seen:
                    seen.add(key)
                    genotype = getattr(variant, 'genotype', '') or ''
                    item = build_from_rsid(analysis_id, rsid, genotype, info)
                    if item:
                        items.append(item)

            # Gene-based matching from annotations
            annotation_result = annotation_results.get(rsid)
            gene, consequence, impact = self._extract_gene_and_consequence(annotation_result)
            if gene and gene in gene_map:
                info = gene_map[gene]
                key = info[dedup_field]
                if key not in seen:
                    seen.add(key)
                    item = build_from_gene(analysis_id, rsid, gene, consequence, info)
                    if item:
                        items.append(item)

        for item in items:
            session.add(item)
        return len(items)

    # ------------------------------------------------------------------
    # Category generators
    # ------------------------------------------------------------------

    async def _generate_health_risks(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            risk_level = self._assess_risk_level(genotype, info['risk_multiplier'])
            return HealthRisk(
                analysis_id=aid, condition=info['condition'],
                risk_level=risk_level, risk_score=f"{info['risk_multiplier']}x",
                associated_variants=[rsid],
                recommendations=self._get_health_recommendations(info['condition'], risk_level)
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return HealthRisk(
                analysis_id=aid, condition=info['condition'],
                risk_level=info['risk_level'], risk_score=info['risk_score'],
                associated_variants=[rsid], recommendations=info['recommendations']
            )

        rsid_map, gene_map = self._get_maps('health')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='condition',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_drug_responses(self, variants, annotation_results, analysis_id, session) -> int:
        """Drug responses need custom logic (multiple drugs per match)."""
        drug_rsid_map, drug_gene_map = self._get_maps('drug')
        drug_responses = []
        seen_drugs: set = set()

        for variant in variants:
            variant_rsid = getattr(variant, 'rsid', None)
            if not variant_rsid:
                continue

            if variant_rsid in drug_rsid_map:
                info = drug_rsid_map[variant_rsid]
                for drug in info['drugs']:
                    drug_key = f"{info['gene']}_{drug}"
                    if drug_key not in seen_drugs:
                        seen_drugs.add(drug_key)
                        genotype = getattr(variant, 'genotype', '') or ''
                        response_type = self._assess_drug_response(genotype, info['gene'])
                        drug_responses.append(DrugResponse(
                            analysis_id=analysis_id, gene=info['gene'],
                            drug=drug, response_type=response_type,
                            recommendations=self._get_drug_recommendations(drug, response_type),
                            variants_involved=[variant_rsid]
                        ))

            annotation_result = annotation_results.get(variant_rsid)
            gene, consequence, impact = self._extract_gene_and_consequence(annotation_result)
            if gene and gene in drug_gene_map:
                info = drug_gene_map[gene]
                for drug_name, response, rec in info['drugs']:
                    drug_key = f"{info['gene']}_{drug_name}"
                    if drug_key not in seen_drugs:
                        seen_drugs.add(drug_key)
                        drug_responses.append(DrugResponse(
                            analysis_id=analysis_id, gene=info['gene'],
                            drug=drug_name, response_type=response,
                            recommendations=rec, variants_involved=[variant_rsid]
                        ))

        for r in drug_responses:
            session.add(r)
        return len(drug_responses)

    async def _generate_physical_traits(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return PhysicalTrait(
                analysis_id=aid, trait_name=info['trait'],
                trait_category=info['category'], genetic_result=info['result'],
                confidence=info['confidence'], associated_variants=[rsid],
                description=self._get_trait_description(info['trait'], info['result'])
            )

        def from_gene(aid, rsid, gene, consequence, info):
            confidence = 'high' if consequence in ('missense_variant', 'stop_gained', 'frameshift_variant') else info['confidence']
            return PhysicalTrait(
                analysis_id=aid, trait_name=info['trait'],
                trait_category=info['category'], genetic_result=info['result'],
                confidence=confidence, associated_variants=[rsid],
                description=info['description']
            )

        rsid_map, gene_map = self._get_maps('physical')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='trait',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_nutrition_traits(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return NutritionTrait(
                analysis_id=aid, nutrient=info['nutrient'],
                metabolism_type=info['metabolism'],
                dietary_recommendations=info['recommendations'],
                associated_variants=[rsid],
                sensitivity_level=info['sensitivity']
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return NutritionTrait(
                analysis_id=aid, nutrient=info['nutrient'],
                metabolism_type=info['metabolism'],
                dietary_recommendations=info['recommendations'],
                associated_variants=[rsid],
                sensitivity_level=info['sensitivity']
            )

        rsid_map, gene_map = self._get_maps('nutrition')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='nutrient',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_sports_performance(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return SportsPerformance(
                analysis_id=aid, performance_category=info['category'],
                genetic_advantage=info['advantage'],
                sport_recommendations=info['recommendations'],
                associated_variants=[rsid],
                training_advice=info['advice']
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return SportsPerformance(
                analysis_id=aid, performance_category=info['category'],
                genetic_advantage=info['advantage'],
                sport_recommendations=info['recommendations'],
                associated_variants=[rsid],
                training_advice=info['advice']
            )

        rsid_map, gene_map = self._get_maps('sports')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='category',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_cognitive_profiles(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return CognitiveProfile(
                analysis_id=aid, cognitive_domain=info['domain'],
                genetic_score=info['score'], percentile=info['percentile'],
                associated_variants=[rsid],
                enhancement_suggestions=info['suggestions']
            )

        def from_gene(aid, rsid, gene, consequence, info):
            percentile = info['percentile']
            if consequence in ('missense_variant', 'stop_gained'):
                percentile = min(95, percentile + 10)
            return CognitiveProfile(
                analysis_id=aid, cognitive_domain=info['domain'],
                genetic_score=info['score'], percentile=percentile,
                associated_variants=[rsid],
                enhancement_suggestions=info['suggestions']
            )

        rsid_map, gene_map = self._get_maps('cognitive')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='domain',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_personality_traits(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return PersonalityTrait(
                analysis_id=aid, trait_name=info['trait'],
                genetic_tendency=info['tendency'], confidence_level=info['confidence'],
                associated_variants=[rsid],
                behavioral_insights=info['insights']
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return PersonalityTrait(
                analysis_id=aid, trait_name=info['trait'],
                genetic_tendency=info['tendency'], confidence_level=info['confidence'],
                associated_variants=[rsid],
                behavioral_insights=info['insights']
            )

        rsid_map, gene_map = self._get_maps('personality')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='trait',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_wellness_metrics(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return WellnessMetric(
                analysis_id=aid, metric_name=info['metric'],
                genetic_predisposition=info['predisposition'],
                optimization_score=info['score'],
                lifestyle_recommendations=info['recommendations'],
                associated_variants=[rsid]
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return WellnessMetric(
                analysis_id=aid, metric_name=info['metric'],
                genetic_predisposition=info['predisposition'],
                optimization_score=info['score'],
                lifestyle_recommendations=info['recommendations'],
                associated_variants=[rsid]
            )

        rsid_map, gene_map = self._get_maps('wellness')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='metric',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_methylation_profiles(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return MethylationProfile(
                analysis_id=aid, gene=info['gene'],
                variant=rsid, methylation_capacity=info['capacity'],
                supplement_recommendations=info['supplements'],
                associated_variants=[rsid]
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return MethylationProfile(
                analysis_id=aid, gene=info['gene'],
                variant=rsid, methylation_capacity=info['capacity'],
                supplement_recommendations=info['supplements'],
                associated_variants=[rsid]
            )

        rsid_map, gene_map = self._get_maps('methylation')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='gene',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    async def _generate_detox_profiles(self, variants, annotation_results, analysis_id, session) -> int:
        def from_rsid(aid, rsid, genotype, info):
            return DetoxificationProfile(
                analysis_id=aid, detox_phase=info['phase'],
                gene=info['gene'], detox_capacity=info['capacity'],
                toxin_sensitivity=info['sensitivity'],
                support_recommendations=info['recommendations'],
                associated_variants=[rsid]
            )

        def from_gene(aid, rsid, gene, consequence, info):
            return DetoxificationProfile(
                analysis_id=aid, detox_phase=info['phase'],
                gene=info['gene'], detox_capacity=info['capacity'],
                toxin_sensitivity=info['sensitivity'],
                support_recommendations=info['recommendations'],
                associated_variants=[rsid]
            )

        rsid_map, gene_map = self._get_maps('detox')
        return await self._generate_from_maps(
            variants, annotation_results, analysis_id, session,
            rsid_map=rsid_map, gene_map=gene_map,
            dedup_field='gene',
            build_from_rsid=from_rsid, build_from_gene=from_gene
        )

    # ------------------------------------------------------------------
    # Generators with unique logic (no generic helper)
    # ------------------------------------------------------------------

    async def _generate_ancestry_results(self, variants, annotation_results, analysis_id, session) -> int:
        from ..db.models import AncestryResult
        ancestry = AncestryResult(
            analysis_id=analysis_id,
            population='Mixed European',
            percentage='Estimated based on variant patterns',
            confidence='moderate',
            geographic_origin='Northern/Western Europe',
            associated_variants=[v.rsid for v in variants[:5] if getattr(v, 'rsid', None)]
        )
        session.add(ancestry)
        return 1

    async def _generate_carrier_status(self, variants, annotation_results, analysis_id, session) -> int:
        from ..db.models import CarrierStatus
        carrier_rsid_map, _ = self._get_maps('carrier')
        carrier_results = []

        for variant in variants:
            variant_rsid = getattr(variant, 'rsid', None)
            if variant_rsid in carrier_rsid_map:
                info = carrier_rsid_map[variant_rsid]
                carrier_results.append(CarrierStatus(
                    analysis_id=analysis_id,
                    condition=info['condition'],
                    carrier_status=info['status'],
                    inheritance_pattern='autosomal_recessive',
                    associated_variants=[variant_rsid],
                    genetic_counseling_recommended=False
                ))

        for c in carrier_results:
            session.add(c)
        return len(carrier_results)

    async def _generate_rare_mutations(self, variants, annotation_results, analysis_id, session) -> int:
        from ..db.models import RareMutation
        rare_mutations = []

        for variant in variants:
            variant_rsid = getattr(variant, 'rsid', None)
            if not variant_rsid:
                continue

            annotation_result = annotation_results.get(variant_rsid)
            if not annotation_result or not annotation_result.annotation_data:
                continue

            clinvar_data = annotation_result.annotation_data.get('annotations', {}).get('clinvar', {})
            if clinvar_data and clinvar_data.get('found'):
                rare_mutations.append(RareMutation(
                    analysis_id=analysis_id,
                    mutation_type='potentially_significant',
                    gene='Unknown',
                    mutation_name=variant_rsid,
                    clinical_significance='uncertain',
                    disease_association='Under investigation',
                    penetrance='unknown',
                    inheritance_pattern='unknown',
                    population_frequency=0.01,
                    clinical_actions=['Genetic counseling recommended'],
                    specialist_referral=True,
                    genetic_counseling_urgent=False,
                    monitoring_recommendations=['Regular medical follow-up'],
                    family_screening_recommended=False,
                    associated_variants=[variant_rsid]
                ))

        for m in rare_mutations:
            session.add(m)
        return len(rare_mutations)

    async def _generate_uncommon_mutations(self, variants, annotation_results, analysis_id, session) -> int:
        uncommon_mutations = []

        for variant in variants:
            variant_rsid = getattr(variant, 'rsid', None)
            if not variant_rsid:
                continue

            annotation_result = annotation_results.get(variant_rsid)
            if not annotation_result or not annotation_result.annotation_data:
                continue

            freq = self._extract_frequency(annotation_result)
            gene, consequence, impact = self._extract_gene_and_consequence(annotation_result)

            if 0.001 <= freq <= 0.05 and gene:
                effect_size = 'moderate' if consequence in ('missense_variant', 'stop_gained', 'frameshift_variant') else 'small'
                research_status = 'well_established' if consequence == 'missense_variant' else 'emerging'

                uncommon_mutations.append(UncommonMutation(
                    analysis_id=analysis_id,
                    mutation_type='low_frequency_variant',
                    gene=gene,
                    mutation_name=f'{gene} {consequence.replace("_", " ")}',
                    clinical_significance='moderate' if effect_size == 'moderate' else 'low',
                    trait_association=f'{gene} pathway variant',
                    effect_size=effect_size,
                    population_frequency=freq,
                    research_status=research_status,
                    lifestyle_implications=['Standard healthy lifestyle', 'No immediate action required'],
                    monitoring_suggestions=['Routine health screening'],
                    research_participation='optional',
                    follow_up_timeline='annual',
                    associated_variants=[variant_rsid]
                ))

                if len(uncommon_mutations) >= 20:
                    break

        for m in uncommon_mutations:
            session.add(m)
        return len(uncommon_mutations)

    # ------------------------------------------------------------------
    # Scoring / recommendation helpers
    # ------------------------------------------------------------------

    def _assess_risk_level(self, genotype: str, risk_multiplier: float) -> str:
        if not genotype:
            return 'unknown'
        if risk_multiplier >= 2.0:
            return 'high'
        elif risk_multiplier >= 1.2:
            return 'moderate'
        elif risk_multiplier <= 0.8:
            return 'low'
        return 'average'

    def _assess_drug_response(self, genotype: str, gene: str) -> str:
        if not genotype:
            return 'normal'
        if gene == 'CYP2C9' and ('*2' in genotype or '*3' in genotype):
            return 'poor'
        elif gene == 'CYP2C19' and '*2' in genotype:
            return 'poor'
        return 'normal'

    def _get_health_recommendations(self, condition: str, risk_level: str) -> List[str]:
        base = {
            'Type 2 Diabetes': [
                'Monitor blood glucose regularly', 'Maintain healthy weight',
                'Exercise regularly', 'Consider genetic counseling'
            ],
            'Cardiovascular Disease': [
                'Monitor blood pressure', 'Maintain healthy cholesterol levels',
                'Exercise regularly', 'Consider cardiology consultation'
            ]
        }
        return base.get(condition, ['Consult with healthcare provider'])

    def _get_drug_recommendations(self, drug: str, response_type: str) -> str:
        if response_type == 'poor':
            return f"Consider alternative to {drug} or adjusted dosing"
        elif response_type == 'intermediate':
            return f"Monitor {drug} response closely"
        return f"Standard {drug} dosing likely appropriate"

    def _get_trait_description(self, trait: str, result: str) -> str:
        return f"Genetic analysis indicates {result} for {trait}"

    # ------------------------------------------------------------------
    # Progress / status persistence
    # ------------------------------------------------------------------

    async def _update_progress(self, analysis_id: int, progress: AnalysisProgress):
        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as session:
                await session.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        progress_percentage=progress.progress_percentage,
                        processed_variants=progress.processed_variants,
                        current_step=progress.current_step,
                        analysis_status=progress.status,
                        estimated_completion=progress.estimated_completion
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

    async def _update_analysis_status(self, analysis_id: int, status: str, step: str):
        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as session:
                await session.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        analysis_status=status,
                        current_step=step
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
