"""
Local Ensembl VEP lookup service backed by VCF files on disk.

Scans per-chromosome VCF files once, builds an in-memory cache of
rsid → vep_data for rsids present in genetic_markers.
No PostgreSQL table needed — reads directly from compressed VCF files.

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

import asyncio
import gzip
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select

from ..db.database import async_session_factory
from ..db.models import GeneticMarker

logger = logging.getLogger(__name__)

_ENSEMBL_DATA_DIR = Path(os.environ.get(
    'ENSEMBL_DATA_DIR',
    '/app/data_sources/ensembl/homo_sapiens',
))
_VCF_VEP_DIR = _ENSEMBL_DATA_DIR / 'variation' / 'vcf_vep'

_CHR_PATTERN = re.compile(r'homo_sapiens_incl_consequences-chr\w+\.vcf\.gz$')


class EnsemblVepLocalService:
    """VCF-file-backed Ensembl VEP lookup service.

    On first use, scans all per-chromosome VCF files and caches parsed VEP data
    for rsids present in the genetic_markers table.  Subsequent lookups are
    instant from the in-memory dict.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded and len(self._cache) > 0

    @property
    def variant_count(self) -> int:
        return len(self._cache)

    async def ensure_loaded(self) -> bool:
        """Scan VCF files and build in-memory cache (runs once)."""
        if self._loaded:
            return len(self._cache) > 0
        async with self._lock:
            if self._loaded:
                return len(self._cache) > 0
            try:
                await self._load_from_vcf_files()
            except Exception as e:
                logger.error(f"Failed to load Ensembl VEP from VCF files: {e}")
            self._loaded = True
        return len(self._cache) > 0

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def _load_known_rsids(self) -> Set[str]:
        """Load all rsids from genetic_markers table."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticMarker.rsid).where(GeneticMarker.rsid.isnot(None))
            )
            rsids = {r[0] for r in result.all()}
        logger.info(f"Ensembl VEP file service: {len(rsids)} known rsids for filtering")
        return rsids

    async def _load_from_vcf_files(self):
        """Scan VCF files and populate in-memory cache for known rsids."""
        if not _VCF_VEP_DIR.exists():
            logger.warning(f"VCF VEP directory not found: {_VCF_VEP_DIR}")
            return

        known_rsids = await self._load_known_rsids()
        if not known_rsids:
            logger.info("No known rsids — skipping VCF scan")
            return

        # Discover per-chromosome consequence VCFs
        vcf_files = sorted(
            p for p in _VCF_VEP_DIR.iterdir()
            if _CHR_PATTERN.match(p.name)
        )
        # Also include clinical/phenotype-associated VCFs (high-value)
        for name in [
            'homo_sapiens_clinically_associated.vcf.gz',
            'homo_sapiens_phenotype_associated.vcf.gz',
        ]:
            p = _VCF_VEP_DIR / name
            if p.exists():
                vcf_files.append(p)

        if not vcf_files:
            logger.warning(f"No VCF files found in {_VCF_VEP_DIR}")
            return

        t0 = time.time()
        total_found = 0

        for vcf_path in vcf_files:
            count = await asyncio.to_thread(
                self._scan_vcf_file, vcf_path, known_rsids,
            )
            total_found += count
            if count > 0:
                logger.info(f"  {vcf_path.name}: {count} variants cached")

        elapsed = time.time() - t0
        logger.info(
            f"Ensembl VEP file scan complete: {total_found} variants "
            f"from {len(vcf_files)} files in {elapsed:.1f}s"
        )

    def _scan_vcf_file(self, vcf_path: Path, known_rsids: Set[str]) -> int:
        """Scan a single VCF file, parse matching lines (runs in thread)."""
        from .ensembl_vep_etl import parse_vcf_line

        count = 0
        open_fn = gzip.open if str(vcf_path).endswith('.gz') else open

        with open_fn(vcf_path, 'rt', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if line.startswith('#'):
                    continue

                # Quick rsid pre-check before expensive full parse
                parts = line.split('\t', 4)
                if len(parts) < 3:
                    continue
                rsid = parts[2]
                if not rsid.startswith('rs') or rsid not in known_rsids:
                    continue

                # Full parse using the existing ETL parser
                parsed = parse_vcf_line(line, known_rsids)
                if parsed and parsed.get('rsid'):
                    vep_data = json.loads(parsed['vep_data'])
                    self._cache[parsed['rsid']] = vep_data
                    count += 1

        return count

    # ------------------------------------------------------------------
    # Lookups (same interface as the old DB-backed service)
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a single rsid."""
        if not await self.ensure_loaded():
            return None
        data = self._cache.get(rsid)
        if data:
            return data
        return {'found': False, 'source': 'ensembl'}

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by rsids from in-memory cache."""
        if not rsids:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for rsid in rsids:
            data = self._cache.get(rsid)
            if data:
                results[rsid] = data
        return results


# Singleton
_instance: Optional[EnsemblVepLocalService] = None


def get_ensembl_vep_service() -> EnsemblVepLocalService:
    global _instance
    if _instance is None:
        _instance = EnsemblVepLocalService()
    return _instance
