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


@dataclass
class _MarkerLite:
    """Lightweight marker proxy — avoids SQLAlchemy ORM overhead for 600k+ variants."""
    id: int
    rsid: Optional[str]
    chromosome: Optional[str]
    position: Optional[int]
    ref_allele: Optional[str]
    alt_alleles: Optional[str]


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

        Local sources are always included if not explicitly disabled,
        even if their config row doesn't exist yet.

        Note on naming:
        - 'ensembl' controls both the remote Ensembl REST API and the
          local Ensembl VEP service — they share the ensembl_data column.
        - 'ensembl_vep' is treated as an alias for 'ensembl' to avoid
          config confusion (both map to the same annotation path).
        """
        # Local sources that should always be enabled unless explicitly disabled.
        # 'ensembl' here means the local VEP service (ensembl_vep_local.py).
        LOCAL_SOURCES = {'alpha_missense', 'clinvar_local', 'thousand_genomes', 'ensembl'}
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

            # Treat 'ensembl_vep' as alias for 'ensembl'
            if 'ensembl_vep' in enabled:
                enabled.add('ensembl')
            if 'ensembl_vep' in explicitly_disabled and 'ensembl' not in enabled:
                explicitly_disabled.add('ensembl')

            # Add local sources that aren't explicitly disabled
            for src in LOCAL_SOURCES:
                if src not in explicitly_disabled:
                    enabled.add(src)

            # Remove the alias — downstream code only checks 'ensembl'
            enabled.discard('ensembl_vep')

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

            # ── Phase 2.5: Correct ref_allele from authoritative sources ──
            # Consumer CSV uploads naively use genotype[0] as ref_allele.
            # Now that we have ClinVar/gnomAD/Ensembl data, correct the
            # genetic_markers.ref_allele column with the true reference.
            await self._correct_ref_alleles(variants, annotation_results)

            # ── Phase 3: BigQuery enrichment (own session, periodic commits) ──
            progress.phase = 3
            progress.phase_progress = 0.0
            progress.current_step = "enriching_bigquery"
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
            logger.info(f"  Generators: {len(ALL_GENERATORS)} — "
                        f"{', '.join(name for name, _ in ALL_GENERATORS)}")
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

    async def _load_analysis_data(self, analysis_id: int) -> tuple:
        """Load analysis header + variants efficiently using Core SQL rows.

        Avoids ORM selectinload which blocks the event loop for 60-90 seconds
        while SQLAlchemy materialises 600k+ objects.  Instead we stream rows
        from a JOIN query in chunks of 5 000, yielding between chunks so HTTP
        handlers can run during the load.

        Returns (GeneticAnalysis, List[VariantLite]).
        """
        from ..db.database import async_session_factory
        from ..db.models import GeneticMarker

        # --- Load GeneticAnalysis header only (no selectinload) ---
        query = select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
        if self.user_id is not None:
            query = query.where(GeneticAnalysis.user_id == self.user_id)

        async with async_session_factory() as session:
            result = await session.execute(query)
            analysis = result.scalar_one_or_none()

        if not analysis:
            raise AnalysisNotFoundException(
                f"Analysis {analysis_id} not found for user {self.user_id}"
            )

        # --- Stream variants as Core rows to avoid ORM overhead ---
        # Core rows are plain Row namedtuples — ~10x less overhead than
        # full SQLAlchemy ORM instances with _sa_instance_state tracking.
        CHUNK = 5_000
        variants: list = []

        stmt = (
            select(
                AnalysisVariant.id,
                AnalysisVariant.analysis_id,
                AnalysisVariant.marker_id,
                AnalysisVariant.genotype,
                AnalysisVariant.quality,
                AnalysisVariant.filter_status,
                AnalysisVariant.info,
                GeneticMarker.rsid,
                GeneticMarker.chromosome,
                GeneticMarker.position,
                GeneticMarker.ref_allele,
                GeneticMarker.alt_alleles,
            )
            .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
            .where(AnalysisVariant.analysis_id == analysis_id)
            .execution_options(stream_results=True, yield_per=CHUNK)
        )

        async with async_session_factory() as session:
            stream = await session.stream(stmt)
            chunk_num = 0
            async for partition in stream.partitions(CHUNK):
                if chunk_num > 0:
                    await asyncio.sleep(0)
                chunk_num += 1
                for row in partition:
                    marker = _MarkerLite(
                        id=row.marker_id,
                        rsid=row.rsid,
                        chromosome=row.chromosome,
                        position=row.position,
                        ref_allele=row.ref_allele,
                        alt_alleles=row.alt_alleles,
                    )
                    variants.append(VariantLite(
                        id=row.id,
                        analysis_id=row.analysis_id,
                        marker_id=row.marker_id,
                        genotype=row.genotype,
                        quality=row.quality,
                        filter_status=row.filter_status,
                        info=row.info,
                        marker=marker,
                    ))

        return analysis, variants

    async def _correct_ref_alleles(
        self,
        variants: List[AnalysisVariant],
        annotation_results: Dict[str, 'AnnotationResult'],
    ):
        """Correct genetic_markers.ref_allele from authoritative annotation sources.

        Consumer CSV uploads naively treat genotype[0] as the ref allele,
        but this is often wrong.  Now that we have annotations from ClinVar,
        gnomAD, and Ensembl VEP, we can identify the true reference genome
        allele and update the global marker catalog.

        This is critical for correct zygosity classification downstream
        (is_homozygous_reference, zygosity_adjust, carrier status, etc.).
        """
        from ..db.database import async_session_factory

        corrections: Dict[int, str] = {}  # marker_id -> true_ref_allele

        for _idx, variant in enumerate(variants):
            if _idx > 0 and _idx % 1000 == 0:
                await asyncio.sleep(0)
            rsid = getattr(variant, 'rsid', None)
            if not rsid:
                continue

            marker = getattr(variant, 'marker', None)
            if not marker:
                continue

            ar = annotation_results.get(rsid)
            if not ar or not ar.annotation_data:
                continue

            annotations = ar.annotation_data.get('annotations', {})
            true_ref = None

            # 1. gnomAD ref_allele (highest confidence — from VCF)
            gnomad = annotations.get('gnomad', {})
            if gnomad and gnomad.get('found'):
                ref = gnomad.get('ref_allele') or gnomad.get('ref')
                if ref and ref not in ('N', '-', '.', ''):
                    true_ref = ref.strip().upper()

            # 2. Ensembl VEP allele_string (format: "REF/ALT")
            if not true_ref:
                ensembl = annotations.get('ensembl', {})
                if ensembl and ensembl.get('found') and ensembl.get('data'):
                    data_list = ensembl['data']
                    if isinstance(data_list, list) and data_list:
                        allele_str = data_list[0].get('allele_string', '')
                        if '/' in allele_str:
                            ref = allele_str.split('/')[0].strip().upper()
                            if ref and ref not in ('N', '-', '.', ''):
                                true_ref = ref

            # 3. ClinVar local ref_allele
            if not true_ref:
                cv = annotations.get('clinvar_local', {})
                if cv and cv.get('found'):
                    ref = cv.get('ref_allele')
                    if ref and ref not in ('N', '-', '.', ''):
                        true_ref = ref.strip().upper()

            # 4. 1000 Genomes ref_allele
            if not true_ref:
                tkg = annotations.get('thousand_genomes', {})
                if tkg and tkg.get('found'):
                    ref = tkg.get('ref_allele')
                    if ref and ref not in ('N', '-', '.', ''):
                        true_ref = ref.strip().upper()

            if not true_ref:
                continue

            current_ref = getattr(marker, 'ref_allele', '') or ''
            if current_ref.strip().upper() != true_ref:
                corrections[marker.id] = true_ref

        if not corrections:
            logger.info("ref_allele correction: all markers already correct")
            return

        # Batch update genetic_markers
        from ..db.models import GeneticMarker
        from sqlalchemy import bindparam

        update_params = [{'b_id': mid, 'b_ref': ref} for mid, ref in corrections.items()]
        CHUNK = 5000
        total_updated = 0

        for i in range(0, len(update_params), CHUNK):
            chunk = update_params[i:i + CHUNK]
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.execute(
                    GeneticMarker.__table__.update()
                    .where(GeneticMarker.__table__.c.id == bindparam('b_id'))
                    .values(ref_allele=bindparam('b_ref')),
                    chunk
                )
                await session.commit()
            total_updated += len(chunk)

        logger.info(
            f"ref_allele correction: updated {total_updated} markers "
            f"from authoritative sources (gnomAD/Ensembl/ClinVar/1000G)"
        )

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

        for _idx, (rsid, annotation_data) in enumerate(existing_annotations.items()):
            if _idx > 0 and _idx % 1000 == 0:
                await asyncio.sleep(0)
            annotation_results[rsid] = AnnotationResult(
                rsid=rsid, was_reused=True,
                annotation_data=annotation_data, source='existing'
            )

        # Count reused annotations as processed — they are analysed variants
        # even though no new API calls were needed.
        progress.annotated_variants = len(existing_annotations)
        progress.processed_variants = len(existing_annotations)

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
        """Backfill local sources for existing annotations.

        Only backfills columns that are NULL (never annotated) or JSON literal
        null (old bug). Columns with {found: false} are genuine misses and are
        NOT re-queried — the migration 009 resets broken entries to NULL.
        """
        from ..db.database import async_session_factory
        from .local_annotation import (
            load_local_sources, build_rsid_variant_map,
            run_all_lookups, chunked_db_write, NOT_FOUND, COL_MAP,
        )

        sources = await load_local_sources(enabled_sources)
        active = sources.active_names
        if not active:
            logger.info("Local source backfill: no local sources loaded")
            return

        # --- Find annotations with NULL columns (needs lookup) ---
        all_rsids = list(existing_annotations.keys())
        # Map source name → list of rsids needing that source
        missing: Dict[str, List[str]] = {s: [] for s in active}

        from ..db.models import SharedVariantAnnotation as SVA
        from sqlalchemy import or_, cast, String

        def _col_empty(col):
            """True when column is SQL NULL or contains JSON literal null."""
            return or_(col.is_(None), cast(col, String) == 'null')

        BATCH = 5000
        for bi in range(0, len(all_rsids), BATCH):
            chunk = all_rsids[bi:bi + BATCH]
            if bi > 0:
                await asyncio.sleep(0)  # yield between DB query batches
            async with async_session_factory() as sess:
                cols = [SVA.rsid]
                col_labels = []
                for src_name in active:
                    db_col = getattr(SVA, COL_MAP[src_name])
                    label = f'{src_name}_empty'
                    cols.append(_col_empty(db_col).label(label))
                    col_labels.append((src_name, label))

                rows = (await sess.execute(
                    select(*cols).where(SVA.rsid.in_(chunk))
                )).all()

            for row_idx, row in enumerate(rows):
                if row_idx > 0 and row_idx % 500 == 0:
                    await asyncio.sleep(0)
                for src_name, label in col_labels:
                    if getattr(row, label):
                        missing[src_name].append(row.rsid)

        total_missing = sum(len(v) for v in missing.values())
        if total_missing == 0:
            logger.info(
                f"Local source backfill: all {len(all_rsids)} annotations "
                f"already have local data (no backfill needed)"
            )
        else:
            import time as _time
            backfill_t0 = _time.monotonic()
            parts = ', '.join(f"{s}: {len(missing[s])}" for s in active)
            logger.info(f"Local source backfill starting — {parts}")

            rsid_to_variant = build_rsid_variant_map(variants)

            # Pass per-source rsid lists so only sources with missing data are queried
            results = await run_all_lookups(
                sources, [], rsid_to_variant, per_source_rsids=missing,
            )

            # --- Build update params and write to DB ---
            logger.info(f"Lookups done in {_time.monotonic() - backfill_t0:.1f}s, writing to DB...")

            ann_key_map = {
                'clinvar_local': 'clinvar_local',
                'gnomad': 'gnomad',
                'ensembl': 'ensembl',
                'thousand_genomes': 'thousand_genomes',
                'alpha_missense': 'alpha_missense',
                'gnomad_tx': 'gnomad_tx',
            }

            for src_name, src_results in results.items():
                col = COL_MAP[src_name]
                needed_rsids = set(missing.get(src_name, []))
                if not needed_rsids:
                    continue

                params = []
                for rsid, data in src_results.items():
                    if rsid not in needed_rsids:
                        continue
                    if data and data.get('found'):
                        params.append({'b_rsid': rsid, 'b_data': data})
                        ann_key = ann_key_map[src_name]
                        if rsid in existing_annotations:
                            existing_annotations[rsid]['annotations'][ann_key] = data
                    else:
                        params.append({'b_rsid': rsid, 'b_data': NOT_FOUND[src_name]})

                if params:
                    updated = await chunked_db_write(col, params)
                    found = sum(1 for p in params if p['b_data'].get('found'))
                    logger.info(f"  Backfilled {src_name}: {found} found, "
                                f"{len(params) - found} not-found, {updated} written")

            elapsed = _time.monotonic() - backfill_t0
            logger.info(f"Local source backfill complete in {elapsed:.1f}s")

        # --- BigQuery backfill (ChEMBL, FDA Drug, AlphaFold) ---
        bq_source_names = {'chembl', 'fda_drug', 'alphafold'}
        enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
        bq_col_map = {'chembl': 'chembl_data', 'fda_drug': 'fda_drug_data', 'alphafold': 'alphafold_data'}
        if enabled_bq:
            missing_bq = {}
            for rsid, data in existing_annotations.items():
                anns = data.get('annotations', {})
                missing_for_rsid = {s for s in enabled_bq if s not in anns}
                if missing_for_rsid:
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

                    pending_updates: List[Tuple[str, Dict]] = []

                    _sva_t = SharedVariantAnnotation.__table__

                    async def _flush_bq_backfill():
                        nonlocal pending_updates
                        if not pending_updates:
                            return
                        async with async_session_factory() as session:
                            conn = await session.connection()
                            for rsid, vals in pending_updates:
                                await conn.execute(
                                    _sva_t.update()
                                    .where(_sva_t.c.rsid == rsid)
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

        Uses the shared local_annotation module for service loading and batch
        lookups, then bulk-upserts shared_variant_annotations and creates
        variant_annotation links.
        """
        from ..db.database import async_session_factory
        from sqlalchemy.dialects.postgresql import insert
        from .local_annotation import load_local_sources, run_all_lookups

        # Deduplicate rsids
        rsid_to_variants: Dict[str, List[AnalysisVariant]] = {}
        for v in variants:
            rsid_to_variants.setdefault(str(v.rsid), []).append(v)

        unique_rsids = list(rsid_to_variants.keys())
        total = len(unique_rsids)
        logger.info(f"Bulk local annotation: {total} unique RSIDs ({len(variants)} variants)")
        bulk_start = time.time()

        # --- Load services and run lookups via shared module ---
        sources = await load_local_sources(enabled_sources)
        rsid_to_variant = {rsid: vlist[0] for rsid, vlist in rsid_to_variants.items()}
        results = await run_all_lookups(sources, unique_rsids, rsid_to_variant)

        # Unpack into per-source maps for the upsert
        cv_map = results.clinvar
        gn_map = results.gnomad
        ens_map = results.ensembl
        tkg_map = results.thousand_genomes
        am_map = results.alpha_missense
        gtx_map = results.gnomad_tx

        await asyncio.sleep(0)

        # --- Bulk upsert shared_variant_annotations + create variant_annotations ---
        annotation_results: Dict[str, AnnotationResult] = {}
        batch_size = 500
        saved_count = 0

        from .scoring_engine import get_scoring_engine
        scorer = get_scoring_engine()

        def _val(data):
            return data if data and data.get('found') else None

        last_progress_update = time.time()

        for i in range(0, len(unique_rsids), batch_size):
            chunk_rsids = unique_rsids[i:i + batch_size]

            batch_values = []
            for rsid in chunk_rsids:
                cv_val = _val(cv_map.get(rsid))
                gn_val = _val(gn_map.get(rsid))
                ens_val = _val(ens_map.get(rsid))
                tkg_val = _val(tkg_map.get(rsid))
                am_val = _val(am_map.get(rsid))
                gtx_val = _val(gtx_map.get(rsid))
                first_variant = rsid_to_variants[rsid][0]
                marker_id = getattr(first_variant, 'marker_id', None)

                row = dict(
                    rsid=rsid,
                    clinvar_local_data=cv_val,
                    gnomad_data=gn_val,
                    gnomad_tx_data=gtx_val,
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
                        gnomad_tx_data=func.coalesce(
                            SharedVariantAnnotation.gnomad_tx_data,
                            stmt.excluded.gnomad_tx_data,
                        ),
                    ),
                ).returning(SharedVariantAnnotation.id, SharedVariantAnnotation.rsid)

                result = await session.execute(stmt)
                rsid_to_shared_id = {row.rsid: row.id for row in result.all()}

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

            # Build in-memory annotation results with event loop yields
            for idx_in_chunk, rsid in enumerate(chunk_rsids):
                if idx_in_chunk > 0 and idx_in_chunk % 50 == 0:
                    await asyncio.sleep(0)
                cv_val = _val(cv_map.get(rsid))
                gn_val = _val(gn_map.get(rsid))
                ens_val = _val(ens_map.get(rsid))
                tkg_val = _val(tkg_map.get(rsid))
                am_val = _val(am_map.get(rsid))
                gtx_val = _val(gtx_map.get(rsid))

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
                if gtx_val:
                    ann_data['annotations']['gnomad_tx'] = gtx_val
                    ann_data['success_count'] += 1

                ann_data['pathogenicity_score'] = scorer.score_variant(
                    ann_data['annotations']
                )

                annotation_results[rsid] = AnnotationResult(
                    rsid=rsid, was_reused=False,
                    annotation_data=ann_data, source='local'
                )
                saved_count += 1

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

            # Yield generously so FastAPI can serve HTTP requests
            await asyncio.sleep(0.01)

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

                # Load existing BQ data into in-memory annotation_results.
                # Use per-gene short sessions — holding one session across hundreds of
                # gene-level SELECT queries pins a connection for the entire loop.
                for gene in already_enriched:
                    rsids_for_gene = gene_to_rsids[gene]
                    async with async_session_factory() as session:
                        result = await session.execute(
                            select(SharedVariantAnnotation)
                            .where(SharedVariantAnnotation.rsid.in_(rsids_for_gene))
                        )
                        rows = result.scalars().all()
                    for sa in rows:
                        ar = annotation_results.get(sa.rsid)
                        if ar and ar.annotation_data:
                            for src, col in bq_col_map.items():
                                data = getattr(sa, col, None)
                                if data:
                                    ar.annotation_data.setdefault('annotations', {})[src] = data
                    await asyncio.sleep(0)
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

            _sva_tbl = SharedVariantAnnotation.__table__

            async def _flush_pending():
                nonlocal pending_updates, pending_mem
                if not pending_updates:
                    return
                async with async_session_factory() as session:
                    conn = await session.connection()
                    for rsids_list, vals in pending_updates:
                        await conn.execute(
                            _sva_tbl.update()
                            .where(_sva_tbl.c.rsid.in_(rsids_list))
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

        Each generator runs in its own DB session so that a connection
        failure in one generator (e.g. ancestry taking >60 s to query
        1000 Genomes) does not poison subsequent generators via a
        PendingRollbackError cascade.
        """
        from ..db.database import async_session_factory
        from sqlalchemy import delete

        # Clean up any partial insights from a previous interrupted run
        insight_tables = [
            HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
            SportsPerformance, CognitiveProfile, PersonalityTrait,
            AncestryResult, CarrierStatus, WellnessMetric,
            MethylationProfile, DetoxificationProfile, RareMutation,
            UncommonMutation,
        ]
        async with async_session_factory() as cleanup_session:
            for tbl in insight_tables:
                await cleanup_session.execute(
                    delete(tbl).where(tbl.analysis_id == analysis_id)
                )
            await cleanup_session.commit()
        logger.info(f"  Cleared {len(insight_tables)} insight tables for fresh generation")

        insights_generated = 0
        total_generators = len(ALL_GENERATORS)
        failed_generators: list[str] = []

        for gen_idx, (gen_name, gen_func) in enumerate(ALL_GENERATORS):
            await self._check_if_cancelled(analysis_id)
            try:
                progress.current_step = f"generating_{gen_name}"
                progress.phase_progress = gen_idx / total_generators
                await self._update_progress(analysis_id, progress)

                # Fresh session per generator — isolates connection failures
                async with async_session_factory() as gen_session:
                    ctx = GeneratorContext(
                        analysis_id=analysis_id,
                        variants=variants,
                        annotation_results=annotation_results,
                        session=gen_session,
                        rsid_gene_map=self._rsid_gene_map,
                        registry=self._registry,
                    )
                    count = await gen_func(ctx)
                    await gen_session.commit()
                insights_generated += count
                logger.info(f"  [{gen_idx + 1}/{total_generators}] {gen_name}: {count} insights")
            except AnalysisCancelled:
                raise
            except Exception as e:
                failed_generators.append(gen_name)
                logger.error(f"  [{gen_idx + 1}/{total_generators}] {gen_name}: FAILED — {e}")
                continue

        if failed_generators:
            logger.warning(f"  {len(failed_generators)} generator(s) failed: {', '.join(failed_generators)}")

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
