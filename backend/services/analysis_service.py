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

    _COMPLETED_PHASES = {
        'initializing': 0,
        'annotating_variants': 0,
        'annotation_complete': 1,
        'enriching_data': 1,
        'generating_insights': 2,
        'completed': 4,
    }

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
                return self._empty_result(analysis_id)

            from ..utils.sex_inferrer import infer_biological_sex
            self._inferred_sex = infer_biological_sex(variants)
            await self._update_db(analysis_id, inferred_sex=self._inferred_sex)

            progress = self._initial_progress(len(variants))
            await self._update_progress(analysis_id, progress)

            await self._run_phase1_gene_map(analysis_id, variants, progress)
            annotation_results = await self._run_phase2_annotations(analysis_id, variants, progress)
            await self._correct_ref_alleles(variants, annotation_results)
            progress.current_step = "annotation_complete"
            await self._update_progress(analysis_id, progress)

            await self._run_phase3_enrichment(analysis_id, annotation_results, progress)
            insights_generated = await self._run_phase4_insights(
                analysis_id, variants, annotation_results, progress,
            )
            await self._finalize_analysis(analysis_id, analysis, variants, progress)

            processing_time = time.time() - start_time
            root_span.set_attribute("analysis.processing_time_s", round(processing_time, 2))
            root_span.set_attribute("analysis.variants_processed", len(variants))
            logger.info(f"Analysis {analysis_id} completed in {processing_time:.1f}s — "
                        f"{len(variants)} variants, {insights_generated} insights")

            return {
                "success": True, "analysis_id": analysis_id, "status": "completed",
                "processed_variants": len(variants), "total_variants": len(variants),
                "reused_annotations": progress.reused_annotations,
                "new_annotations": progress.new_annotations,
                "insights_generated": insights_generated,
                "processing_time": processing_time,
            }

        except AnalysisCancelled as e:
            root_span.set_attribute("analysis.cancelled", True)
            logger.info(f"Analysis {analysis_id} cancelled: {e}")
            return {"success": False, "analysis_id": analysis_id, "status": "cancelled",
                    "error": str(e), "processing_time": time.time() - start_time}

        except Exception as e:
            root_span.record_exception(e)
            logger.error(f"Analysis {analysis_id} failed: {e}", exc_info=True)
            try:
                await self._update_analysis_status(analysis_id, "failed", f"Failed: {str(e)}")
            except Exception:
                pass
            return {"success": False, "analysis_id": analysis_id, "status": "failed",
                    "error": str(e), "processing_time": time.time() - start_time}

        finally:
            otel_context.detach(_ctx_token)
            root_span.end()
            await self._persist_logs_and_cleanup(analysis_id, log_collector)

    def _empty_result(self, analysis_id: int) -> Dict[str, Any]:
        return {"success": True, "analysis_id": analysis_id, "status": "completed",
                "processed_variants": 0, "total_variants": 0, "message": "No variants found"}

    def _initial_progress(self, variant_count: int) -> AnalysisProgress:
        return AnalysisProgress(
            total_variants=variant_count, processed_variants=0,
            annotated_variants=0, new_annotations=0, reused_annotations=0,
            current_step="classifying_variants", status="processing",
            phase=1, phase_progress=0.0,
        )

    async def _run_phase1_gene_map(self, analysis_id: int, variants, progress):
        logger.info(f"Phase 1/4: Building gene map for {len(variants)} variants")
        with tracer.start_as_current_span("analysis.phase1.build_gene_map") as span:
            span.set_attribute("variant.count", len(variants))
            await self._build_rsid_gene_map(variants)
        progress.phase = 1
        progress.phase_progress = 1.0
        logger.info(f"Phase 1/4 complete: {len(self._rsid_gene_map)} genes mapped")

    async def _run_phase2_annotations(self, analysis_id, variants, progress):
        from ..db.database import async_session_factory

        progress.phase = 2
        progress.phase_progress = 0.0
        progress.current_step = "annotating_variants"
        await self._update_progress(analysis_id, progress)
        logger.info("Phase 2/4: Annotating variants")

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
        logger.info(f"Phase 2/4 complete: reused={progress.reused_annotations}, "
                     f"new={progress.new_annotations}")
        return annotation_results

    async def _run_phase3_enrichment(self, analysis_id, annotation_results, progress):
        progress.phase = 3
        progress.phase_progress = 0.0
        progress.current_step = "enriching_data"
        await self._update_progress(analysis_id, progress)
        logger.info("Phase 3/4: BigQuery + Open Targets enrichment")

        with tracer.start_as_current_span("analysis.phase3.bigquery_enrichment"):
            await self._bulk_enrich_bigquery(annotation_results, analysis_id, progress)

        with tracer.start_as_current_span("analysis.phase3.open_targets"):
            await self._bulk_enrich_open_targets(annotation_results)

        new_mappings = await self._enrich_mappings_from_annotations(annotation_results)
        if new_mappings > 0:
            await self._load_registry()
            logger.info(f"Phase 3/4: {new_mappings} new multi-source mappings discovered")

        progress.phase_progress = 1.0

    async def _run_phase4_insights(self, analysis_id, variants, annotation_results, progress):
        progress.phase = 4
        progress.phase_progress = 0.0
        progress.current_step = "generating_insights"
        await self._update_progress(analysis_id, progress)
        logger.info("Phase 4/4: Generating insights")

        with tracer.start_as_current_span("analysis.phase4.generate_insights") as span:
            insights_generated = await self._generate_comprehensive_insights(
                variants, annotation_results, analysis_id, None, progress,
            )
            span.set_attribute("insights.generated", insights_generated)

        logger.info(f"Phase 4/4 complete: {insights_generated} insights generated")
        return insights_generated

    async def _finalize_analysis(self, analysis_id, analysis, variants, progress):
        progress.current_step = "completed"
        progress.status = "completed"
        progress.processed_variants = len(variants)
        progress.phase = 4
        progress.phase_progress = 1.0
        await self._update_progress(analysis_id, progress, force_percentage=100)

        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as inv_session:
                await inv_session.execute(
                    DashboardCache.__table__.delete().where(
                        DashboardCache.user_id == analysis.user_id
                    )
                )
                await inv_session.commit()
        except Exception:
            pass

    async def _persist_logs_and_cleanup(self, analysis_id: int, log_collector):
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
        except Exception:
            pass
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

    async def _bulk_enrich_open_targets(self, annotation_results):
        """Enrich annotations with Open Targets gene-disease associations."""
        from .open_targets_service import get_open_targets_service
        from ..db.database import async_session_factory
        from ..db.models import SharedVariantAnnotation

        ot_service = get_open_targets_service()
        genes_seen: dict = {}
        gene_to_rsids: dict = {}

        for rsid, ar in annotation_results.items():
            gene = self._rsid_gene_map.get(rsid)
            if not gene:
                continue
            existing_ot = ar.annotation_data.get('annotations', {}).get('open_targets')
            if existing_ot and isinstance(existing_ot, dict) and existing_ot.get('found'):
                continue
            gene_to_rsids.setdefault(gene, []).append(rsid)

        unique_genes = list(gene_to_rsids.keys())
        if not unique_genes:
            return

        results = await ot_service.lookup_genes_batch(unique_genes)
        enriched = 0

        async with async_session_factory() as session:
            for gene, ot_data in results.items():
                if not ot_data or not ot_data.get('found'):
                    continue
                for rsid in gene_to_rsids.get(gene, []):
                    ar = annotation_results.get(rsid)
                    if ar and ar.annotation_data:
                        ar.annotation_data.setdefault('annotations', {})['open_targets'] = ot_data
                        enriched += 1

                first_rsid = gene_to_rsids[gene][0] if gene_to_rsids.get(gene) else None
                if first_rsid:
                    from sqlalchemy import update
                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid == first_rsid)
                        .values(open_targets_data=ot_data)
                    )
            if enriched:
                await session.commit()

        logger.info(f"Open Targets enrichment: {enriched} variants across {len(results)} genes")

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
            inferred_sex=getattr(self, '_inferred_sex', None),
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
        pct = force_percentage if force_percentage is not None else progress.progress_percentage
        await self._update_db(
            analysis_id,
            progress_percentage=pct,
            processed_variants=progress.processed_variants,
            current_step=progress.current_step,
            analysis_status=progress.status,
            estimated_completion=progress.estimated_completion,
            guard_paused=True,
        )

    async def _update_analysis_status(self, analysis_id: int, status: str, step: str):
        await self._update_db(analysis_id, analysis_status=status, current_step=step)

    async def _update_db(self, analysis_id: int, *, guard_paused: bool = False, **values):
        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as session:
                q = update(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
                if guard_paused:
                    q = q.where(GeneticAnalysis.analysis_status.notin_(['paused', 'stopped']))
                await session.execute(q.values(**values))
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update analysis {analysis_id}: {e}")
