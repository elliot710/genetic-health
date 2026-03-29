"""
Genetic analysis service — orchestrates annotation and insight generation.

Delegates to extracted modules:
- variant_loader: data loading, gene map, ref allele correction
- annotation_coordinator: annotation reuse, local/remote annotation, BQ enrichment
- insight_dispatcher: insight generation, regeneration
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from ..db.models import (
    GeneticAnalysis, VariantMapping, DashboardCache,
)
from ..core.exceptions import AnalysisNotFoundException
from ..core.config import settings
from ..core.telemetry import get_tracer
from .job_logs import JobLogCollector
from .shared_annotation_service import SharedVariantAnnotationService

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


@dataclass
class _MarkerLite:
    """Lightweight marker proxy — avoids SQLAlchemy ORM overhead for 600k+ variants."""
    id: int
    rsid: Optional[str]
    chromosome: Optional[str]
    position: Optional[int]
    ref_allele: Optional[str]
    alt_alleles: Optional[str]
    gene_symbol: Optional[str] = None  # Cached gene symbol (PERF-04)


@dataclass
class VariantLite:
    """Lightweight variant with the same public interface as AnalysisVariant.

    Using Core SQL rows + dataclasses instead of ORM objects avoids the
    60-90 second event-loop stall caused by SQLAlchemy materialising
    600k+ ORM instances after selectinload returns.
    """
    id: int
    analysis_id: int
    marker_id: int
    genotype: Optional[str]
    quality: Optional[str]
    filter_status: Optional[str]
    info: Optional[dict]
    marker: '_MarkerLite'

    # Proxy properties to match AnalysisVariant interface
    @property
    def rsid(self): return self.marker.rsid

    @property
    def chromosome(self): return self.marker.chromosome

    @property
    def position(self): return self.marker.position

    @property
    def ref_allele(self): return self.marker.ref_allele

    @property
    def alt_allele(self): return self.marker.alt_alleles


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
                select(VariantMapping).where(VariantMapping.is_active)
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

    async def _build_rsid_gene_map(self, variants):
        """Delegate to variant_loader."""
        from .variant_loader import build_rsid_gene_map
        self._rsid_gene_map = await build_rsid_gene_map(variants)

    async def _load_enabled_sources(self) -> Optional[List[str]]:
        """Delegate to variant_loader."""
        from .variant_loader import load_enabled_sources
        return await load_enabled_sources()

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
            # Map step names to completed phase numbers.
            # 'annotating_variants' means Phase 2 was in progress when the
            # worker stopped — we can't know how far it got, so restart Phase 2.
            # 'annotation_complete' is written after Phase 2 fully finishes so
            # a crash between Phase 2 completion and Phase 3 start is safe to
            # resume from Phase 3 without re-annotating.
            _completed_phases = {
                'initializing': 0,
                'annotating_variants': 0,   # Phase 2 was in progress — restart it
                'annotation_complete': 1,   # Phase 2 finished — skip to Phase 3
                'enriching_data': 1,        # Phase 3 in progress (Phase 2 done)
                'generating_insights': 2,   # Phases 2+3 done, Phase 4 in progress
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
                current_step="classifying_variants",
                status="processing",
                phase=1,
                phase_progress=0.0,
            )
            await self._update_progress(analysis_id, progress)

            # ── Phase 1: Build gene map (always — cheap, in-memory only) ──
            phase_start = time.time()
            logger.info("═══ Phase 1/4: Building gene map ═══")
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
            logger.info("═══ Phase 2/4: Annotating variants ═══")
            phase_start = time.time()

            with tracer.start_as_current_span("analysis.phase2.annotate_variants") as span:
                span.set_attribute("variant.count", len(variants))
                annotation_service = SharedVariantAnnotationService()
                annotation_results = await self._annotate_variants_efficiently(
                    variants, analysis_id, annotation_service, progress,
                    update_progress_fn=self._update_progress,
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

            # ── Phase 2.5: Correct ref_allele from authoritative sources ──
            # Consumer CSV uploads naively use genotype[0] as ref_allele.
            # Now that we have ClinVar/gnomAD/Ensembl data, correct the
            # genetic_markers.ref_allele column with the true reference.
            await self._correct_ref_alleles(variants, annotation_results)

            # Mark Phase 2 as fully complete so a crash between here and Phase 3
            # won't cause a full re-annotation on resume.
            progress.current_step = "annotation_complete"
            await self._update_progress(analysis_id, progress)

            # ── Phase 3: BigQuery enrichment (own session, periodic commits) ──
            progress.phase = 3
            progress.phase_progress = 0.0
            progress.current_step = "enriching_data"
            await self._update_progress(analysis_id, progress)
            logger.info("═══ Phase 3/4: BigQuery enrichment ═══")
            enabled_sources = await self._load_enabled_sources()
            bq_source_names = {'chembl', 'fda_drug', 'alphafold'}
            enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
            logger.info(f"  Input: {len(annotation_results)} annotated variants | "
                        f"{len(set(self._rsid_gene_map.values()))} unique genes in map")
            logger.info(f"  BigQuery sources: {sorted(enabled_bq) if enabled_bq else 'none enabled'}")
            phase_start = time.time()
            with tracer.start_as_current_span("analysis.phase3.bigquery_enrichment") as span:
                span.set_attribute("annotation.count", len(annotation_results))
                await self._bulk_enrich_bigquery(annotation_results, analysis_id, progress)
            phase_elapsed = time.time() - phase_start
            progress.phase_progress = 1.0
            logger.info(f"═══ Phase 3/4 complete ({phase_elapsed:.1f}s) ═══")

            # ── Phase 3.5: Multi-source mapping enrichment ──────────
            # Cross-reference annotated variants against multi-source
            # categorizer to discover new mappings from user's data.
            ms_start = time.time()
            new_mappings = await self._enrich_mappings_from_annotations(
                annotation_results
            )
            if new_mappings > 0:
                # Reload registry to include newly created mappings
                await self._load_registry()
                logger.info(f"  Multi-source enrichment: {new_mappings} new mappings "
                            f"({time.time() - ms_start:.1f}s), registry reloaded")

            # ── Phase 4: Generate insights (own session, committed at end) ──
            progress.phase = 4
            progress.phase_progress = 0.0
            progress.current_step = "generating_insights"
            await self._update_progress(analysis_id, progress)
            # Count how many annotations have real data for context
            annotated_with_data = sum(1 for ar in annotation_results.values()
                                      if ar.annotation_data and ar.annotation_data.get('annotations'))
            logger.info("═══ Phase 4/4: Generating insights ═══")
            logger.info(f"  Input: {annotated_with_data}/{len(annotation_results)} variants with annotation data")
            phase_start = time.time()

            with tracer.start_as_current_span("analysis.phase4.generate_insights") as span:
                insights_generated = await self._generate_comprehensive_insights(
                    variants, annotation_results, analysis_id, None, progress
                )
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

            logger.info("╔══════════════════════════════════════════╗")
            logger.info(f"║  Analysis {analysis_id} completed in {processing_time:.1f}s")
            logger.info(f"║  Variants: {len(variants)} total, {len(annotation_results)} annotated")
            logger.info(f"║  Annotations: {progress.reused_annotations} reused, {progress.new_annotations} new")
            logger.info(f"║  Gene map: {len(self._rsid_gene_map)} RSIDs → {len(set(self._rsid_gene_map.values()))} genes")
            logger.info(f"║  Insights: {insights_generated} generated")
            logger.info(f"║  Throughput: {len(variants) / max(0.1, processing_time):.0f} variants/sec overall")
            logger.info("╚══════════════════════════════════════════╝")

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

    # ------------------------------------------------------------------
    # Delegated method stubs
    # ------------------------------------------------------------------

    async def _load_analysis_data(self, analysis_id: int) -> tuple:
        """Delegate to variant_loader."""
        from .variant_loader import load_analysis_data
        return await load_analysis_data(analysis_id, self.user_id)

    async def _correct_ref_alleles(self, variants, annotation_results):
        """Delegate to variant_loader."""
        from .variant_loader import correct_ref_alleles
        await correct_ref_alleles(variants, annotation_results)

    async def _annotate_variants_efficiently(
        self, variants, analysis_id, annotation_service, progress,
        update_progress_fn=None,
    ) -> Dict[str, AnnotationResult]:
        """Delegate to annotation_coordinator."""
        from .annotation_coordinator import annotate_variants_efficiently
        return await annotate_variants_efficiently(
            variants, analysis_id, annotation_service, progress,
            api_service=self.api_service,
            enabled_sources=await self._load_enabled_sources(),
            rsid_gene_map=self._rsid_gene_map,
            update_progress_fn=update_progress_fn,
            check_cancelled_fn=self._check_if_cancelled,
        )

    async def _bulk_enrich_bigquery(self, annotation_results, analysis_id, progress):
        """Delegate to annotation_coordinator."""
        from .annotation_coordinator import bulk_enrich_bigquery
        await bulk_enrich_bigquery(
            annotation_results, analysis_id, self._rsid_gene_map, progress,
            enabled_sources=await self._load_enabled_sources(),
            check_cancelled_fn=self._check_if_cancelled,
            update_progress_fn=self._update_progress,
        )

    async def _enrich_mappings_from_annotations(
        self, annotation_results: Dict,
    ) -> int:
        """Create variant mappings from user's annotated variants using multi-source evidence.

        Scans annotation_results (already fetched during Phase 2/3) and runs
        the multi-source categorizer on each. New mappings are created directly,
        so the insight generator in Phase 4 can use them.

        Loads condition hints from clinvar_gene_conditions and ensembl_genes so
        that variants without ClinVar data still get meaningful condition names
        instead of generic "{gene} variant".
        """
        from ..db.database import async_session_factory
        from ..db.models import VariantMapping
        from .multi_source_categorizer import categorize_variant, load_condition_hints
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        new_mappings = 0
        batch_count = 0

        # Pre-load condition hints for all genes in the rsid→gene map
        all_genes = list(set(self._rsid_gene_map.values()))
        condition_hints = await load_condition_hints(all_genes)

        async with async_session_factory() as session:
            for rsid, ar in annotation_results.items():
                if not ar.annotation_data:
                    continue
                annotations = ar.annotation_data.get("annotations", {})
                if not annotations:
                    continue

                # Get gene from rsid→gene map
                gene_hint = self._rsid_gene_map.get(rsid)

                suggestions = categorize_variant(
                    rsid, annotations, gene_hint=gene_hint,
                    condition_hints=condition_hints,
                )
                for s in suggestions:
                    if s.confidence < 0.5:
                        continue
                    stmt = pg_insert(VariantMapping).values(
                        category=s.category,
                        map_type="rsid",
                        key=rsid,
                        data=s.data,
                        sources=s.sources,
                        confidence=s.confidence,
                        is_active=True,
                        is_auto_discovered=True,
                    ).on_conflict_do_update(
                        index_elements=["category", "map_type", "key"],
                        set_={
                            "data": s.data,
                            "sources": s.sources,
                            "confidence": s.confidence,
                        },
                        where=VariantMapping.confidence < s.confidence,
                    )
                    try:
                        result = await session.execute(stmt)
                        if result.rowcount > 0:
                            new_mappings += 1
                    except Exception as e:
                        logger.warning("Failed to upsert variant_mapping for %s: %s", rsid, e)

                batch_count += 1
                if batch_count % 5000 == 0:
                    await session.commit()

            await session.commit()

        return new_mappings

    async def _generate_comprehensive_insights(
        self, variants, annotation_results, analysis_id, _unused, progress,
    ) -> int:
        """Delegate to insight_dispatcher."""
        from .insight_dispatcher import generate_comprehensive_insights
        return await generate_comprehensive_insights(
            variants, annotation_results, analysis_id,
            self._rsid_gene_map, self._registry, progress,
            check_cancelled_fn=self._check_if_cancelled,
            update_progress_fn=self._update_progress,
        )

    async def regenerate_insights(self, analysis_id: int) -> Dict[str, Any]:
        """Delegate to insight_dispatcher."""
        from .insight_dispatcher import regenerate_insights
        return await regenerate_insights(analysis_id, self.user_id)

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
