import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, func
from sqlalchemy.dialects.postgresql import insert

from ..db.models import SharedVariantAnnotation, VariantAnnotation
from ..utils.alpha_missense import get_alpha_missense_service

logger = logging.getLogger(__name__)

_ANNOTATION_COL_MAP: List[Tuple[str, str]] = [
    ('ensembl_data',          'ensembl'),
    ('clinvar_data',          'clinvar'),
    ('pharmgkb_data',         'clinpgx'),
    ('snpedia_data',          'snpedia'),
    ('litvar_data',           'litvar'),
    ('alpha_missense_data',   'alpha_missense'),
    ('clinvar_local_data',    'clinvar_local'),
    ('gnomad_data',           'gnomad'),
    ('thousand_genomes_data', 'thousand_genomes'),
    ('chembl_data',           'chembl'),
    ('fda_drug_data',         'fda_drug'),
    ('alphafold_data',        'alphafold'),
    ('gnomad_tx_data',        'gnomad_tx'),
]

_COL_NAMES = ', '.join(col for col, _ in _ANNOTATION_COL_MAP)
_FETCH_SQL = (
    f"SELECT rsid, {_COL_NAMES} FROM shared_variant_annotations "
    f"WHERE rsid = ANY(:rsids) "
    f"AND annotation_status IN ('completed', 'partial')"
)


def _row_to_annotation_dict(row) -> Dict[str, Any]:
    rsid_val = row[0]
    merged: Dict[str, Any] = {
        'rsid': rsid_val,
        'annotations': {},
        'sources_queried': [],
        'success_count': 0,
    }
    for col_idx, (_, key) in enumerate(_ANNOTATION_COL_MAP, start=1):
        data = row[col_idx]
        if data is not None:
            merged['annotations'][key] = data
            merged['sources_queried'].append(key)
            merged['success_count'] += 1
    return merged


def _empty_annotation_dict(rsid: str) -> Dict[str, Any]:
    return {'rsid': rsid, 'annotations': {}, 'sources_queried': [], 'success_count': 0}


