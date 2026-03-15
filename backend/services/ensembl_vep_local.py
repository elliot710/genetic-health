"""
Local Ensembl VEP lookup service backed by PostgreSQL (ensembl_vep_variants table).

Provides batch rsid lookups returning data in the same format as the Ensembl
REST VEP API, so downstream code (extract_gene_info, extract_frequency, etc.)
works unchanged.

Usage:
    svc = get_ensembl_vep_service()
    await svc.ensure_loaded()
    result = await svc.lookup('rs1234')
    batch = await svc.lookup_batch(['rs1234', 'rs5678'])
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func

from ..db.database import async_session_factory
from ..db.models import EnsemblVepVariant

logger = logging.getLogger(__name__)


class EnsemblVepLocalService:
    """PostgreSQL-backed Ensembl VEP lookup service."""

    def __init__(self):
        self._variant_count: Optional[int] = None

    @property
    def is_loaded(self) -> bool:
        return self._variant_count is not None and self._variant_count > 0

    @property
    def variant_count(self) -> int:
        return self._variant_count or 0

    async def ensure_loaded(self) -> bool:
        """Check if ensembl_vep_variants table has data."""
        if self._variant_count is not None:
            return self._variant_count > 0
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(EnsemblVepVariant)
                )
                self._variant_count = result.scalar() or 0
            if self._variant_count > 0:
                logger.info(f"Ensembl VEP local: {self._variant_count} variants available")
            else:
                logger.info("Ensembl VEP local: no variants loaded (run ETL first)")
            return self._variant_count > 0
        except Exception as e:
            self._variant_count = 0
            logger.debug(f"Ensembl VEP local: table not available: {e}")
            return False

    def _format_result(self, row: EnsemblVepVariant) -> Dict[str, Any]:
        """Format a DB row into the Ensembl VEP API-compatible dict."""
        if row.vep_data and isinstance(row.vep_data, dict):
            return row.vep_data
        # Fallback: build from columns
        return {
            'found': True,
            'source': 'ensembl',
            'data': [{
                'allele_string': f"{row.ref_allele}/{row.alt_alleles}",
                'seq_region_name': row.chromosome,
                'start': row.position,
                'most_severe_consequence': row.most_severe_consequence,
                'transcript_consequences': [],
            }],
        }

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a single rsid."""
        if not await self.ensure_loaded():
            return None
        async with async_session_factory() as session:
            result = await session.execute(
                select(EnsemblVepVariant).where(EnsemblVepVariant.rsid == rsid)
            )
            row = result.scalar_one_or_none()
            if not row:
                return {'found': False, 'source': 'ensembl'}
            return self._format_result(row)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by rsids. Uses raw column access to skip ORM hydration."""
        if not rsids:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        batch_size = 2000
        async with async_session_factory() as session:
            for i in range(0, len(rsids), batch_size):
                chunk = rsids[i:i + batch_size]
                result = await session.execute(
                    select(
                        EnsemblVepVariant.rsid,
                        EnsemblVepVariant.vep_data,
                    ).where(
                        EnsemblVepVariant.rsid.in_(chunk)
                    )
                )
                for row in result.all():
                    vep = row.vep_data
                    if vep and isinstance(vep, dict):
                        results[row.rsid] = vep
                    else:
                        results[row.rsid] = {'found': True, 'source': 'ensembl', 'data': []}
        return results


# Singleton
_instance: Optional[EnsemblVepLocalService] = None


def get_ensembl_vep_service() -> EnsemblVepLocalService:
    global _instance
    if _instance is None:
        _instance = EnsemblVepLocalService()
    return _instance
