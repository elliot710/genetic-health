"""
Genetic analysis service — annotates variants and populates all category tables.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, func

from ..db.models import (
    GeneticAnalysis, AnalysisVariant, SharedVariantAnnotation, VariantAnnotation,
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait, SportsPerformance,
    CognitiveProfile, PersonalityTrait, AncestryResult, CarrierStatus,
    WellnessMetric, MethylationProfile, DetoxificationProfile, RareMutation,
    UncommonMutation, VariantMapping, AnnotationSourceConfig, ClinVarVariant
)
from ..core.exceptions import AnalysisNotFoundException
from ..core.config import settings
from ..core.telemetry import get_tracer
from .job_logs import JobLogCollector
from .shared_annotation_service import SharedVariantAnnotationService
from .insight_generators import ALL_GENERATORS, GeneratorContext

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class AnalysisCancelled(Exception):
    """Raised when an analysis is paused or stopped by the user."""
    pass


@dataclass
class AnalysisProgress:
    """Enhanced progress tracking for comprehensive analysis.

    Progress is split across four phases with time-based weights:
      Phase 1 (gene map):        0% –  2%   (fast)
      Phase 2 (annotation):      2% – 30%   (minutes)
      Phase 3 (BQ enrichment):  30% – 90%   (hours for large datasets)
      Phase 4 (insights):       90% – 100%  (moderate)
    """
    total_variants: int
    processed_variants: int
    annotated_variants: int
    new_annotations: int
    reused_annotations: int
    current_step: str
    status: str
    estimated_completion: Optional[datetime] = None
    phase: int = 1
    phase_progress: float = 0.0  # 0.0 – 1.0 within current phase

    # Phase weights (must sum to 100)
    _PHASE_OFFSETS: ClassVar[Dict[int, int]] = {1: 0, 2: 2, 3: 30, 4: 90}
    _PHASE_WEIGHTS: ClassVar[Dict[int, int]] = {1: 2, 2: 28, 3: 60, 4: 10}

    @property
    def progress_percentage(self) -> int:
        if self.total_variants == 0:
            return 0
        offset = self._PHASE_OFFSETS.get(self.phase, 0)
        weight = self._PHASE_WEIGHTS.get(self.phase, 0)
        return min(99, int(offset + weight * self.phase_progress))


@dataclass
class AnnotationResult:
    """Result of variant annotation with reuse tracking."""
    rsid: str
    was_reused: bool
    annotation_data: Optional[Dict[str, Any]]
    source: str  # 'existing', 'api', 'failed'


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
        self._rsid_gene_map: Dict[str, str] = {}  # rsid -> gene symbol from ClinVar DB

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

    async def _build_rsid_gene_map(self, variants: List[AnalysisVariant]):
        """Bulk-load rsid→gene from ClinVar DB + Ensembl local position-based lookup."""
        from ..db.database import async_session_factory
        gene_map: Dict[str, str] = {}
        rsids = [str(v.rsid) for v in variants if v.rsid]

        # Step 1: ClinVar DB lookup (fast, covers ~6% of variants)
        batch_size = 1000
        for i in range(0, len(rsids), batch_size):
            batch = rsids[i:i + batch_size]
            # Yield between batches so HTTP handlers can run
            if i > 0:
                await asyncio.sleep(0.01)
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ClinVarVariant.rsid, ClinVarVariant.gene)
                    .where(
                        ClinVarVariant.rsid.in_(batch),
                        ClinVarVariant.gene.isnot(None),
                        ClinVarVariant.gene != '',
                        ClinVarVariant.gene != '-',
                    )
                    .distinct(ClinVarVariant.rsid)
                )
                for row in result:
                    gene_map[row.rsid] = row.gene

        clinvar_count = len(gene_map)
        logger.info(f"ClinVar DB gene map: {clinvar_count} of {len(rsids)} rsids")

        # Step 2: Ensembl local position-based lookup for remaining variants
        unmapped = [
            v for v in variants
            if v.rsid and str(v.rsid) not in gene_map and v.chromosome and v.position
        ]
        if unmapped:
            try:
                from .ensembl_local import get_ensembl_local_service
                ensembl_svc = get_ensembl_local_service()
                if await ensembl_svc.ensure_loaded():
                    positions = [
                        (str(v.chromosome), int(v.position), str(v.rsid))
                        for v in unmapped
                    ]
                    ensembl_genes = await ensembl_svc.batch_position_to_gene(positions)
                    gene_map.update(ensembl_genes)
                    logger.info(
                        f"Ensembl local gene map: {len(ensembl_genes)} additional "
                        f"(total {len(gene_map)}/{len(rsids)})"
                    )
            except Exception as e:
                logger.debug(f"Ensembl local gene lookup skipped: {e}")

        self._rsid_gene_map = gene_map
        logger.info(
            f"Built rsid→gene map: {len(gene_map)} of {len(rsids)} rsids "
            f"(ClinVar: {clinvar_count}, Ensembl: {len(gene_map) - clinvar_count})"
        )

    async def _load_enabled_sources(self) -> Optional[List[str]]:
        """Load enabled annotation sources from the database.
        Returns a list of enabled source names, or None if the table
        doesn't exist yet / is empty (meaning use all sources).

        Local sources (alpha_missense, clinvar_local) are always included
        if not explicitly disabled, even if their config row doesn't exist yet."""
        # Local sources that should always be enabled unless explicitly disabled
        LOCAL_SOURCES = {'alpha_missense', 'clinvar_local', 'gnomad', 'thousand_genomes', 'ensembl_vep'}
        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as session:
                result = await session.execute(
                    select(AnnotationSourceConfig.source_name, AnnotationSourceConfig.is_enabled)
                )
                rows = result.all()
            if not rows:
                return None  # No rows → use all sources (table not seeded yet)

            enabled = set()
            explicitly_disabled = set()
            for name, is_enabled in rows:
                if is_enabled:
                    enabled.add(name)
                else:
                    explicitly_disabled.add(name)

            # Add local sources that aren't explicitly disabled
            for src in LOCAL_SOURCES:
                if src not in explicitly_disabled:
                    enabled.add(src)

            names = sorted(enabled)
            logger.info(f"Enabled annotation sources: {names}")
            return names
        except Exception as e:
            logger.warning(f"Could not load annotation source config: {e} — using all sources")
            return None

    async def _check_if_cancelled(self, analysis_id: int):
        """Check if the analysis has been paused, stopped, cancelled, or deleted."""
        from ..db.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticAnalysis.analysis_status).where(GeneticAnalysis.id == analysis_id)
            )
            current_status = result.scalar_one_or_none()
            if current_status in ('paused', 'stopped', 'failed', 'deleted'):
                raise AnalysisCancelled(f"Analysis {analysis_id} was {current_status}")

    # ------------------------------------------------------------------
    # Top-level orchestration
    # ------------------------------------------------------------------

    async def process_analysis(self, analysis_id: int, strategy: str = 'comprehensive') -> Dict[str, Any]:
        """Process genetic analysis with efficient annotation reuse and comprehensive insights.

        Resume-aware: if the analysis was interrupted mid-run, it detects the
        last completed phase via ``current_step`` and skips work that was
        already persisted to the database.
        """
        start_time = time.time()
        log_collector = JobLogCollector.get_instance()
        log_collector.set_active_job(analysis_id)

        from opentelemetry import context as otel_context, trace as otel_trace
        root_span = tracer.start_span(
            "analysis.process",
            attributes={"analysis.id": analysis_id, "analysis.strategy": strategy},
        )
        _ctx_token = otel_context.attach(otel_trace.set_span_in_context(root_span))

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

            # Determine resume point from prior run's current_step
            resume_step = getattr(analysis, 'current_step', None) or 'initializing'
            # Map step names to completed phase numbers
            _completed_phases = {
                'initializing': 0,
                'annotating_variants': 0,   # Phase 2 was in progress (not done)
                'enriching_bigquery': 1,     # Phase 2 done, Phase 3 in progress
                'generating_insights': 2,    # Phases 2+3 done, Phase 4 in progress
                'completed': 4,
            }
            last_completed_phase = _completed_phases.get(resume_step, 0)
            is_resume = last_completed_phase > 0
            if is_resume:
                logger.info(f"Resuming analysis {analysis_id} from step '{resume_step}' "
                            f"(phases 1-{last_completed_phase} already done)")

            logger.info(f"Starting comprehensive analysis for {len(variants)} variants")
            logger.info(f"  Analysis ID: {analysis_id} | Strategy: {strategy} | User: {self.user_id}")
            logger.info(f"  Registry: {len(self._registry)} categories, "
                        f"{sum(len(v.get('rsid', {})) + len(v.get('gene', {})) for v in self._registry.values())} mappings")

            progress = AnalysisProgress(
                total_variants=len(variants),
                processed_variants=0,
                annotated_variants=0,
                new_annotations=0,
                reused_annotations=0,
                current_step="initializing",
                status="processing",
                phase=1,
                phase_progress=0.0,
            )
            await self._update_progress(analysis_id, progress)

            # ── Phase 1: Build gene map (always — cheap, in-memory only) ──
            phase_start = time.time()
            logger.info(f"═══ Phase 1/4: Building gene map ═══")
            all_rsids = [str(v.rsid) for v in variants if v.rsid]
            has_position = sum(1 for v in variants if v.chromosome and v.position)
            logger.info(f"  Input: {len(all_rsids)} RSIDs, {has_position} with chr:pos")
            with tracer.start_as_current_span("analysis.phase1.build_gene_map") as span:
                span.set_attribute("variant.count", len(variants))
                await self._build_rsid_gene_map(variants)
                span.set_attribute("rsid.count", len(all_rsids))
            unmapped = len(all_rsids) - len(self._rsid_gene_map)
            logger.info(f"═══ Phase 1/4 complete ({time.time() - phase_start:.1f}s) ═══")
            logger.info(f"  Gene map coverage: {len(self._rsid_gene_map)}/{len(all_rsids)} "
                        f"({100 * len(self._rsid_gene_map) / max(1, len(all_rsids)):.1f}%) | "
                        f"{unmapped} unmapped")
            progress.phase = 1
            progress.phase_progress = 1.0

            # ── Phase 2: Annotate variants ──
            # Even on resume we re-load existing annotations from DB.  When
            # Phase 2 was already completed the bulk of variants will be found
            # in shared_variant_annotations and reused instantly.
            from ..db.database import async_session_factory

            progress.phase = 2
            progress.phase_progress = 0.0
            progress.current_step = "annotating_variants"
            await self._update_progress(analysis_id, progress)
            logger.info(f"═══ Phase 2/4: Annotating variants ═══")
            phase_start = time.time()

            with tracer.start_as_current_span("analysis.phase2.annotate_variants") as span:
                span.set_attribute("variant.count", len(variants))
                annotation_service = SharedVariantAnnotationService()
                annotation_results = await self._annotate_variants_efficiently(
                    variants, analysis_id, annotation_service, progress
                )
                span.set_attribute("annotation.reused", progress.reused_annotations)
                span.set_attribute("annotation.new", progress.new_annotations)
            progress.phase_progress = 1.0
            phase_elapsed = time.time() - phase_start
            total_annotated = progress.reused_annotations + progress.new_annotations
            logger.info(f"═══ Phase 2/4 complete ({phase_elapsed:.1f}s) ═══")
            logger.info(f"  Reused: {progress.reused_annotations} | New: {progress.new_annotations} | "
                        f"Total annotated: {total_annotated}/{len(variants)} "
                        f"({100 * total_annotated / max(1, len(variants)):.1f}%)")
            if phase_elapsed > 0:
                logger.info(f"  Throughput: {total_annotated / phase_elapsed:.0f} variants/sec")

            # ── Phase 3: BigQuery enrichment (own session, periodic commits) ──
            progress.phase = 3
            progress.phase_progress = 0.0
            progress.current_step = "enriching_bigquery"
            await self._update_progress(analysis_id, progress)
            logger.info(f"═══ Phase 3/4: BigQuery enrichment ═══")
            logger.info(f"  Input: {len(annotation_results)} annotated variants | "
                        f"{len(set(self._rsid_gene_map.values()))} unique genes in map")
            phase_start = time.time()
            with tracer.start_as_current_span("analysis.phase3.bigquery_enrichment") as span:
                span.set_attribute("annotation.count", len(annotation_results))
                await self._bulk_enrich_bigquery(annotation_results, analysis_id, progress)
            phase_elapsed = time.time() - phase_start
            progress.phase_progress = 1.0
            logger.info(f"═══ Phase 3/4 complete ({phase_elapsed:.1f}s) ═══")

            # ── Phase 4: Generate insights (own session, committed at end) ──
            progress.phase = 4
            progress.phase_progress = 0.0
            progress.current_step = "generating_insights"
            await self._update_progress(analysis_id, progress)
            # Count how many annotations have real data for context
            annotated_with_data = sum(1 for ar in annotation_results.values()
                                      if ar.annotation_data and ar.annotation_data.get('annotations'))
            logger.info(f"═══ Phase 4/4: Generating insights ═══")
            logger.info(f"  Input: {annotated_with_data}/{len(annotation_results)} variants with annotation data")
            logger.info(f"  Generators: {len(ALL_GENERATORS)} — "
                        f"{', '.join(name for name, _ in ALL_GENERATORS)}")
            phase_start = time.time()

            with tracer.start_as_current_span("analysis.phase4.generate_insights") as span:
                async with async_session_factory() as session:
                    insights_generated = await self._generate_comprehensive_insights(
                        variants, annotation_results, analysis_id, session, progress
                    )
                    await session.commit()
                span.set_attribute("insights.generated", insights_generated)
            phase_elapsed = time.time() - phase_start
            logger.info(f"═══ Phase 4/4 complete ({phase_elapsed:.1f}s) ═══")
            logger.info(f"  Total insights: {insights_generated} | "
                        f"Rate: {insights_generated / max(0.1, phase_elapsed):.0f} insights/sec")

            progress.current_step = "completed"
            progress.status = "completed"
            progress.processed_variants = len(variants)
            progress.phase = 4
            progress.phase_progress = 1.0
            await self._update_progress(analysis_id, progress, force_percentage=100)

            # Invalidate dashboard cache so next load picks up new results
            try:
                from ..db.models import DashboardCache
                async with async_session_factory() as inv_session:
                    await inv_session.execute(
                        DashboardCache.__table__.delete().where(
                            DashboardCache.user_id == analysis.user_id
                        )
                    )
                    await inv_session.commit()
            except Exception:
                logger.debug("Dashboard cache invalidation skipped (table may not exist yet)")

            processing_time = time.time() - start_time

            root_span.set_attribute("analysis.processing_time_s", round(processing_time, 2))
            root_span.set_attribute("analysis.variants_processed", len(variants))
            root_span.set_attribute("analysis.insights_generated", insights_generated)

            logger.info(f"╔══════════════════════════════════════════╗")
            logger.info(f"║  Analysis {analysis_id} completed in {processing_time:.1f}s")
            logger.info(f"║  Variants: {len(variants)} total, {len(annotation_results)} annotated")
            logger.info(f"║  Annotations: {progress.reused_annotations} reused, {progress.new_annotations} new")
            logger.info(f"║  Gene map: {len(self._rsid_gene_map)} RSIDs → {len(set(self._rsid_gene_map.values()))} genes")
            logger.info(f"║  Insights: {insights_generated} generated")
            logger.info(f"║  Throughput: {len(variants) / max(0.1, processing_time):.0f} variants/sec overall")
            logger.info(f"╚══════════════════════════════════════════╝")

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

        except AnalysisCancelled as e:
            root_span.set_attribute("analysis.cancelled", True)
            logger.info(f"Analysis {analysis_id} was cancelled: {e}")
            # Status already set by user action (paused/stopped) — don't overwrite
            return {
                "success": False,
                "analysis_id": analysis_id,
                "status": "cancelled",
                "error": str(e),
                "processing_time": time.time() - start_time
            }

        except Exception as e:
            root_span.record_exception(e)
            root_span.set_attribute("error", True)
            logger.error(f"Analysis {analysis_id} failed: {str(e)}", exc_info=True)
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
            otel_context.detach(_ctx_token)
            root_span.end()
            # Persist logs to DB before clearing from memory
            try:
                logs = log_collector.get_logs(analysis_id)
                if logs:
                    from ..db.database import async_session_factory
                    async with async_session_factory() as session:
                        await session.execute(
                            update(GeneticAnalysis)
                            .where(GeneticAnalysis.id == analysis_id)
                            .values(job_logs=logs)
                        )
                        await session.commit()
            except Exception as e:
                logger.debug(f"Failed to persist job logs: {e}")
            log_collector.clear_active_job()
            try:
                if self.api_service:
                    await self.api_service.close()
            except Exception:
                pass
            try:
                from .bq_public import get_bq_public_service
                get_bq_public_service().clear_gene_cache(analysis_id)
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
        if len(variants) > len(variants_with_rsid):
            logger.info(f"  Skipped {len(variants) - len(variants_with_rsid)} variants without valid RS ID")

        existing_annotations = await annotation_service.get_existing_annotations(rsids)
        progress.reused_annotations = len(existing_annotations)
        logger.info(f"  Existing annotations in cache: {len(existing_annotations)}/{len(rsids)} "
                    f"({100 * len(existing_annotations) / max(1, len(rsids)):.1f}%)")

        # Backfill local sources (ClinVar Local, AlphaMissense) for existing
        # annotations that were created before those sources were added
        enabled_sources = await self._load_enabled_sources()
        await self._backfill_local_sources(existing_annotations, enabled_sources, variants_with_rsid, analysis_id)

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

        # Determine if any remote APIs would actually be called
        remote_api_names = {'ensembl', 'clinvar', 'clinpgx', 'snpedia'}
        remote_enabled = remote_api_names & set(enabled_sources or [])

        # If the only remote API is 'ensembl' (we have local ensembl data) or none,
        # use bulk local annotation — 100x+ faster than per-variant HTTP calls
        use_bulk_local = not remote_enabled or remote_enabled <= {'ensembl'}
        if variants_needing_annotation:
            logger.info(f"  Annotation path: {'bulk local' if use_bulk_local else 'remote API'} "
                        f"| Remote APIs enabled: {sorted(remote_enabled) if remote_enabled else 'none'} "
                        f"| Local sources: {sorted(set(enabled_sources or []) - remote_api_names)}")

        if variants_needing_annotation and use_bulk_local:
            logger.info(f"Using bulk local annotation path (remote APIs: {remote_enabled or 'none'})")
            new_results = await self._bulk_annotate_locally(
                variants_needing_annotation, analysis_id,
                annotation_service, progress, enabled_sources
            )
            annotation_results.update(new_results)

        elif variants_needing_annotation and self.api_service:
            batch_size = settings.api.batch_size

            total_batches = (len(variants_needing_annotation) + batch_size - 1) // batch_size

            for i in range(0, len(variants_needing_annotation), batch_size):
                # Check for cancellation every 3 batches
                batch_num = i // batch_size
                if batch_num % 3 == 0:
                    await self._check_if_cancelled(analysis_id)

                batch = variants_needing_annotation[i:i + batch_size]
                batch_rsids = [str(v.rsid) for v in batch]

                logger.info(f"Fetching annotations for batch {batch_num + 1}/{total_batches}: {len(batch)} variants")

                await asyncio.sleep(0)

                new_annotations = await self.api_service.batch_annotate_variants(
                    batch_rsids, strategy='comprehensive', enabled_sources=enabled_sources
                )

                await asyncio.sleep(0)

                for variant in batch:
                    rsid = str(variant.rsid)
                    annotation_data = new_annotations.get(rsid)

                    if annotation_data:
                        success = await annotation_service.save_annotation(
                            rsid, annotation_data, analysis_id, getattr(variant, 'id'),
                            marker_id=getattr(variant, 'marker_id', None),
                            enabled_sources=enabled_sources,
                            rsid_gene_map=self._rsid_gene_map
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
                progress.phase_progress = progress.processed_variants / max(1, progress.total_variants)
                await self._update_progress(analysis_id, progress)

                if i + batch_size < len(variants_needing_annotation):
                    # Yield generously so FastAPI can serve HTTP requests
                    await asyncio.sleep(0.05)

        logger.info(f"Annotation complete: {progress.reused_annotations} reused, {progress.new_annotations} new")
        return annotation_results

    async def _backfill_local_sources(
        self,
        existing_annotations: Dict[str, Dict[str, Any]],
        enabled_sources: Optional[List[str]],
        variants: List[AnalysisVariant],
        analysis_id: int = 0,
    ):
        """Backfill local sources for existing annotations using a single session."""
        from ..db.database import async_session_factory

        # --- Determine which sources need backfilling ---
        do_clinvar = enabled_sources is None or 'clinvar_local' in enabled_sources
        cv_svc = None
        if do_clinvar:
            from .clinvar_local import get_clinvar_local_service
            cv_svc = get_clinvar_local_service()
            do_clinvar = cv_svc.is_loaded

        do_gnomad = enabled_sources is None or 'gnomad' in enabled_sources
        gnomad_svc = None
        if do_gnomad:
            from .gnomad_local import get_gnomad_service
            gnomad_svc = get_gnomad_service()
            do_gnomad = gnomad_svc.is_loaded

        do_ensembl = enabled_sources is None or 'ensembl' in enabled_sources
        vep_svc = None
        if do_ensembl:
            from .ensembl_vep_local import get_ensembl_vep_service
            vep_svc = get_ensembl_vep_service()
            if not vep_svc.is_loaded:
                logger.info("VEP cache still loading in background, waiting for it to finish...")
                await vep_svc.ensure_loaded()
            do_ensembl = vep_svc.is_loaded

        do_1kg = enabled_sources is None or 'thousand_genomes' in enabled_sources
        tkg_svc = None
        if do_1kg:
            from .thousand_genomes_local import get_thousand_genomes_service
            tkg_svc = get_thousand_genomes_service()
            do_1kg = tkg_svc.is_loaded

        do_am = enabled_sources is None or 'alpha_missense' in enabled_sources
        am_svc = None
        if do_am:
            from ..utils.alpha_missense import get_alpha_missense_service
            am_svc = get_alpha_missense_service()
            do_am = am_svc.available

        # Build missing lists from existing annotations
        missing_cv = [
            rsid for rsid, data in existing_annotations.items()
            if do_clinvar and 'clinvar_local' not in data.get('annotations', {})
        ]
        missing_gnomad = [
            rsid for rsid, data in existing_annotations.items()
            if do_gnomad and 'gnomad' not in data.get('annotations', {})
        ]
        missing_ensembl = [
            rsid for rsid, data in existing_annotations.items()
            if do_ensembl and 'ensembl' not in data.get('annotations', {})
        ]
        missing_1kg = [
            rsid for rsid, data in existing_annotations.items()
            if do_1kg and 'thousand_genomes' not in data.get('annotations', {})
        ]
        missing_am = [
            rsid for rsid, data in existing_annotations.items()
            if do_am and 'alpha_missense' not in data.get('annotations', {})
        ]

        if not missing_cv and not missing_gnomad and not missing_ensembl and not missing_1kg and not missing_am:
            # Skip to BQ backfill check below
            pass
        else:
            import time as _time
            backfill_t0 = _time.monotonic()
            logger.info(
                f"Local source backfill starting — "
                f"ClinVar: {len(missing_cv)}, gnomAD: {len(missing_gnomad)}, "
                f"Ensembl: {len(missing_ensembl)}, 1000G: {len(missing_1kg)}, "
                f"AlphaMissense: {len(missing_am)}"
            )
            # --- Batch lookups (parallel-friendly: each uses its own read session) ---
            cv_results: Dict[str, Optional[Dict]] = {}
            gn_results: Dict[str, Optional[Dict]] = {}
            ens_results: Dict[str, Optional[Dict]] = {}

            # Pre-build rsid→variant map once (used by gnomAD and AlphaMissense)
            rsid_to_variant = {str(v.rsid): v for v in variants if v.rsid}

            if missing_cv:
                logger.info(f"Backfilling ClinVar Local for {len(missing_cv)} existing annotations")
                cv_results = await cv_svc.lookup_batch(missing_cv)
            if missing_gnomad:
                logger.info(f"Backfilling gnomAD for {len(missing_gnomad)} existing annotations")
                # Build position tuples from variants for position-based lookup
                gn_pos_tuples = []
                for rsid in missing_gnomad:
                    v = rsid_to_variant.get(rsid)
                    if v:
                        marker = getattr(v, 'marker', None)
                        if marker and marker.chromosome and marker.position and marker.ref_allele:
                            gn_pos_tuples.append((
                                rsid,
                                marker.chromosome,
                                marker.position,
                                marker.ref_allele,
                                marker.alt_alleles or '',
                            ))
                if gn_pos_tuples:
                    gn_results = await gnomad_svc.lookup_batch_by_position(gn_pos_tuples)
            if missing_ensembl:
                logger.info(f"Backfilling Ensembl VEP for {len(missing_ensembl)} existing annotations")
                ens_results = await vep_svc.lookup_batch(missing_ensembl)

            tkg_results: Dict[str, Optional[Dict]] = {}
            if missing_1kg:
                logger.info(f"Backfilling 1000G for {len(missing_1kg)} existing annotations")
                tkg_results = await tkg_svc.lookup_batch(missing_1kg)

            am_results: Dict[str, Optional[Dict]] = {}
            if missing_am:
                logger.info(f"Backfilling AlphaMissense for {len(missing_am)} existing annotations")
                am_batch = []
                for rsid in missing_am:
                    v = rsid_to_variant.get(rsid)
                    if v:
                        marker = getattr(v, 'marker', None)
                        if marker and marker.chromosome and marker.position and marker.ref_allele and marker.alt_alleles:
                            for alt in str(marker.alt_alleles).split(','):
                                alt = alt.strip()
                                if alt:
                                    am_batch.append({
                                        'rsid': rsid,
                                        'chromosome': str(marker.chromosome),
                                        'position': int(marker.position),
                                        'ref_allele': str(marker.ref_allele),
                                        'alt_allele': alt,
                                    })
                                    break
                if am_batch:
                    am_results = am_svc.lookup_variants_batch(am_batch)

            # --- Batch DB updates using executemany (pipelined via asyncpg) ---
            from sqlalchemy import bindparam
            cv_updated = gn_updated = ens_updated = 0
            logger.info("Local source lookups complete, writing results to DB...")

            # Build update params for each source
            cv_params = []
            for rsid, cv_data in cv_results.items():
                if cv_data and cv_data.get('found'):
                    cv_params.append({'b_rsid': rsid, 'b_data': cv_data})
                    existing_annotations[rsid]['annotations']['clinvar_local'] = cv_data

            gn_params = []
            for rsid, gn_data in gn_results.items():
                if gn_data and gn_data.get('found'):
                    gn_params.append({'b_rsid': rsid, 'b_data': gn_data})
                    existing_annotations[rsid]['annotations']['gnomad'] = gn_data

            ens_params = []
            for rsid, ens_data in ens_results.items():
                if ens_data and ens_data.get('found'):
                    ens_params.append({'b_rsid': rsid, 'b_data': ens_data})
                    existing_annotations[rsid]['annotations']['ensembl'] = ens_data

            tkg_params = []
            for rsid, tkg_data in tkg_results.items():
                if tkg_data and tkg_data.get('found'):
                    tkg_params.append({'b_rsid': rsid, 'b_data': tkg_data})
                    existing_annotations[rsid]['annotations']['thousand_genomes'] = tkg_data

            am_params = []
            for rsid, am_data in am_results.items():
                if am_data and am_data.get('found'):
                    am_params.append({'b_rsid': rsid, 'b_data': am_data})
                    existing_annotations[rsid]['annotations']['alpha_missense'] = am_data

            async with async_session_factory() as session:
                if cv_params:
                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid == bindparam('b_rsid'))
                        .values(clinvar_local_data=bindparam('b_data')),
                        cv_params
                    )
                    cv_updated = len(cv_params)

                if gn_params:
                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid == bindparam('b_rsid'))
                        .values(gnomad_data=bindparam('b_data')),
                        gn_params
                    )
                    gn_updated = len(gn_params)

                if ens_params:
                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid == bindparam('b_rsid'))
                        .values(ensembl_data=bindparam('b_data')),
                        ens_params
                    )
                    ens_updated = len(ens_params)

                tkg_updated = 0
                if tkg_params:
                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid == bindparam('b_rsid'))
                        .values(thousand_genomes_data=bindparam('b_data')),
                        tkg_params
                    )
                    tkg_updated = len(tkg_params)

                am_updated = 0
                if am_params:
                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid == bindparam('b_rsid'))
                        .values(alpha_missense_data=bindparam('b_data')),
                        am_params
                    )
                    am_updated = len(am_params)

                if cv_updated or gn_updated or ens_updated or tkg_updated or am_updated:
                    await session.commit()

            if cv_updated:
                logger.info(f"Backfilled ClinVar Local data for {cv_updated}/{len(missing_cv)} annotations")
            if gn_updated:
                logger.info(f"Backfilled gnomAD data for {gn_updated}/{len(missing_gnomad)} annotations")
            if ens_updated:
                logger.info(f"Backfilled Ensembl VEP data for {ens_updated}/{len(missing_ensembl)} annotations")
            if tkg_updated:
                logger.info(f"Backfilled 1000G data for {tkg_updated}/{len(missing_1kg)} annotations")
            if am_updated:
                logger.info(f"Backfilled AlphaMissense data for {am_updated}/{len(missing_am)} annotations")

            backfill_elapsed = _time.monotonic() - backfill_t0
            logger.info(
                f"Local source backfill complete in {backfill_elapsed:.1f}s — "
                f"DB writes: CV={cv_updated}, gnomAD={gn_updated}, VEP={ens_updated}, "
                f"1KG={tkg_updated}, AM={am_updated}"
            )

        # --- BigQuery backfill (ChEMBL, FDA Drug, AlphaFold) ---
        bq_source_names = {'chembl', 'fda_drug', 'alphafold'}
        enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
        bq_col_map = {'chembl': 'chembl_data', 'fda_drug': 'fda_drug_data', 'alphafold': 'alphafold_data'}
        if enabled_bq:
            # Find annotations missing any enabled BQ source
            missing_bq = {}
            for rsid, data in existing_annotations.items():
                anns = data.get('annotations', {})
                missing_for_rsid = {s for s in enabled_bq if s not in anns}
                if missing_for_rsid:
                    # Need gene symbol from ensembl data
                    ensembl_ann = anns.get('ensembl', {})
                    gene = None
                    if ensembl_ann and ensembl_ann.get('found') and ensembl_ann.get('data'):
                        e_entry = ensembl_ann['data'][0] if isinstance(ensembl_ann['data'], list) else ensembl_ann['data']
                        tcs = e_entry.get('transcript_consequences', [])
                        if tcs:
                            gene = tcs[0].get('gene_symbol')
                    if not gene:
                        cv = anns.get('clinvar_local', {})
                        if cv and cv.get('found'):
                            gene = cv.get('gene_symbol') or cv.get('gene')
                    if gene:
                        missing_bq[rsid] = (gene, missing_for_rsid)

            if missing_bq:
                logger.info(f"Backfilling BigQuery sources for {len(missing_bq)} existing annotations")
                try:
                    from .bq_public import get_bq_public_service
                    bq_svc = get_bq_public_service()
                    bq_updated = 0
                    bq_total = len(missing_bq)
                    bq_start = time.time()
                    commit_interval = 50

                    # Accumulate updates between commits (same pattern as _bulk_enrich_bigquery)
                    pending_updates: List[Tuple[str, Dict]] = []  # (rsid, update_vals)

                    async def _flush_bq_backfill():
                        nonlocal pending_updates
                        if not pending_updates:
                            return
                        async with async_session_factory() as session:
                            for rsid, vals in pending_updates:
                                await session.execute(
                                    update(SharedVariantAnnotation)
                                    .where(SharedVariantAnnotation.rsid == rsid)
                                    .values(**vals)
                                )
                            await session.commit()
                        pending_updates = []

                    for idx, (rsid, (gene, needed)) in enumerate(missing_bq.items(), 1):
                        bq_result = await bq_svc.enrich_variant(gene, needed, analysis_id=analysis_id)
                        update_vals = {}
                        for src, src_data in bq_result.items():
                            if src in bq_col_map and src_data:
                                update_vals[bq_col_map[src]] = src_data
                                existing_annotations[rsid]['annotations'][src] = src_data
                        if update_vals:
                            pending_updates.append((rsid, update_vals))
                            bq_updated += 1

                        if idx % commit_interval == 0:
                            await _flush_bq_backfill()

                        if idx % 100 == 0 or idx == bq_total:
                            elapsed = time.time() - bq_start
                            logger.info(f"  BQ backfill progress: {idx}/{bq_total} ({bq_updated} enriched, {elapsed:.1f}s)")

                        await asyncio.sleep(0)

                    await _flush_bq_backfill()
                    logger.info(f"Backfilled BigQuery data for {bq_updated}/{bq_total} annotations ({time.time() - bq_start:.1f}s)")
                except Exception as e:
                    logger.warning(f"BigQuery backfill failed: {e}")

    async def _bulk_annotate_locally(
        self,
        variants: List[AnalysisVariant],
        analysis_id: int,
        annotation_service: SharedVariantAnnotationService,
        progress: AnalysisProgress,
        enabled_sources: Optional[List[str]],
    ) -> Dict[str, AnnotationResult]:
        """Annotate variants using only local data sources — no HTTP API calls.

        Uses batch SQL (IN-clause) for ClinVar and gnomAD lookups, then bulk-
        upserts shared_variant_annotations and creates variant_annotation links.
        ~100x faster than per-variant remote API annotation.
        """
        from ..db.database import async_session_factory
        from sqlalchemy.dialects.postgresql import insert

        # Deduplicate rsids — multiple analysis_variants can share the same rsid
        rsid_to_variants: Dict[str, List[AnalysisVariant]] = {}
        for v in variants:
            rsid_to_variants.setdefault(str(v.rsid), []).append(v)

        unique_rsids = list(rsid_to_variants.keys())
        total = len(unique_rsids)
        logger.info(f"Bulk local annotation: {total} unique RSIDs ({len(variants)} variants)")
        bulk_start = time.time()

        # --- Step 1: Batch ClinVar local lookups ---
        cv_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'clinvar_local' in enabled_sources:
            from .clinvar_local import get_clinvar_local_service
            cv_svc = get_clinvar_local_service()
            if cv_svc.is_loaded:
                t0 = time.time()
                cv_map = await cv_svc.lookup_batch(unique_rsids)
                cv_found = sum(1 for v in cv_map.values() if v and v.get('found'))
                logger.info(f"  ClinVar local batch: {cv_found}/{total} found ({time.time() - t0:.1f}s)")

        # --- Step 2: Batch gnomAD local lookups (position-based for TSV data) ---
        gn_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'gnomad' in enabled_sources:
            from .gnomad_local import get_gnomad_service
            gnomad_svc = get_gnomad_service()
            if gnomad_svc.is_loaded:
                t0 = time.time()
                # Build position tuples from markers for position-based lookup
                pos_tuples = []
                for rsid in unique_rsids:
                    v = rsid_to_variants[rsid][0]
                    marker = getattr(v, 'marker', None)
                    if marker and marker.chromosome and marker.position and marker.ref_allele:
                        pos_tuples.append((
                            rsid,
                            marker.chromosome,
                            marker.position,
                            marker.ref_allele,
                            marker.alt_alleles or '',
                        ))
                if pos_tuples:
                    gn_map = await gnomad_svc.lookup_batch_by_position(pos_tuples)
                gn_found = sum(1 for v in gn_map.values() if v and v.get('found'))
                logger.info(f"  gnomAD local batch: {gn_found}/{total} found ({time.time() - t0:.1f}s)")

        # --- Step 2.5: Batch Ensembl VEP local lookups ---
        ens_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'ensembl' in enabled_sources:
            from .ensembl_vep_local import get_ensembl_vep_service
            vep_svc = get_ensembl_vep_service()
            if not vep_svc.is_loaded:
                logger.info("VEP cache still loading, waiting for it to finish before annotation...")
                await vep_svc.ensure_loaded()
            if vep_svc.is_loaded:
                t0 = time.time()
                ens_map = await vep_svc.lookup_batch(unique_rsids)
                ens_found = sum(1 for v in ens_map.values() if v and v.get('found'))
                logger.info(f"  Ensembl VEP local batch: {ens_found}/{total} found ({time.time() - t0:.1f}s)")

        # --- Step 2.6: Batch 1000 Genomes local lookups ---
        tkg_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'thousand_genomes' in enabled_sources:
            from .thousand_genomes_local import get_thousand_genomes_service
            tkg_svc = get_thousand_genomes_service()
            if tkg_svc.is_loaded:
                t0 = time.time()
                tkg_map = await tkg_svc.lookup_batch(unique_rsids)
                tkg_found = sum(1 for v in tkg_map.values() if v and v.get('found'))
                logger.info(f"  1000G local batch: {tkg_found}/{total} found ({time.time() - t0:.1f}s)")

        # --- Step 2.7: Batch AlphaMissense local lookups ---
        am_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'alpha_missense' in enabled_sources:
            from ..utils.alpha_missense import get_alpha_missense_service
            am_svc = get_alpha_missense_service()
            if am_svc.available:
                t0 = time.time()
                am_variants = []
                for rsid in unique_rsids:
                    v = rsid_to_variants[rsid][0]
                    marker = getattr(v, 'marker', None)
                    if marker and marker.chromosome and marker.position and marker.ref_allele and marker.alt_alleles:
                        for alt in str(marker.alt_alleles).split(','):
                            alt = alt.strip()
                            if alt:
                                am_variants.append({
                                    'rsid': rsid,
                                    'chromosome': str(marker.chromosome),
                                    'position': int(marker.position),
                                    'ref_allele': str(marker.ref_allele),
                                    'alt_allele': alt,
                                })
                                break  # one alt per rsid is enough
                if am_variants:
                    am_map = am_svc.lookup_variants_batch(am_variants)
                am_found = sum(1 for v in am_map.values() if v and v.get('found'))
                logger.info(f"  AlphaMissense local batch: {am_found}/{total} found ({time.time() - t0:.1f}s)")

        await asyncio.sleep(0)

        # --- Step 3: Bulk upsert shared_variant_annotations + create variant_annotations ---
        annotation_results: Dict[str, AnnotationResult] = {}
        batch_size = 500
        saved_count = 0

        # Pre-import scoring engine once — not per-variant
        from .scoring_engine import get_scoring_engine
        scorer = get_scoring_engine()

        # Pre-compute per-rsid values to avoid dict lookups in inner loop
        def _val(data):
            return data if data and data.get('found') else None

        last_progress_update = time.time()

        for i in range(0, len(unique_rsids), batch_size):
            chunk_rsids = unique_rsids[i:i + batch_size]

            # ── Build batch values ──
            batch_values = []
            for rsid in chunk_rsids:
                cv_val = _val(cv_map.get(rsid))
                gn_val = _val(gn_map.get(rsid))
                ens_val = _val(ens_map.get(rsid))
                tkg_val = _val(tkg_map.get(rsid))
                am_val = _val(am_map.get(rsid))
                first_variant = rsid_to_variants[rsid][0]
                marker_id = getattr(first_variant, 'marker_id', None)

                row = dict(
                    rsid=rsid,
                    clinvar_local_data=cv_val,
                    gnomad_data=gn_val,
                    ensembl_data=ens_val,
                    thousand_genomes_data=tkg_val,
                    alpha_missense_data=am_val,
                    annotation_status='partial',
                    total_api_calls=0,
                    usage_count=1,
                )
                if marker_id is not None:
                    row['marker_id'] = marker_id
                batch_values.append(row)

            async with async_session_factory() as session:
                # ── Multi-value upsert (one statement for the whole chunk) ──
                stmt = insert(SharedVariantAnnotation).values(batch_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['rsid'],
                    set_=dict(
                        usage_count=SharedVariantAnnotation.usage_count + 1,
                        last_updated_at=func.now(),
                        clinvar_local_data=func.coalesce(
                            SharedVariantAnnotation.clinvar_local_data,
                            stmt.excluded.clinvar_local_data,
                        ),
                        gnomad_data=func.coalesce(
                            SharedVariantAnnotation.gnomad_data,
                            stmt.excluded.gnomad_data,
                        ),
                        ensembl_data=func.coalesce(
                            SharedVariantAnnotation.ensembl_data,
                            stmt.excluded.ensembl_data,
                        ),
                        thousand_genomes_data=func.coalesce(
                            SharedVariantAnnotation.thousand_genomes_data,
                            stmt.excluded.thousand_genomes_data,
                        ),
                        alpha_missense_data=func.coalesce(
                            SharedVariantAnnotation.alpha_missense_data,
                            stmt.excluded.alpha_missense_data,
                        ),
                    ),
                ).returning(SharedVariantAnnotation.id, SharedVariantAnnotation.rsid)

                result = await session.execute(stmt)
                rsid_to_shared_id = {row.rsid: row.id for row in result.all()}

                # ── Batch insert variant_annotation links ──
                link_values = []
                for rsid in chunk_rsids:
                    shared_id = rsid_to_shared_id.get(rsid)
                    if shared_id is None:
                        continue
                    for v in rsid_to_variants[rsid]:
                        link_values.append(dict(
                            analysis_id=analysis_id,
                            analysis_variant_id=getattr(v, 'id'),
                            shared_annotation_id=shared_id,
                            rsid=rsid,
                        ))
                if link_values:
                    link_stmt = insert(VariantAnnotation).values(link_values)
                    link_stmt = link_stmt.on_conflict_do_nothing(
                        constraint='uq_variant_annotations_analysis_variant'
                    )
                    await session.execute(link_stmt)

                await session.commit()

            # ── Build in-memory annotation results (no DB, pure CPU) ──
            for rsid in chunk_rsids:
                cv_val = _val(cv_map.get(rsid))
                gn_val = _val(gn_map.get(rsid))
                ens_val = _val(ens_map.get(rsid))
                tkg_val = _val(tkg_map.get(rsid))
                am_val = _val(am_map.get(rsid))

                ann_data: Dict[str, Any] = {
                    'rsid': rsid,
                    'annotations': {},
                    'sources_queried': [],
                    'success_count': 0,
                }
                if cv_val:
                    ann_data['annotations']['clinvar_local'] = cv_val
                    ann_data['success_count'] += 1
                if gn_val:
                    ann_data['annotations']['gnomad'] = gn_val
                    ann_data['success_count'] += 1
                if ens_val:
                    ann_data['annotations']['ensembl'] = ens_val
                    ann_data['success_count'] += 1
                if tkg_val:
                    ann_data['annotations']['thousand_genomes'] = tkg_val
                    ann_data['success_count'] += 1
                if am_val:
                    ann_data['annotations']['alpha_missense'] = am_val
                    ann_data['success_count'] += 1

                ann_data['pathogenicity_score'] = scorer.score_variant(
                    ann_data['annotations']
                )

                annotation_results[rsid] = AnnotationResult(
                    rsid=rsid, was_reused=False,
                    annotation_data=ann_data, source='local'
                )
                saved_count += 1

            # Progress — throttle DB updates to every 2s to reduce connection churn
            progress.annotated_variants += sum(
                len(rsid_to_variants[r]) for r in chunk_rsids
            )
            progress.new_annotations += len(chunk_rsids)
            progress.processed_variants = progress.annotated_variants
            progress.phase_progress = progress.processed_variants / max(1, progress.total_variants)

            now = time.time()
            chunk_num = i // batch_size + 1
            total_chunks = (total + batch_size - 1) // batch_size
            if now - last_progress_update >= 2.0 or chunk_num == total_chunks:
                await self._update_progress(analysis_id, progress)
                last_progress_update = now

            if chunk_num % 20 == 0 or chunk_num == total_chunks:
                elapsed = time.time() - bulk_start
                logger.info(
                    f"  Bulk annotation: {saved_count}/{total} RSIDs "
                    f"({progress.annotated_variants} variants, {elapsed:.1f}s)"
                )

            # Yield generously so FastAPI can serve HTTP requests during heavy analysis
            await asyncio.sleep(0.01)

        elapsed = time.time() - bulk_start
        logger.info(f"Bulk local annotation complete: {saved_count} RSIDs in {elapsed:.1f}s")
        return annotation_results

    async def _bulk_enrich_bigquery(
        self,
        annotation_results: Dict[str, AnnotationResult],
        analysis_id: int,
        progress: Optional[AnalysisProgress] = None,
    ):
        """Bulk-enrich annotations with BigQuery data (ChEMBL, FDA Drug, AlphaFold).

        Groups variants by gene, queries BQ once per unique gene, then
        bulk-updates shared_variant_annotations and annotation_results in memory.

        Uses its own session and commits every 50 genes so progress is
        persisted incrementally.  On resume, genes whose BQ columns are
        already populated in the DB are skipped.
        """
        enabled_sources = await self._load_enabled_sources()
        bq_source_names = {'chembl', 'fda_drug', 'alphafold'}
        enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
        if not enabled_bq:
            return

        bq_col_map = {'chembl': 'chembl_data', 'fda_drug': 'fda_drug_data', 'alphafold': 'alphafold_data'}

        # Build gene → [rsids] mapping from all available sources
        gene_to_rsids: Dict[str, List[str]] = {}
        for rsid, ar in annotation_results.items():
            gene = None
            gene = self._rsid_gene_map.get(rsid)
            if not gene and ar.annotation_data:
                cv = ar.annotation_data.get('annotations', {}).get('clinvar_local', {})
                if cv and cv.get('found'):
                    genes = cv.get('genes', [])
                    gene = genes[0] if genes else None
            if not gene and ar.annotation_data:
                gn = ar.annotation_data.get('annotations', {}).get('gnomad', {})
                if gn and gn.get('found') and gn.get('gene'):
                    gene = gn['gene']
            if gene:
                gene_to_rsids.setdefault(gene, []).append(rsid)

        if not gene_to_rsids:
            logger.info("BigQuery enrichment: no genes found, skipping")
            return

        unique_genes = list(gene_to_rsids.keys())
        total_genes = len(unique_genes)
        logger.info(f"BigQuery enrichment: {total_genes} unique genes covering "
                     f"{sum(len(v) for v in gene_to_rsids.values())} variants")

        # ── Determine which genes are already enriched in the DB ──
        from ..db.database import async_session_factory
        already_enriched: set = set()
        try:
            # Collect all rsids that map to genes
            all_gene_rsids = []
            for rsids_list in gene_to_rsids.values():
                all_gene_rsids.extend(rsids_list)

            async with async_session_factory() as session:
                # Check which rsids already have ALL enabled BQ columns filled
                # Batch to stay under PostgreSQL's 32767 parameter limit
                bq_columns = [getattr(SharedVariantAnnotation, bq_col_map[s]) for s in enabled_bq]
                from sqlalchemy import and_
                filters = [col.isnot(None) for col in bq_columns]

                BATCH_SIZE = 30000
                enriched_rsids: set = set()
                for batch_start in range(0, len(all_gene_rsids), BATCH_SIZE):
                    batch = all_gene_rsids[batch_start:batch_start + BATCH_SIZE]
                    result = await session.execute(
                        select(SharedVariantAnnotation.rsid)
                        .where(
                            SharedVariantAnnotation.rsid.in_(batch),
                            and_(*filters)
                        )
                    )
                    enriched_rsids.update(r[0] for r in result.all())

            # A gene is "already enriched" if ALL its rsids have BQ data
            for gene, rsids_for_gene in gene_to_rsids.items():
                if all(r in enriched_rsids for r in rsids_for_gene):
                    already_enriched.add(gene)

            if already_enriched:
                logger.info(f"BigQuery enrichment: skipping {len(already_enriched)} already-enriched genes")

                # Load existing BQ data into in-memory annotation_results
                async with async_session_factory() as session:
                    for gene in already_enriched:
                        rsids_for_gene = gene_to_rsids[gene]
                        result = await session.execute(
                            select(SharedVariantAnnotation)
                            .where(SharedVariantAnnotation.rsid.in_(rsids_for_gene))
                        )
                        for sa in result.scalars().all():
                            ar = annotation_results.get(sa.rsid)
                            if ar and ar.annotation_data:
                                for src, col in bq_col_map.items():
                                    data = getattr(sa, col, None)
                                    if data:
                                        ar.annotation_data.setdefault('annotations', {})[src] = data
        except Exception as e:
            logger.warning(f"BQ enrichment skip-check failed (will re-enrich all): {e}")

        genes_to_process = [g for g in unique_genes if g not in already_enriched]
        if not genes_to_process:
            logger.info("BigQuery enrichment: all genes already enriched — nothing to do")
            return

        logger.info(f"BigQuery enrichment: processing {len(genes_to_process)}/{total_genes} genes")

        try:
            from .bq_public import get_bq_public_service
            bq_svc = get_bq_public_service()

            enriched_genes = 0
            updated_variants = 0
            commit_interval = 50  # Commit every N genes

            # Accumulate updates between commits instead of holding one session open for hours
            pending_updates: List[Tuple[List[str], Dict]] = []  # (rsids, update_vals)
            pending_mem: List[Tuple[List[str], Dict]] = []  # (rsids, mem_updates)

            async def _flush_pending():
                nonlocal pending_updates, pending_mem
                if not pending_updates:
                    return
                async with async_session_factory() as session:
                    for rsids_list, vals in pending_updates:
                        await session.execute(
                            update(SharedVariantAnnotation)
                            .where(SharedVariantAnnotation.rsid.in_(rsids_list))
                            .values(**vals)
                        )
                    await session.commit()
                for rsids_list, mem_upd in pending_mem:
                    for rsid in rsids_list:
                        ar = annotation_results.get(rsid)
                        if ar and ar.annotation_data:
                            for src, src_data in mem_upd.items():
                                ar.annotation_data.setdefault('annotations', {})[src] = src_data
                pending_updates = []
                pending_mem = []

            try:
                total_to_process = len(genes_to_process)
                for idx, gene in enumerate(genes_to_process, 1):
                    # Check for cancellation and update progress periodically
                    if idx % 20 == 0:
                        await self._check_if_cancelled(analysis_id)
                        if progress:
                            progress.phase_progress = idx / total_to_process
                            await self._update_progress(analysis_id, progress)

                    if idx % 100 == 0 or idx == len(genes_to_process):
                        logger.info(f"BQ enriching gene {idx}/{len(genes_to_process)}: {gene} "
                                    f"({enriched_genes} enriched, {updated_variants} variants updated)")
                    try:
                        bq_result = await asyncio.wait_for(
                            bq_svc.enrich_variant(gene, enabled_bq, analysis_id=analysis_id),
                            timeout=90,
                        )
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        logger.warning(f"BigQuery enrichment timed out for gene {gene}")
                        continue
                    except Exception as e:
                        logger.warning(f"BigQuery enrichment failed for gene {gene}: {e}")
                        continue

                    update_vals = {}
                    mem_updates = {}
                    for src, src_data in bq_result.items():
                        if src in bq_col_map and src_data and src_data.get('found'):
                            update_vals[bq_col_map[src]] = src_data
                            mem_updates[src] = src_data

                    if not update_vals:
                        # Periodic flush even when no data, to persist pending updates
                        if idx % commit_interval == 0 and pending_updates:
                            await _flush_pending()
                            logger.info(f"  BQ commit checkpoint at gene {idx}/{len(genes_to_process)}")
                        await asyncio.sleep(0)
                        continue

                    enriched_genes += 1
                    rsids_for_gene = gene_to_rsids[gene]
                    updated_variants += len(rsids_for_gene)

                    pending_updates.append((rsids_for_gene, update_vals))
                    pending_mem.append((rsids_for_gene, mem_updates))

                    # Periodic flush to persist progress (releases connection between flushes)
                    if idx % commit_interval == 0:
                        await _flush_pending()
                        logger.info(f"  BQ commit checkpoint at gene {idx}/{len(genes_to_process)}")

                    await asyncio.sleep(0.01)

                # Final flush
                await _flush_pending()

            except Exception as inner_e:
                # Try to flush what we have before propagating
                try:
                    await _flush_pending()
                except Exception:
                    pass
                raise inner_e

            logger.info(f"BigQuery enrichment complete: {enriched_genes}/{len(genes_to_process)} genes "
                        f"enriched, {updated_variants} variants updated "
                        f"({len(already_enriched)} skipped as already enriched)")

        except Exception as e:
            logger.warning(f"BigQuery bulk enrichment failed: {e}")

    async def _generate_comprehensive_insights(
        self,
        variants: List[AnalysisVariant],
        annotation_results: Dict[str, AnnotationResult],
        analysis_id: int,
        session: AsyncSession,
        progress: AnalysisProgress
    ) -> int:
        """Generate comprehensive insights for all categories.

        Deletes any existing insights for this analysis first so that
        resume does not produce duplicates.
        """
        # Clean up any partial insights from a previous interrupted run
        insight_tables = [
            HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
            SportsPerformance, CognitiveProfile, PersonalityTrait,
            AncestryResult, CarrierStatus, WellnessMetric,
            MethylationProfile, DetoxificationProfile, RareMutation,
            UncommonMutation,
        ]
        from sqlalchemy import delete
        for tbl in insight_tables:
            await session.execute(
                delete(tbl).where(tbl.analysis_id == analysis_id)
            )
        await session.flush()
        logger.info(f"  Cleared {len(insight_tables)} insight tables for fresh generation")

        # Build the shared context for all generators
        ctx = GeneratorContext(
            analysis_id=analysis_id,
            variants=variants,
            annotation_results=annotation_results,
            session=session,
            rsid_gene_map=self._rsid_gene_map,
            registry=self._registry,
        )

        insights_generated = 0
        total_generators = len(ALL_GENERATORS)

        for gen_idx, (gen_name, gen_func) in enumerate(ALL_GENERATORS):
            await self._check_if_cancelled(analysis_id)
            try:
                progress.current_step = f"generating_{gen_name}"
                progress.phase_progress = gen_idx / total_generators
                await self._update_progress(analysis_id, progress)

                count = await gen_func(ctx)
                insights_generated += count
                logger.info(f"  [{gen_idx + 1}/{total_generators}] {gen_name}: {count} insights")
            except AnalysisCancelled:
                raise
            except Exception as e:
                logger.error(f"  [{gen_idx + 1}/{total_generators}] {gen_name}: FAILED — {e}")
                continue

        return insights_generated

    # ------------------------------------------------------------------
    # Category generators (delegated to insight_generators package)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Progress / status persistence
    # ------------------------------------------------------------------

    async def _update_progress(self, analysis_id: int, progress: AnalysisProgress,
                               *, force_percentage: Optional[int] = None):
        try:
            from ..db.database import async_session_factory
            pct = force_percentage if force_percentage is not None else progress.progress_percentage

            async with async_session_factory() as session:
                # Single UPDATE with status guard — no separate SELECT needed
                await session.execute(
                    update(GeneticAnalysis)
                    .where(
                        GeneticAnalysis.id == analysis_id,
                        GeneticAnalysis.analysis_status.notin_(['paused', 'stopped']),
                    )
                    .values(
                        progress_percentage=pct,
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