class SharedVariantAnnotationService:
    def __init__(self, session: AsyncSession = None):
        self.session = session
        self._annotation_cache: Dict[str, Dict[str, Any]] = {}

    async def get_existing_annotations(
        self,
        rsids: List[str],
        on_progress=None,
        update_usage: bool = True,
        chunk_size: int = 100_000,
    ) -> Dict[str, Dict[str, Any]]:
        if not rsids:
            return {}

        from ..db.database import async_session_factory
        from sqlalchemy import text

        annotation_map: Dict[str, Dict[str, Any]] = {}
        t0 = time.time()
        total = len(rsids)
        logger.info(f"Loading shared annotations for {total} RSIDs (streaming ANY query)")

        for i in range(0, total, chunk_size):
            chunk = rsids[i:i + chunk_size]
            if i > 0:
                await asyncio.sleep(0)

            async with async_session_factory() as session:
                rows = (await session.execute(text(_FETCH_SQL), {'rsids': chunk})).fetchall()

            for row_idx, row in enumerate(rows):
                if row_idx > 0 and row_idx % 5000 == 0:
                    await asyncio.sleep(0)
                merged = _row_to_annotation_dict(row)
                if merged['success_count'] > 0:
                    annotation_map[merged['rsid']] = merged

            checked = min(i + chunk_size, total)
            elapsed = time.time() - t0
            rate = checked / elapsed if elapsed > 0 else 0
            logger.info(
                f"  Loaded {len(annotation_map)} annotations from {checked}/{total} RSIDs "
                f"({rate:.0f} rsids/s, {elapsed:.1f}s)"
            )
            if on_progress is not None:
                await on_progress(checked, total)

        if update_usage and annotation_map:
            await self._increment_usage_counts(list(annotation_map.keys()))

        elapsed = time.time() - t0
        logger.info(
            f"Found {len(annotation_map)} existing shared annotations "
            f"for {len(rsids)} requested RSIDs ({elapsed:.1f}s)"
        )
        return annotation_map

    async def get_existing_annotations_fast(self, rsids: List[str]) -> Dict[str, Dict[str, Any]]:
        return await self.get_existing_annotations(rsids, update_usage=False, chunk_size=5000)

    async def _increment_usage_counts(self, rsids: List[str]) -> None:
        from ..db.database import async_session_factory
        UPDATE_BATCH = 30_000
        for j in range(0, len(rsids), UPDATE_BATCH):
            batch = rsids[j:j + UPDATE_BATCH]
            async with async_session_factory() as session:
                await session.execute(
                    update(SharedVariantAnnotation)
                    .where(SharedVariantAnnotation.rsid.in_(batch))
                    .values(
                        usage_count=SharedVariantAnnotation.usage_count + 1,
                        last_updated_at=func.now(),
                    )
                )
                await session.commit()
            await asyncio.sleep(0)

    async def save_annotation(
        self,
        rsid: str,
        annotation_data: Dict[str, Any],
        analysis_id: int,
        analysis_variant_id: int,
        marker_id: int = None,
        enabled_sources: Optional[List[str]] = None,
        rsid_gene_map: Optional[Dict[str, str]] = None,
    ) -> bool:
        try:
            annotations = annotation_data.get('annotations', {})
            status, failed = self._compute_annotation_status(annotation_data)
            local_data = await self._fetch_local_source_data(rsid, annotations, enabled_sources)
            values = self._build_insert_values(rsid, annotations, status, failed, local_data, marker_id)
            conflict_set = self._build_conflict_set(annotations, local_data)

            stmt = (
                insert(SharedVariantAnnotation)
                .values(**values)
                .on_conflict_do_update(index_elements=['rsid'], set_=conflict_set)
                .returning(SharedVariantAnnotation.id)
            )

            from ..db.database import async_session_factory
            async with async_session_factory() as save_session:
                result = await save_session.execute(stmt)
                shared_annotation_id = result.scalar_one()
                await self._upsert_variant_link(
                    save_session, analysis_id, analysis_variant_id, shared_annotation_id, rsid
                )
                await save_session.commit()
            return True

        except Exception as e:
            # A failed write must not look like "nothing to save" to the caller —
            # re-raise so the analysis pipeline surfaces and retries/fails loudly
            # instead of silently dropping this variant's annotation.
            logger.error(f"Failed to save annotation for {rsid}: {e}")
            raise

    def _compute_annotation_status(
        self, annotation_data: Dict[str, Any]
    ) -> Tuple[str, List[str]]:
        annotations = annotation_data.get('annotations', {})
        sources_queried = annotation_data.get('sources_queried', ['ensembl', 'clinvar', 'clinpgx', 'snpedia'])
        success_count = annotation_data.get('success_count', 0)
        failed = [src for src in sources_queried if annotations.get(src) is None]
        if failed:
            status = 'partial' if success_count > 0 else 'failed'
        else:
            status = 'completed'
        return status, failed

    async def _fetch_local_source_data(
        self,
        rsid: str,
        annotations: Dict[str, Any],
        enabled_sources: Optional[List[str]],
    ) -> Dict[str, Any]:
        def _enabled(name: str) -> bool:
            return enabled_sources is None or name in enabled_sources

        result: Dict[str, Any] = {
            'am': None, 'cv_local': None, 'gnomad': None,
            'thousand_genomes': None, 'gnomad_tx': None,
            'chembl': None, 'fda_drug': None, 'alphafold': None,
        }
        if _enabled('alpha_missense'):
            result['am'] = await self._lookup_alpha_missense(annotations)
        if _enabled('clinvar_local'):
            result['cv_local'] = await self._lookup_clinvar_local(rsid)
        if _enabled('gnomad'):
            result['gnomad'] = await self._lookup_gnomad(rsid)
        if _enabled('thousand_genomes'):
            result['thousand_genomes'] = await self._lookup_thousand_genomes(rsid)
        if _enabled('gnomad_tx'):
            result['gnomad_tx'] = await self._lookup_gnomad_tx(annotations)
        return result

    async def _lookup_alpha_missense(self, annotations: Dict[str, Any]) -> Optional[Dict]:
        ensembl_ann = annotations.get('ensembl', {})
        if not (ensembl_ann and ensembl_ann.get('found') and ensembl_ann.get('data')):
            return None
        e_entry = ensembl_ann['data'][0] if isinstance(ensembl_ann['data'], list) else ensembl_ann['data']
        chrom = e_entry.get('seq_region_name')
        pos = e_entry.get('start')
        parts = (e_entry.get('allele_string', '') or '').split('/')
        if not (chrom and pos and len(parts) == 2 and len(parts[0]) == 1 and len(parts[1]) == 1):
            return None
        return get_alpha_missense_service().lookup_comprehensive(str(chrom), int(pos), parts[0], parts[1])

    async def _lookup_clinvar_local(self, rsid: str) -> Optional[Dict]:
        from .clinvar_local import get_clinvar_local_service
        svc = get_clinvar_local_service()
        return await svc.lookup(rsid) if svc.is_loaded else None

    async def _lookup_gnomad(self, rsid: str) -> Optional[Dict]:
        from .gnomad_local import get_gnomad_service
        svc = get_gnomad_service()
        return await svc.lookup(rsid, local_only=True) if svc.is_loaded else None

    async def _lookup_thousand_genomes(self, rsid: str) -> Optional[Dict]:
        from .thousand_genomes_local import get_thousand_genomes_service
        svc = get_thousand_genomes_service()
        if not svc.is_loaded:
            return None
        data = await svc.lookup(rsid)
        return data if (data and data.get('found')) else None

    async def _lookup_gnomad_tx(self, annotations: Dict[str, Any]) -> Optional[Dict]:
        ensembl = annotations.get('ensembl', {})
        if not (ensembl and ensembl.get('found') and ensembl.get('data')):
            return None
        entry = ensembl['data'][0] if isinstance(ensembl['data'], list) else ensembl['data']
        chrom = entry.get('seq_region_name')
        pos = entry.get('start')
        parts = (entry.get('allele_string', '') or '').split('/')
        if not (chrom and pos and len(parts) == 2 and len(parts[0]) == 1 and len(parts[1]) == 1):
            return None
        from .gnomad_local import get_gnomad_tx_service
        svc = get_gnomad_tx_service()
        return await svc.lookup(str(chrom), int(pos), parts[0], parts[1]) if svc.available else None

    def _build_insert_values(
        self,
        rsid: str,
        annotations: Dict[str, Any],
        status: str,
        failed: List[str],
        local_data: Dict[str, Any],
        marker_id: Optional[int],
    ) -> Dict[str, Any]:
        values: Dict[str, Any] = dict(
            rsid=rsid,
            ensembl_data=annotations.get('ensembl'),
            clinvar_data=annotations.get('clinvar'),
            pharmgkb_data=annotations.get('clinpgx'),
            snpedia_data=annotations.get('snpedia'),
            litvar_data=annotations.get('litvar'),
            annotation_status=status,
            failed_sources=failed or None,
            total_api_calls=annotations.get('success_count', 0),
            usage_count=1,
        )
        optional_cols = {
            'alpha_missense_data':    local_data.get('am'),
            'clinvar_local_data':     local_data.get('cv_local'),
            'gnomad_data':            local_data.get('gnomad'),
            'thousand_genomes_data':  local_data.get('thousand_genomes'),
            'gnomad_tx_data':         local_data.get('gnomad_tx'),
            'chembl_data':            local_data.get('chembl'),
            'fda_drug_data':          local_data.get('fda_drug'),
            'alphafold_data':         local_data.get('alphafold'),
        }
        for col, val in optional_cols.items():
            if val is not None:
                values[col] = val
        if marker_id is not None:
            values['marker_id'] = marker_id
        return values

    def _build_conflict_set(
        self,
        annotations: Dict[str, Any],
        local_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        from sqlalchemy import case, literal
        stmt_excl = insert(SharedVariantAnnotation).excluded
        conflict_set: Dict[str, Any] = dict(
            usage_count=SharedVariantAnnotation.usage_count + 1,
            last_updated_at=func.now(),
        )
        for col_name, ann_key in [
            ('ensembl_data', 'ensembl'), ('clinvar_data', 'clinvar'),
            ('pharmgkb_data', 'clinpgx'), ('snpedia_data', 'snpedia'), ('litvar_data', 'litvar'),
        ]:
            if annotations.get(ann_key) is not None:
                col = getattr(SharedVariantAnnotation, col_name)
                conflict_set[col_name] = func.coalesce(col, stmt_excl[col_name])

        for col_name, local_key in [
            ('alpha_missense_data', 'am'), ('clinvar_local_data', 'cv_local'),
            ('gnomad_data', 'gnomad'), ('thousand_genomes_data', 'thousand_genomes'),
            ('gnomad_tx_data', 'gnomad_tx'), ('chembl_data', 'chembl'),
            ('fda_drug_data', 'fda_drug'), ('alphafold_data', 'alphafold'),
        ]:
            if local_data.get(local_key):
                col = getattr(SharedVariantAnnotation, col_name)
                conflict_set[col_name] = func.coalesce(col, stmt_excl[col_name])

        merged_ensembl  = func.coalesce(SharedVariantAnnotation.ensembl_data,  stmt_excl.ensembl_data)
        merged_clinvar  = func.coalesce(SharedVariantAnnotation.clinvar_data,   stmt_excl.clinvar_data)
        merged_pharmgkb = func.coalesce(SharedVariantAnnotation.pharmgkb_data,  stmt_excl.pharmgkb_data)
        merged_snpedia  = func.coalesce(SharedVariantAnnotation.snpedia_data,   stmt_excl.snpedia_data)
        all_core_present = (
            merged_ensembl.isnot(None) & merged_clinvar.isnot(None)
            & merged_pharmgkb.isnot(None) & merged_snpedia.isnot(None)
        )
        conflict_set['annotation_status'] = case(
            (all_core_present, literal('completed')), else_=literal('partial')
        )
        conflict_set['failed_sources'] = case(
            (all_core_present, None), else_=stmt_excl.failed_sources
        )
        return conflict_set

    async def _upsert_variant_link(
        self,
        session: AsyncSession,
        analysis_id: int,
        analysis_variant_id: int,
        shared_annotation_id: int,
        rsid: str,
    ) -> None:
        stmt = (
            insert(VariantAnnotation)
            .values(
                analysis_id=analysis_id,
                analysis_variant_id=analysis_variant_id,
                shared_annotation_id=shared_annotation_id,
                rsid=rsid,
            )
            .on_conflict_do_nothing(constraint='uq_variant_annotations_analysis_variant')
        )
        await session.execute(stmt)
