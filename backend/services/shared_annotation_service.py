import asyncio
import logging
import time
from typing import Dict, List, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, func

from ..db.models import SharedVariantAnnotation

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
    """Read path for shared_variant_annotations, used by insight regeneration.

    Bulk analysis annotation writes go through annotation_coordinator, which
    upserts local + remote data directly. This service only serves the
    cached-annotation lookup used to regenerate insights without re-annotating.
    """

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

    async def get_existing_annotations_fast(self, rsids: List[str], on_progress=None) -> Dict[str, Dict[str, Any]]:
        return await self.get_existing_annotations(
            rsids, update_usage=False, chunk_size=5000, on_progress=on_progress
        )

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
