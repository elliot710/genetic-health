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
    CognitiveProfile, PersonalityTrait, AncestryResult, CarrierStatus,
    WellnessMetric, MethylationProfile, DetoxificationProfile, RareMutation,
    UncommonMutation, VariantMapping, AnnotationSourceConfig, ClinVarVariant
)
from ..core.exceptions import AnalysisNotFoundException
from ..core.config import settings
from .job_logs import JobLogCollector
from ..utils.alpha_missense import get_alpha_missense_service, AlphaMissenseService

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

        total_batches = (len(rsids) + batch_size - 1) // batch_size
        logger.info(f"Checking for existing shared annotations for {len(rsids)} RSIDs in {total_batches} batches")
        lookup_start = time.time()

        for i in range(0, len(rsids), batch_size):
            batch_rsids = rsids[i:i + batch_size]
            batch_num = i // batch_size + 1
            if batch_num % 200 == 0 or batch_num == total_batches:
                elapsed = time.time() - lookup_start
                logger.info(f"📊 Annotation lookup batch {batch_num}/{total_batches} ({elapsed:.1f}s elapsed, {len(annotation_map)} found so far)")

            await asyncio.sleep(0)

            result = await self.session.execute(
                select(SharedVariantAnnotation).where(
                    SharedVariantAnnotation.rsid.in_(batch_rsids),
                    SharedVariantAnnotation.annotation_status.in_(['completed', 'partial'])
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

                for source in ('ensembl', 'clinvar', 'clinpgx', 'snpedia', 'litvar'):
                    data = getattr(annotation, f'{source}_data', None)
                    if data is None and source == 'clinpgx':
                        # DB column is still named pharmgkb_data for backward compat
                        data = getattr(annotation, 'pharmgkb_data', None)
                    if data is not None:
                        merged_data['annotations'][source] = data
                        merged_data['sources_queried'].append(source)
                        merged_data['success_count'] += 1

                # Include AlphaMissense data (local, not an API source)
                am_data = getattr(annotation, 'alpha_missense_data', None)
                if am_data is not None:
                    merged_data['annotations']['alpha_missense'] = am_data

                # Include ClinVar Local data (PG-backed, not an API source)
                cv_local = getattr(annotation, 'clinvar_local_data', None)
                if cv_local is not None:
                    merged_data['annotations']['clinvar_local'] = cv_local

                # Include gnomAD data (PG-backed, not an API source)
                gnomad = getattr(annotation, 'gnomad_data', None)
                if gnomad is not None:
                    merged_data['annotations']['gnomad'] = gnomad

                # Include BigQuery data (ChEMBL, FDA Drug, AlphaFold)
                for bq_src, bq_col in (('chembl', 'chembl_data'), ('fda_drug', 'fda_drug_data'), ('alphafold', 'alphafold_data')):
                    bq_data = getattr(annotation, bq_col, None)
                    if bq_data is not None:
                        merged_data['annotations'][bq_src] = bq_data

                # Compute composite pathogenicity score
                from .scoring_engine import get_scoring_engine
                merged_data['pathogenicity_score'] = get_scoring_engine().score_variant(
                    merged_data['annotations']
                )

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
        elapsed = time.time() - lookup_start
        logger.info(f"Found {len(annotation_map)} existing shared annotations for {len(rsids)} requested RSIDs ({elapsed:.1f}s)")
        return annotation_map

    async def save_annotation(
        self,
        rsid: str,
        annotation_data: Dict[str, Any],
        analysis_id: int,
        analysis_variant_id: int,
        marker_id: int = None,
        enabled_sources: Optional[List[str]] = None,
        rsid_gene_map: Optional[Dict[str, str]] = None
    ) -> bool:
        """Save new annotation data to shared system and create user reference."""
        try:
            annotations = annotation_data.get('annotations', {})
            sources_queried = annotation_data.get('sources_queried', ['ensembl', 'clinvar', 'clinpgx', 'snpedia'])
            success_count = annotation_data.get('success_count', 0)

            # Determine which sources failed (queried but threw errors / returned None)
            # A response with found=False means the API confirmed no data exists — that's not a failure
            failed = []
            for src in sources_queried:
                src_data = annotations.get(src)
                if src_data is None:
                    # Source was queried but returned nothing (error/timeout)
                    failed.append(src)
                # found=False with a dict response = confirmed absence, NOT a failure

            total_sources = len(sources_queried)
            if failed:
                status = 'partial' if success_count > 0 else 'failed'
            else:
                status = 'completed'

            # Look up AlphaMissense prediction from local data (comprehensive)
            am_data = None
            if enabled_sources is None or 'alpha_missense' in enabled_sources:
                ensembl_ann = annotations.get('ensembl', {})
            if ensembl_ann and ensembl_ann.get('found') and ensembl_ann.get('data'):
                e_entry = ensembl_ann['data'][0] if isinstance(ensembl_ann['data'], list) else ensembl_ann['data']
                chrom = e_entry.get('seq_region_name')
                pos = e_entry.get('start')
                allele_str = e_entry.get('allele_string', '')
                parts = allele_str.split('/') if allele_str else []
                if chrom and pos and len(parts) == 2:
                    ref, alt = parts[0], parts[1]
                    if len(ref) == 1 and len(alt) == 1:
                        am_svc = get_alpha_missense_service()
                        am_data = am_svc.lookup_comprehensive(str(chrom), int(pos), ref, alt)

            # Look up ClinVar local data (PostgreSQL-backed)
            cv_local_data = None
            if enabled_sources is None or 'clinvar_local' in enabled_sources:
                from .clinvar_local import get_clinvar_local_service
                cv_svc = get_clinvar_local_service()
                if cv_svc.is_loaded:
                    cv_local_data = await cv_svc.lookup(rsid)

            # Look up gnomAD data (PG-only during bulk analysis — no BQ fallback)
            gnomad_data_val = None
            if enabled_sources is None or 'gnomad' in enabled_sources:
                from .gnomad_local import get_gnomad_service
                gnomad_svc = get_gnomad_service()
                if gnomad_svc.is_loaded:
                    gnomad_data_val = await gnomad_svc.lookup(rsid, local_only=True)

            # BigQuery enrichment (ChEMBL, FDA Drug, AlphaFold) is deferred to
            # backfill / on-demand variant-detail to avoid blocking bulk analysis.
            chembl_data_val = None
            fda_drug_data_val = None
            alphafold_data_val = None

            from sqlalchemy.dialects.postgresql import insert
            values = dict(
                rsid=rsid,
                ensembl_data=annotations.get('ensembl'),
                clinvar_data=annotations.get('clinvar'),
                pharmgkb_data=annotations.get('clinpgx'),
                snpedia_data=annotations.get('snpedia'),
                litvar_data=annotations.get('litvar'),
                alpha_missense_data=am_data,
                clinvar_local_data=cv_local_data,
                gnomad_data=gnomad_data_val,
                chembl_data=chembl_data_val,
                fda_drug_data=fda_drug_data_val,
                alphafold_data=alphafold_data_val,
                annotation_status=status,
                failed_sources=failed if failed else None,
                total_api_calls=success_count,
                usage_count=1
            )
            if marker_id is not None:
                values['marker_id'] = marker_id
            stmt = insert(SharedVariantAnnotation).values(**values)
            # Build the conflict-update dict — always bump usage_count and
            # back-fill any columns that were previously NULL.
            conflict_set = dict(
                usage_count=SharedVariantAnnotation.usage_count + 1,
                last_updated_at=func.now(),
                total_api_calls=func.greatest(
                    SharedVariantAnnotation.total_api_calls,
                    stmt.excluded.total_api_calls
                ),
            )
            # Back-fill NULL data columns with new values (coalesce keeps existing)
            for col_name, ann_key in [
                ('ensembl_data', 'ensembl'),
                ('clinvar_data', 'clinvar'),
                ('pharmgkb_data', 'clinpgx'),
                ('snpedia_data', 'snpedia'),
                ('litvar_data', 'litvar'),
            ]:
                val = annotations.get(ann_key)
                if val is not None:
                    col = getattr(SharedVariantAnnotation, col_name)
                    conflict_set[col_name] = func.coalesce(col, stmt.excluded[col_name])
            if am_data:
                conflict_set['alpha_missense_data'] = func.coalesce(
                    SharedVariantAnnotation.alpha_missense_data,
                    stmt.excluded.alpha_missense_data,
                )
            if cv_local_data:
                conflict_set['clinvar_local_data'] = func.coalesce(
                    SharedVariantAnnotation.clinvar_local_data,
                    stmt.excluded.clinvar_local_data,
                )
            if gnomad_data_val:
                conflict_set['gnomad_data'] = func.coalesce(
                    SharedVariantAnnotation.gnomad_data,
                    stmt.excluded.gnomad_data,
                )
            if chembl_data_val:
                conflict_set['chembl_data'] = func.coalesce(
                    SharedVariantAnnotation.chembl_data,
                    stmt.excluded.chembl_data,
                )
            if fda_drug_data_val:
                conflict_set['fda_drug_data'] = func.coalesce(
                    SharedVariantAnnotation.fda_drug_data,
                    stmt.excluded.fda_drug_data,
                )
            if alphafold_data_val:
                conflict_set['alphafold_data'] = func.coalesce(
                    SharedVariantAnnotation.alphafold_data,
                    stmt.excluded.alphafold_data,
                )

            # Recalculate annotation_status & failed_sources after the merge.
            # A source is "failed" only when its column is still NULL after
            # merging old + new data.  found=false is a confirmed absence, not
            # a failure.
            merged_ensembl  = func.coalesce(SharedVariantAnnotation.ensembl_data,  stmt.excluded.ensembl_data)
            merged_clinvar  = func.coalesce(SharedVariantAnnotation.clinvar_data,  stmt.excluded.clinvar_data)
            merged_pharmgkb = func.coalesce(SharedVariantAnnotation.pharmgkb_data, stmt.excluded.pharmgkb_data)
            merged_snpedia  = func.coalesce(SharedVariantAnnotation.snpedia_data,  stmt.excluded.snpedia_data)

            # Status: 'completed' when all 4 core columns are non-NULL
            from sqlalchemy import case, literal, cast, type_coerce
            from sqlalchemy.types import Text
            conflict_set['annotation_status'] = case(
                (
                    (merged_ensembl.isnot(None))
                    & (merged_clinvar.isnot(None))
                    & (merged_pharmgkb.isnot(None))
                    & (merged_snpedia.isnot(None)),
                    literal('completed')
                ),
                else_=literal('partial'),
            )
            # Clear failed_sources when completed
            conflict_set['failed_sources'] = case(
                (
                    (merged_ensembl.isnot(None))
                    & (merged_clinvar.isnot(None))
                    & (merged_pharmgkb.isnot(None))
                    & (merged_snpedia.isnot(None)),
                    None
                ),
                else_=stmt.excluded.failed_sources,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['rsid'],
                set_=conflict_set,
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
        async with async_session_factory() as session:
            for i in range(0, len(rsids), batch_size):
                batch = rsids[i:i + batch_size]
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
        LOCAL_SOURCES = {'alpha_missense', 'clinvar_local', 'gnomad'}
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
        """Process genetic analysis with efficient annotation reuse and comprehensive insights.

        Resume-aware: if the analysis was interrupted mid-run, it detects the
        last completed phase via ``current_step`` and skips work that was
        already persisted to the database.
        """
        start_time = time.time()
        log_collector = JobLogCollector.get_instance()
        log_collector.set_active_job(analysis_id)

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

            # ── Phase 1: Build gene map (always — cheap, in-memory only) ──
            logger.info(f"═══ Phase 1/4: Building gene map ═══")
            all_rsids = [str(v.rsid) for v in variants if v.rsid]
            await self._build_rsid_gene_map(variants)

            # ── Phase 2: Annotate variants ──
            # Even on resume we re-load existing annotations from DB.  When
            # Phase 2 was already completed the bulk of variants will be found
            # in shared_variant_annotations and reused instantly.
            from ..db.database import async_session_factory

            progress.current_step = "annotating_variants"
            await self._update_progress(analysis_id, progress)
            logger.info(f"═══ Phase 2/4: Annotating variants ═══")
            phase_start = time.time()

            async with async_session_factory() as session:
                annotation_service = SharedVariantAnnotationService(session)
                annotation_results = await self._annotate_variants_efficiently(
                    variants, analysis_id, annotation_service, progress
                )
            logger.info(f"═══ Phase 2/4 complete ({time.time() - phase_start:.1f}s) ═══")

            # ── Phase 3: BigQuery enrichment (own session, periodic commits) ──
            progress.current_step = "enriching_bigquery"
            await self._update_progress(analysis_id, progress)
            logger.info(f"═══ Phase 3/4: BigQuery enrichment ═══")
            phase_start = time.time()
            await self._bulk_enrich_bigquery(annotation_results, analysis_id)
            logger.info(f"═══ Phase 3/4 complete ({time.time() - phase_start:.1f}s) ═══")

            # ── Phase 4: Generate insights (own session, committed at end) ──
            progress.current_step = "generating_insights"
            await self._update_progress(analysis_id, progress)
            logger.info(f"═══ Phase 4/4: Generating insights ═══")
            phase_start = time.time()

            async with async_session_factory() as session:
                insights_generated = await self._generate_comprehensive_insights(
                    variants, annotation_results, analysis_id, session, progress
                )
                await session.commit()
            logger.info(f"═══ Phase 4/4 complete ({time.time() - phase_start:.1f}s) ═══")

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

        except AnalysisCancelled as e:
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

        existing_annotations = await annotation_service.get_existing_annotations(rsids)
        progress.reused_annotations = len(existing_annotations)

        # Backfill local sources (ClinVar Local, AlphaMissense) for existing
        # annotations that were created before those sources were added
        enabled_sources = await self._load_enabled_sources()
        await self._backfill_local_sources(existing_annotations, enabled_sources, variants_with_rsid)

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
    ):
        """Backfill ClinVar Local (and AlphaMissense) data for existing annotations
        that were created before those local sources were added."""
        from ..db.database import async_session_factory

        # --- ClinVar Local backfill ---
        do_clinvar = enabled_sources is None or 'clinvar_local' in enabled_sources
        if do_clinvar:
            from .clinvar_local import get_clinvar_local_service
            cv_svc = get_clinvar_local_service()
            do_clinvar = cv_svc.is_loaded

        missing_cv = []
        if do_clinvar:
            missing_cv = [
                rsid for rsid, data in existing_annotations.items()
                if 'clinvar_local' not in data.get('annotations', {})
            ]

        # --- gnomAD backfill ---
        do_gnomad = enabled_sources is None or 'gnomad' in enabled_sources
        gnomad_svc = None
        if do_gnomad:
            from .gnomad_local import get_gnomad_service
            gnomad_svc = get_gnomad_service()
            do_gnomad = gnomad_svc.is_loaded

        missing_gnomad = []
        if do_gnomad:
            missing_gnomad = [
                rsid for rsid, data in existing_annotations.items()
                if 'gnomad' not in data.get('annotations', {})
            ]

        if not missing_cv and not missing_gnomad:
            return

        # ClinVar Local backfill
        cv_updated = 0
        if missing_cv:
            logger.info(f"Backfilling ClinVar Local for {len(missing_cv)} existing annotations")
            cv_results = await cv_svc.lookup_batch(missing_cv)
            async with async_session_factory() as session:
                for rsid, cv_data in cv_results.items():
                    if cv_data and cv_data.get('found'):
                        await session.execute(
                            update(SharedVariantAnnotation)
                            .where(SharedVariantAnnotation.rsid == rsid)
                            .values(clinvar_local_data=cv_data)
                        )
                        existing_annotations[rsid]['annotations']['clinvar_local'] = cv_data
                        cv_updated += 1
                if cv_updated:
                    await session.commit()
            logger.info(f"Backfilled ClinVar Local data for {cv_updated}/{len(missing_cv)} annotations")

        # gnomAD backfill (local only — no BigQuery fallback)
        gnomad_updated = 0
        if missing_gnomad and gnomad_svc:
            logger.info(f"Backfilling gnomAD for {len(missing_gnomad)} existing annotations (local only)")
            batch_results = await gnomad_svc.lookup_batch(missing_gnomad)
            async with async_session_factory() as session:
                for rsid, gn_data in batch_results.items():
                    if gn_data and gn_data.get('found'):
                        await session.execute(
                            update(SharedVariantAnnotation)
                            .where(SharedVariantAnnotation.rsid == rsid)
                            .values(gnomad_data=gn_data)
                        )
                        existing_annotations[rsid]['annotations']['gnomad'] = gn_data
                        gnomad_updated += 1
                if gnomad_updated:
                    await session.commit()
            logger.info(f"Backfilled gnomAD data for {gnomad_updated}/{len(missing_gnomad)} annotations")

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
                    async with async_session_factory() as session:
                        for idx, (rsid, (gene, needed)) in enumerate(missing_bq.items(), 1):
                            bq_result = await bq_svc.enrich_variant(gene, needed, analysis_id=analysis_id)
                            update_vals = {}
                            for src, src_data in bq_result.items():
                                if src in bq_col_map and src_data:
                                    update_vals[bq_col_map[src]] = src_data
                                    existing_annotations[rsid]['annotations'][src] = src_data
                            if update_vals:
                                await session.execute(
                                    update(SharedVariantAnnotation)
                                    .where(SharedVariantAnnotation.rsid == rsid)
                                    .values(**update_vals)
                                )
                                bq_updated += 1
                            if idx % 100 == 0 or idx == bq_total:
                                elapsed = time.time() - bq_start
                                logger.info(f"  BQ backfill progress: {idx}/{bq_total} ({bq_updated} enriched, {elapsed:.1f}s)")
                        if bq_updated:
                            await session.commit()
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

        # --- Step 2: Batch gnomAD local lookups ---
        gn_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'gnomad' in enabled_sources:
            from .gnomad_local import get_gnomad_service
            gnomad_svc = get_gnomad_service()
            if gnomad_svc.is_loaded:
                t0 = time.time()
                gn_map = await gnomad_svc.lookup_batch(unique_rsids)
                gn_found = sum(1 for v in gn_map.values() if v and v.get('found'))
                logger.info(f"  gnomAD local batch: {gn_found}/{total} found ({time.time() - t0:.1f}s)")

        await asyncio.sleep(0)

        # --- Step 3: Bulk upsert shared_variant_annotations + create variant_annotations ---
        annotation_results: Dict[str, AnnotationResult] = {}
        batch_size = 500
        saved_count = 0

        for i in range(0, len(unique_rsids), batch_size):
            chunk_rsids = unique_rsids[i:i + batch_size]

            async with async_session_factory() as session:
                for rsid in chunk_rsids:
                    cv_data = cv_map.get(rsid)
                    cv_val = cv_data if cv_data and cv_data.get('found') else None
                    gn_data = gn_map.get(rsid)
                    gn_val = gn_data if gn_data and gn_data.get('found') else None

                    # Get marker_id from first variant with this rsid
                    first_variant = rsid_to_variants[rsid][0]
                    marker_id = getattr(first_variant, 'marker_id', None)

                    # Upsert shared annotation
                    values = dict(
                        rsid=rsid,
                        clinvar_local_data=cv_val,
                        gnomad_data=gn_val,
                        annotation_status='partial',
                        total_api_calls=0,
                        usage_count=1,
                    )
                    if marker_id is not None:
                        values['marker_id'] = marker_id

                    stmt = insert(SharedVariantAnnotation).values(**values)
                    conflict_set = dict(
                        usage_count=SharedVariantAnnotation.usage_count + 1,
                        last_updated_at=func.now(),
                    )
                    if cv_val:
                        conflict_set['clinvar_local_data'] = func.coalesce(
                            SharedVariantAnnotation.clinvar_local_data,
                            stmt.excluded.clinvar_local_data,
                        )
                    if gn_val:
                        conflict_set['gnomad_data'] = func.coalesce(
                            SharedVariantAnnotation.gnomad_data,
                            stmt.excluded.gnomad_data,
                        )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['rsid'],
                        set_=conflict_set,
                    ).returning(SharedVariantAnnotation.id)

                    result = await session.execute(stmt)
                    shared_id = result.scalar_one()

                    # Create variant_annotation links for ALL analysis_variants with this rsid
                    for v in rsid_to_variants[rsid]:
                        session.add(VariantAnnotation(
                            analysis_id=analysis_id,
                            analysis_variant_id=getattr(v, 'id'),
                            shared_annotation_id=shared_id,
                            rsid=rsid,
                        ))

                    # Build in-memory annotation result
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

                    from .scoring_engine import get_scoring_engine
                    ann_data['pathogenicity_score'] = get_scoring_engine().score_variant(
                        ann_data['annotations']
                    )

                    annotation_results[rsid] = AnnotationResult(
                        rsid=rsid, was_reused=False,
                        annotation_data=ann_data, source='local'
                    )
                    saved_count += 1

                await session.commit()

            # Progress + logging
            progress.annotated_variants += sum(
                len(rsid_to_variants[r]) for r in chunk_rsids
            )
            progress.new_annotations += len(chunk_rsids)
            progress.processed_variants = progress.annotated_variants
            await self._update_progress(analysis_id, progress)

            chunk_num = i // batch_size + 1
            total_chunks = (total + batch_size - 1) // batch_size
            if chunk_num % 20 == 0 or chunk_num == total_chunks:
                elapsed = time.time() - bulk_start
                logger.info(
                    f"  Bulk annotation: {saved_count}/{total} RSIDs "
                    f"({progress.annotated_variants} variants, {elapsed:.1f}s)"
                )

            await asyncio.sleep(0)

        elapsed = time.time() - bulk_start
        logger.info(f"Bulk local annotation complete: {saved_count} RSIDs in {elapsed:.1f}s")
        return annotation_results

    async def _bulk_enrich_bigquery(
        self,
        annotation_results: Dict[str, AnnotationResult],
        analysis_id: int,
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

            session = async_session_factory()
            await session.__aenter__()

            try:
                for idx, gene in enumerate(genes_to_process, 1):
                    # Check for cancellation periodically
                    if idx % 20 == 0:
                        await self._check_if_cancelled(analysis_id)

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
                        # Periodic commit even when no data, to flush pending updates
                        if idx % commit_interval == 0 and enriched_genes > 0:
                            await session.commit()
                        await asyncio.sleep(0)
                        continue

                    enriched_genes += 1
                    rsids_for_gene = gene_to_rsids[gene]

                    await session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid.in_(rsids_for_gene))
                        .values(**update_vals)
                    )

                    for rsid in rsids_for_gene:
                        ar = annotation_results.get(rsid)
                        if ar and ar.annotation_data:
                            for src, src_data in mem_updates.items():
                                ar.annotation_data.setdefault('annotations', {})[src] = src_data
                            updated_variants += 1

                    # Periodic commit to persist progress
                    if idx % commit_interval == 0:
                        await session.commit()
                        logger.info(f"  BQ commit checkpoint at gene {idx}/{len(genes_to_process)}")

                    await asyncio.sleep(0)

                # Final commit
                if enriched_genes:
                    await session.commit()

            finally:
                await session.__aexit__(None, None, None)

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
        """Extract gene symbol and consequence from annotation data.
        Falls back to ClinVar DB rsid→gene map when Ensembl data is unavailable."""
        if not annotation_result or not annotation_result.annotation_data:
            # Last resort: ClinVar DB map
            if annotation_result and annotation_result.rsid:
                gene = self._rsid_gene_map.get(annotation_result.rsid)
                if gene:
                    return gene, None, None
            return None, None, None

        try:
            # 1. Try Ensembl
            ensembl_data = annotation_result.annotation_data.get('annotations', {}).get('ensembl', {})
            if ensembl_data:
                data_list = ensembl_data.get('data', [])
                if data_list:
                    entry = data_list[0]
                    transcript_consequences = entry.get('transcript_consequences', [])
                    if transcript_consequences:
                        tc = transcript_consequences[0]
                        gene = tc.get('gene_symbol')
                        if gene:
                            consequence = tc.get('consequence_terms', [None])[0] if tc.get('consequence_terms') else None
                            impact = tc.get('impact')
                            return gene, consequence, impact

            # 2. Try ClinVar local annotation data
            cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
            if cv_local and cv_local.get('found'):
                genes = cv_local.get('genes', [])
                if genes:
                    return genes[0], cv_local.get('molecular_consequence'), None

            # 3. Try gnomAD annotation data
            gnomad = annotation_result.annotation_data.get('annotations', {}).get('gnomad', {})
            if gnomad and gnomad.get('found') and gnomad.get('gene'):
                return gnomad['gene'], gnomad.get('consequence'), gnomad.get('impact')

            # 4. Fallback: ClinVar DB rsid→gene map
            gene = self._rsid_gene_map.get(annotation_result.rsid)
            if gene:
                return gene, None, None

            return None, None, None
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
                consequence_label = (consequence or 'variant').replace("_", " ")

                uncommon_mutations.append(UncommonMutation(
                    analysis_id=analysis_id,
                    mutation_type='low_frequency_variant',
                    gene=gene,
                    mutation_name=f'{gene} {consequence_label}',
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
                # Never overwrite user-initiated statuses (paused/stopped)
                result = await session.execute(
                    select(GeneticAnalysis.analysis_status).where(GeneticAnalysis.id == analysis_id)
                )
                current_status = result.scalar_one_or_none()
                if current_status in ('paused', 'stopped'):
                    return

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
