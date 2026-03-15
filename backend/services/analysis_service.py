"""
Genetic analysis service — annotates variants and populates all category tables.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Any, Callable, Tuple
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

        from .scoring_engine import get_scoring_engine
        scorer = get_scoring_engine()

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

                # Include 1000 Genomes Phase 3 data (PG-backed)
                tkg = getattr(annotation, 'thousand_genomes_data', None)
                if tkg is not None:
                    merged_data['annotations']['thousand_genomes'] = tkg

                # Include BigQuery data (ChEMBL, FDA Drug, AlphaFold)
                for bq_src, bq_col in (('chembl', 'chembl_data'), ('fda_drug', 'fda_drug_data'), ('alphafold', 'alphafold_data')):
                    bq_data = getattr(annotation, bq_col, None)
                    if bq_data is not None:
                        merged_data['annotations'][bq_src] = bq_data

                # Compute composite pathogenicity score
                merged_data['pathogenicity_score'] = scorer.score_variant(
                    merged_data['annotations']
                )

                if merged_data['success_count'] > 0:
                    annotation_map[annotation.rsid] = merged_data

        if annotation_map:
            # Chunk usage_count updates to stay under PostgreSQL's 32767 parameter limit
            found_rsids = list(annotation_map.keys())
            UPDATE_BATCH = 30000
            for j in range(0, len(found_rsids), UPDATE_BATCH):
                batch = found_rsids[j:j + UPDATE_BATCH]
                await self.session.execute(
                    update(SharedVariantAnnotation)
                    .where(SharedVariantAnnotation.rsid.in_(batch))
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

            # Look up 1000 Genomes Phase 3 data
            thousand_genomes_data_val = None
            if enabled_sources is None or '1000genomes' in enabled_sources:
                from .thousand_genomes_local import get_thousand_genomes_service
                tkg_svc = get_thousand_genomes_service()
                if tkg_svc.is_loaded:
                    thousand_genomes_data_val = await tkg_svc.lookup(rsid)
                    if thousand_genomes_data_val and not thousand_genomes_data_val.get('found'):
                        thousand_genomes_data_val = None

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
                thousand_genomes_data=thousand_genomes_data_val,
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
            if thousand_genomes_data_val:
                conflict_set['thousand_genomes_data'] = func.coalesce(
                    SharedVariantAnnotation.thousand_genomes_data,
                    stmt.excluded.thousand_genomes_data,
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

            # Use INSERT ... ON CONFLICT DO NOTHING to handle resume/retry
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            va_stmt = pg_insert(VariantAnnotation).values(
                analysis_id=analysis_id,
                analysis_variant_id=analysis_variant_id,
                shared_annotation_id=shared_annotation_id,
                rsid=rsid
            ).on_conflict_do_nothing(
                constraint='uq_variant_annotations_analysis_variant'
            )
            await self.session.execute(va_stmt)
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
                status="processing",
                phase=1,
                phase_progress=0.0,
            )
            await self._update_progress(analysis_id, progress)

            # ── Phase 1: Build gene map (always — cheap, in-memory only) ──
            logger.info(f"═══ Phase 1/4: Building gene map ═══")
            all_rsids = [str(v.rsid) for v in variants if v.rsid]
            await self._build_rsid_gene_map(variants)
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

            async with async_session_factory() as session:
                annotation_service = SharedVariantAnnotationService(session)
                annotation_results = await self._annotate_variants_efficiently(
                    variants, analysis_id, annotation_service, progress
                )
            progress.phase_progress = 1.0
            logger.info(f"═══ Phase 2/4 complete ({time.time() - phase_start:.1f}s) ═══")

            # ── Phase 3: BigQuery enrichment (own session, periodic commits) ──
            progress.phase = 3
            progress.phase_progress = 0.0
            progress.current_step = "enriching_bigquery"
            await self._update_progress(analysis_id, progress)
            logger.info(f"═══ Phase 3/4: BigQuery enrichment ═══")
            phase_start = time.time()
            await self._bulk_enrich_bigquery(annotation_results, analysis_id, progress)
            progress.phase_progress = 1.0
            logger.info(f"═══ Phase 3/4 complete ({time.time() - phase_start:.1f}s) ═══")

            # ── Phase 4: Generate insights (own session, committed at end) ──
            progress.phase = 4
            progress.phase_progress = 0.0
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
            progress.phase = 4
            progress.phase_progress = 1.0
            await self._update_progress(analysis_id, progress, force_percentage=100)

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
            do_ensembl = await vep_svc.ensure_loaded()

        do_1kg = enabled_sources is None or '1000genomes' in enabled_sources
        tkg_svc = None
        if do_1kg:
            from .thousand_genomes_local import get_thousand_genomes_service
            tkg_svc = get_thousand_genomes_service()
            do_1kg = tkg_svc.is_loaded

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
            if do_1kg and '1000genomes' not in data.get('annotations', {})
        ]

        if not missing_cv and not missing_gnomad and not missing_ensembl and not missing_1kg:
            # Skip to BQ backfill check below
            pass
        else:
            # --- Batch lookups (parallel-friendly: each uses its own read session) ---
            cv_results: Dict[str, Optional[Dict]] = {}
            gn_results: Dict[str, Optional[Dict]] = {}
            ens_results: Dict[str, Optional[Dict]] = {}

            if missing_cv:
                logger.info(f"Backfilling ClinVar Local for {len(missing_cv)} existing annotations")
                cv_results = await cv_svc.lookup_batch(missing_cv)
            if missing_gnomad:
                logger.info(f"Backfilling gnomAD for {len(missing_gnomad)} existing annotations")
                gn_results = await gnomad_svc.lookup_batch(missing_gnomad)
            if missing_ensembl:
                logger.info(f"Backfilling Ensembl VEP for {len(missing_ensembl)} existing annotations")
                ens_results = await vep_svc.lookup_batch(missing_ensembl)

            tkg_results: Dict[str, Optional[Dict]] = {}
            if missing_1kg:
                logger.info(f"Backfilling 1000G for {len(missing_1kg)} existing annotations")
                tkg_results = await tkg_svc.lookup_batch(missing_1kg)

            # --- Batch DB updates using executemany (pipelined via asyncpg) ---
            from sqlalchemy import bindparam
            cv_updated = gn_updated = ens_updated = 0

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
                    existing_annotations[rsid]['annotations']['1000genomes'] = tkg_data

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

                if cv_updated or gn_updated or ens_updated or tkg_updated:
                    await session.commit()

            if cv_updated:
                logger.info(f"Backfilled ClinVar Local data for {cv_updated}/{len(missing_cv)} annotations")
            if gn_updated:
                logger.info(f"Backfilled gnomAD data for {gn_updated}/{len(missing_gnomad)} annotations")
            if ens_updated:
                logger.info(f"Backfilled Ensembl VEP data for {ens_updated}/{len(missing_ensembl)} annotations")
            if tkg_updated:
                logger.info(f"Backfilled 1000G data for {tkg_updated}/{len(missing_1kg)} annotations")

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

        # --- Step 2.5: Batch Ensembl VEP local lookups ---
        ens_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or 'ensembl' in enabled_sources:
            from .ensembl_vep_local import get_ensembl_vep_service
            vep_svc = get_ensembl_vep_service()
            if await vep_svc.ensure_loaded():
                t0 = time.time()
                ens_map = await vep_svc.lookup_batch(unique_rsids)
                ens_found = sum(1 for v in ens_map.values() if v and v.get('found'))
                logger.info(f"  Ensembl VEP local batch: {ens_found}/{total} found ({time.time() - t0:.1f}s)")

        # --- Step 2.6: Batch 1000 Genomes local lookups ---
        tkg_map: Dict[str, Optional[Dict]] = {}
        if enabled_sources is None or '1000genomes' in enabled_sources:
            from .thousand_genomes_local import get_thousand_genomes_service
            tkg_svc = get_thousand_genomes_service()
            if tkg_svc.is_loaded:
                t0 = time.time()
                tkg_map = await tkg_svc.lookup_batch(unique_rsids)
                tkg_found = sum(1 for v in tkg_map.values() if v and v.get('found'))
                logger.info(f"  1000G local batch: {tkg_found}/{total} found ({time.time() - t0:.1f}s)")

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
                first_variant = rsid_to_variants[rsid][0]
                marker_id = getattr(first_variant, 'marker_id', None)

                row = dict(
                    rsid=rsid,
                    clinvar_local_data=cv_val,
                    gnomad_data=gn_val,
                    ensembl_data=ens_val,
                    thousand_genomes_data=tkg_val,
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

            await asyncio.sleep(0)

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

                    await asyncio.sleep(0)

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

        total_generators = len(generators)
        for gen_idx, generator in enumerate(generators):
            await self._check_if_cancelled(analysis_id)
            try:
                progress.current_step = f"generating_{generator.__name__.replace('_generate_', '')}"
                progress.phase_progress = gen_idx / total_generators
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

    @staticmethod
    def _get_user_genotype(variant) -> Optional[str]:
        """Extract the user's genotype from the variant.

        Checks the dedicated ``genotype`` column first, then falls back to
        ``info.original_genotype`` (older CSV uploads stored it there).
        """
        gt = getattr(variant, 'genotype', None)
        if gt:
            return gt.strip().upper()
        info = getattr(variant, 'info', None)
        if isinstance(info, dict):
            og = info.get('original_genotype')
            if og:
                return str(og).strip().upper()
        return None

    @staticmethod
    def _is_homozygous_reference(genotype: Optional[str]) -> bool:
        """Return True when the genotype is homozygous (both alleles identical).

        For a rare pathogenic SNV (freq < 1%), being homozygous almost
        certainly means the user carries two copies of the **reference**
        allele, not the pathogenic alternate (probability < 0.0001%).
        """
        if not genotype:
            return False
        gt = genotype.strip().upper()
        # Handle different genotype formats
        if '/' in gt:
            alleles = gt.split('/')
        elif '|' in gt:
            alleles = gt.split('|')
        elif len(gt) == 2:
            alleles = [gt[0], gt[1]]
        elif len(gt) == 1:
            # Hemizygous (e.g. X chromosome in males) — single allele,
            # treat as "not heterozygous" but don't skip since it could
            # be the alternate allele.
            return False
        else:
            return False
        return len(alleles) == 2 and alleles[0] == alleles[1]

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
        """Estimate ancestry composition using a genotype-likelihood model.

        Queries the thousand_genomes_variants table directly (JOIN via
        genetic_markers) to obtain population-specific allele frequencies,
        then computes P(observed_genotype | population) under Hardy-Weinberg.
        Log-likelihoods are summed across informative variants and
        normalised via softmax to produce percentage estimates.
        """
        from ..db.models import AncestryResult
        from ..db.database import async_session_factory
        import math
        from sqlalchemy import text

        POP_CODES = ['afr', 'amr', 'eas', 'eur', 'sas']
        POP_LABELS = {
            'afr': 'African',
            'amr': 'Admixed American',
            'eas': 'East Asian',
            'eur': 'European',
            'sas': 'South Asian',
        }
        POP_ORIGINS = {
            'afr': 'Sub-Saharan Africa',
            'amr': 'The Americas',
            'eas': 'East & Southeast Asia',
            'eur': 'Europe & Western Asia',
            'sas': 'South & Central Asia',
        }

        FLOOR = 0.001

        def _genotype_log_likelihood(af: float, gt_type: str) -> float:
            p = max(min(af, 1 - FLOOR), FLOOR)
            q = 1 - p
            if gt_type == 'hom_ref':
                return math.log(q * q + 1e-30)
            elif gt_type == 'het':
                return math.log(2 * p * q + 1e-30)
            else:
                return math.log(p * p + 1e-30)

        def _classify_genotype(gt_str: Optional[str], ref: Optional[str], alt: Optional[str]) -> Optional[str]:
            if not gt_str:
                return None
            gt = gt_str.strip().upper()
            if '/' in gt:
                alleles = gt.split('/')
            elif '|' in gt:
                alleles = gt.split('|')
            elif len(gt) == 2:
                alleles = [gt[0], gt[1]]
            else:
                return None
            if len(alleles) != 2:
                return None
            a1, a2 = alleles[0].strip(), alleles[1].strip()
            ref_u = (ref or '').strip().upper()
            alt_u = (alt or '').strip().upper()
            if ref_u and alt_u:
                is_ref = [a == ref_u for a in (a1, a2)]
                is_alt = [a == alt_u for a in (a1, a2)]
                if all(is_ref):
                    return 'hom_ref'
                if all(is_alt):
                    return 'hom_alt'
                if any(is_ref) and any(is_alt):
                    return 'het'
                if a1 != a2:
                    return 'het'
                return 'hom_ref'
            else:
                if a1 == a2:
                    return 'hom_ref'
                return 'het'

        # ── Bulk-fetch population AFs directly from thousand_genomes_variants ──
        # Use a separate read-only session so we don't bloat the write session.
        rows = []
        async with async_session_factory() as read_session:
            result_proxy = await read_session.execute(text("""
                SELECT gm.rsid, av.genotype, gm.ref_allele, gm.alt_alleles,
                       tg.af_afr, tg.af_amr, tg.af_eas, tg.af_eur, tg.af_sas
                FROM analysis_variants av
                JOIN genetic_markers gm ON av.marker_id = gm.id
                JOIN thousand_genomes_variants tg ON gm.rsid = tg.rsid
                WHERE av.analysis_id = :aid
                  AND tg.af_eur IS NOT NULL
                  AND tg.af_afr IS NOT NULL
            """), {'aid': analysis_id})
            rows = result_proxy.fetchall()

        logger.info(f"Ancestry: fetched {len(rows)} variant×1000G rows for analysis {analysis_id}")

        # De-duplicate by rsid (keep first row per rsid)
        seen_rsids: set = set()
        unique_rows = []
        for row in rows:
            if row[0] not in seen_rsids:
                seen_rsids.add(row[0])
                unique_rows.append(row)

        log_likelihoods = {p: 0.0 for p in POP_CODES}
        informative_count = 0
        contributing_rsids: Dict[str, List[str]] = {p: [] for p in POP_CODES}

        for rsid, genotype, ref_allele, alt_alleles, af_afr, af_amr, af_eas, af_eur, af_sas in unique_rows:
            afs = {
                'afr': af_afr or 0.0,
                'amr': af_amr or 0.0,
                'eas': af_eas or 0.0,
                'eur': af_eur or 0.0,
                'sas': af_sas or 0.0,
            }

            af_vals = list(afs.values())
            # Skip uninformative variants (all AFs very similar)
            if max(af_vals) - min(af_vals) < 0.05:
                continue
            # Skip fixed variants
            if min(af_vals) > 0.95 or max(af_vals) < 0.005:
                continue

            gt_type = _classify_genotype(genotype, ref_allele, alt_alleles)
            if not gt_type:
                continue

            informative_count += 1

            for pc in POP_CODES:
                ll = _genotype_log_likelihood(afs[pc], gt_type)
                log_likelihoods[pc] += ll

            best_pop = max(afs, key=lambda p: afs[p])
            if afs[best_pop] > 0.3:
                contributing_rsids[best_pop].append(rsid)

        logger.info(f"Ancestry: {informative_count} informative variants out of {len(unique_rows)} unique")

        # ── Convert log-likelihoods to percentages ──
        if informative_count < 10:
            result = AncestryResult(
                analysis_id=analysis_id,
                population='Undetermined',
                percentage='0',
                confidence='low',
                geographic_origin='Insufficient data',
                associated_variants=[getattr(v, 'rsid', '') for v in variants[:5] if getattr(v, 'rsid', None)],
                composition=[{'region': 'Undetermined', 'percentage': 0}],
            )
            session.add(result)
            return 1

        max_ll = max(log_likelihoods.values())
        # Temperature scaling: with many variants, raw log-likelihoods
        # produce extreme softmax concentrations.  Scale by a factor
        # proportional to the number of informative variants so that the
        # resulting distribution has realistic spread (similar to using a
        # curated panel of ~1-2 K ancestry-informative markers).
        temperature = max(informative_count / 500, 1.0)
        exp_lls = {p: math.exp((log_likelihoods[p] - max_ll) / temperature) for p in POP_CODES}
        total_exp = sum(exp_lls.values()) or 1.0
        percentages = {p: round((exp_lls[p] / total_exp) * 100, 1) for p in POP_CODES}

        dominant_pop = max(percentages, key=lambda p: percentages[p])
        confidence = 'high' if percentages[dominant_pop] > 60 else 'moderate' if percentages[dominant_pop] > 35 else 'low'

        composition = sorted(
            [
                {'region': POP_LABELS[p], 'percentage': percentages[p]}
                for p in POP_CODES if percentages[p] >= 0.5
            ],
            key=lambda x: x['percentage'],
            reverse=True,
        )

        # ── Neanderthal estimation ──
        NEANDERTHAL_RSIDS = {
            'rs2066827', 'rs10166942', 'rs2298813', 'rs4792887', 'rs1534696',
            'rs3917862', 'rs10490770', 'rs2664280', 'rs12477142', 'rs11209026',
            'rs1800407', 'rs7214986', 'rs2066807', 'rs4988235', 'rs12913832',
            'rs1426654', 'rs16891982', 'rs1805007', 'rs1805008', 'rs6152',
        }
        user_rsids = {getattr(v, 'rsid', '') for v in variants}
        neanderthal_hits = user_rsids & NEANDERTHAL_RSIDS
        neanderthal_pct = round(len(neanderthal_hits) / max(len(NEANDERTHAL_RSIDS), 1) * 3.5, 1)
        neanderthal_pct = min(neanderthal_pct, 4.0)

        neanderthal_data = {
            'percentage': neanderthal_pct,
            'variants': len(neanderthal_hits),
            'moreOrLess': 'more' if neanderthal_pct > 2.0 else 'less' if neanderthal_pct < 1.5 else 'about average',
            'comparison': f'than the average of ~2% for non-African populations ({informative_count} variants analyzed)',
        }

        logger.info(f"Ancestry result: {', '.join(f'{POP_LABELS[p]} {percentages[p]}%' for p in POP_CODES)} "
                     f"(dominant={POP_LABELS[dominant_pop]}, confidence={confidence})")

        result = AncestryResult(
            analysis_id=analysis_id,
            population=POP_LABELS[dominant_pop],
            percentage=str(percentages[dominant_pop]),
            confidence=confidence,
            geographic_origin=POP_ORIGINS[dominant_pop],
            associated_variants=contributing_rsids.get(dominant_pop, [])[:20],
            composition=composition,
            neanderthal_variants=neanderthal_data,
        )
        session.add(result)
        return 1

    async def _generate_carrier_status(self, variants, annotation_results, analysis_id, session) -> int:
        from ..db.models import CarrierStatus
        carrier_rsid_map, _ = self._get_maps('carrier')
        carrier_results = []
        seen_conditions: set = set()

        for variant in variants:
            variant_rsid = getattr(variant, 'rsid', None)
            if not variant_rsid:
                continue

            # Skip homozygous-reference genotypes — user doesn't carry
            # the alternate allele at this position.
            user_gt = self._get_user_genotype(variant)
            if self._is_homozygous_reference(user_gt):
                continue

            # Registry-based matching
            if variant_rsid in carrier_rsid_map:
                info = carrier_rsid_map[variant_rsid]
                cond = info['condition']
                if cond not in seen_conditions:
                    seen_conditions.add(cond)
                    carrier_results.append(CarrierStatus(
                        analysis_id=analysis_id,
                        condition=cond,
                        carrier_status=info['status'],
                        inheritance_pattern=info.get('inheritance', 'autosomal_recessive'),
                        associated_variants=[variant_rsid],
                        genetic_counseling_recommended=info.get('counseling', False)
                    ))

            # ClinVar-local annotation-based discovery
            annotation_result = annotation_results.get(variant_rsid)
            if not annotation_result or not annotation_result.annotation_data:
                continue

            cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
            if not cv_local or not cv_local.get('found'):
                continue

            clin_sigs = cv_local.get('clinical_significances', [])
            sig_lower = ' '.join(s.lower() for s in clin_sigs)

            # Only carrier-relevant: pathogenic/likely pathogenic variants
            if not any(kw in sig_lower for kw in ('pathogenic', 'risk_factor', 'risk factor')):
                continue

            gene_conditions = cv_local.get('gene_conditions', [])
            if not gene_conditions:
                continue

            genotype = getattr(variant, 'genotype', '') or ''
            is_homozygous = len(set(genotype.replace('/', ''))) == 1 if genotype else False

            for gc in gene_conditions:
                disease = gc.get('disease', '')
                if not disease or disease in seen_conditions or disease.lower() == 'not provided':
                    continue
                seen_conditions.add(disease)

                status = 'affected' if is_homozygous else 'carrier'
                inheritance = 'autosomal_recessive'
                if 'dominant' in disease.lower():
                    inheritance = 'autosomal_dominant'
                elif 'x-linked' in disease.lower():
                    inheritance = 'x_linked'

                needs_counseling = 'pathogenic' in sig_lower and not ('benign' in sig_lower)
                carrier_results.append(CarrierStatus(
                    analysis_id=analysis_id,
                    condition=disease,
                    carrier_status=status,
                    inheritance_pattern=inheritance,
                    associated_variants=[variant_rsid],
                    genetic_counseling_recommended=needs_counseling
                ))

        # Prioritize counseling-recommended conditions but cap at 100
        carrier_results.sort(key=lambda c: (0 if c.genetic_counseling_recommended else 1, c.condition))
        carrier_results = carrier_results[:100]

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

            # Must have ClinVar data to qualify
            cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
            clinvar_api = annotation_result.annotation_data.get('annotations', {}).get('clinvar', {})
            if not ((cv_local and cv_local.get('found')) or (clinvar_api and clinvar_api.get('found'))):
                continue

            # Skip homozygous-reference genotypes — if both alleles are
            # identical at a rare ClinVar position, the user almost certainly
            # carries the reference allele, not the pathogenic alternate.
            user_gt = self._get_user_genotype(variant)
            if self._is_homozygous_reference(user_gt):
                continue

            # Extract frequency — must be truly rare (< 1%)
            freq = self._extract_frequency(annotation_result)
            # Also try gnomAD direct AF if ensembl frequency missing
            if freq == 0.0:
                gnomad = annotation_result.annotation_data.get('annotations', {}).get('gnomad', {})
                if gnomad and gnomad.get('found'):
                    freq = gnomad.get('af', 0.0) or 0.0
            if freq > 0.01:
                continue

            # Extract gene and consequence
            gene, consequence, impact = self._extract_gene_and_consequence(annotation_result)

            # Extract clinical significance from ClinVar local
            clinical_significance = 'uncertain'
            disease_association = ''
            gene_conditions = []
            inheritance_pattern = 'unknown'
            penetrance = 'unknown'

            if cv_local and cv_local.get('found'):
                clin_sigs = cv_local.get('clinical_significances', [])
                if clin_sigs:
                    raw_sig = clin_sigs[0].lower().replace('_', ' ')
                    if 'conflicting' in raw_sig:
                        clinical_significance = 'conflicting'
                        penetrance = 'unknown'
                    elif 'pathogenic' in raw_sig and 'benign' not in raw_sig:
                        clinical_significance = 'pathogenic' if 'likely' not in raw_sig else 'likely_pathogenic'
                        penetrance = 'moderate'
                    elif 'benign' in raw_sig and 'pathogenic' not in raw_sig:
                        clinical_significance = 'benign' if 'likely' not in raw_sig else 'likely_benign'
                    elif 'risk' in raw_sig:
                        clinical_significance = 'risk_factor'

                gene_conditions = cv_local.get('gene_conditions', [])
                if gene_conditions:
                    diseases = [gc.get('disease', '') for gc in gene_conditions
                                if gc.get('disease') and gc.get('disease', '').lower() != 'not provided']
                    disease_association = '; '.join(diseases[:3]) if diseases else ''

                    # Infer inheritance from disease name
                    for gc in gene_conditions:
                        d = gc.get('disease', '').lower()
                        if 'dominant' in d:
                            inheritance_pattern = 'autosomal_dominant'
                            break
                        elif 'recessive' in d:
                            inheritance_pattern = 'autosomal_recessive'
                            break
                        elif 'x-linked' in d:
                            inheritance_pattern = 'x_linked'
                            break

                if not gene:
                    genes = cv_local.get('genes', [])
                    if genes:
                        gene = genes[0]

            # Skip benign/likely_benign — not clinically relevant as rare findings
            if clinical_significance in ('benign', 'likely_benign'):
                continue

            if not gene:
                continue

            consequence_label = (consequence or 'variant').replace('_', ' ')
            mutation_name = f'{gene} {consequence_label}'

            # Determine mutation type from clinical significance
            if clinical_significance in ('pathogenic', 'likely_pathogenic'):
                mutation_type = 'clinically_significant'
            elif clinical_significance == 'conflicting':
                mutation_type = 'conflicting_evidence'
            elif clinical_significance == 'risk_factor':
                mutation_type = 'risk_factor'
            else:
                mutation_type = 'potentially_significant'

            # Build clinical actions based on significance
            clinical_actions = []
            if clinical_significance in ('pathogenic', 'likely_pathogenic'):
                clinical_actions = ['Genetic counseling recommended', 'Discuss with specialist']
            elif clinical_significance == 'conflicting':
                clinical_actions = ['Further testing may clarify significance']
            else:
                clinical_actions = ['Monitor in future research updates']

            rare_mutations.append(RareMutation(
                analysis_id=analysis_id,
                mutation_type=mutation_type,
                gene=gene,
                mutation_name=mutation_name,
                clinical_significance=clinical_significance,
                disease_association=disease_association or 'No known disease association',
                penetrance=penetrance,
                inheritance_pattern=inheritance_pattern,
                population_frequency=freq if freq > 0 else 0.001,
                clinical_actions=clinical_actions,
                specialist_referral=clinical_significance in ('pathogenic', 'likely_pathogenic'),
                genetic_counseling_urgent=clinical_significance == 'pathogenic',
                monitoring_recommendations=['Regular medical follow-up'],
                family_screening_recommended=clinical_significance in ('pathogenic', 'likely_pathogenic'),
                associated_variants=[variant_rsid]
            ))

        # Sort by clinical priority and cap at 150 most significant
        sig_priority = {
            'pathogenic': 0, 'likely_pathogenic': 1, 'risk_factor': 2,
            'conflicting': 3, 'uncertain': 4
        }
        rare_mutations.sort(key=lambda m: (sig_priority.get(m.clinical_significance, 5), m.population_frequency))
        rare_mutations = rare_mutations[:150]

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

            # Skip homozygous-reference genotypes
            user_gt = self._get_user_genotype(variant)
            if self._is_homozygous_reference(user_gt):
                continue

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
