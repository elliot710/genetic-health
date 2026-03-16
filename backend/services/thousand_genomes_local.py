"""
1000 Genomes Phase 3 local lookup service — PostgreSQL-backed.

Looks up variants in the local thousand_genomes_variants table (populated by ETL).
Provides per-superpopulation allele frequencies (AFR, AMR, EAS, EUR, SAS).

Usage:
    svc = get_thousand_genomes_service()
    result = await svc.lookup("rs1234")
    results = await svc.lookup_batch(["rs1234", "rs5678"])
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.models import ThousandGenomesVariant

logger = logging.getLogger(__name__)

# Superpopulation code → human-readable name
_POP_NAMES = {
    "afr": "African",
    "amr": "Admixed American",
    "eas": "East Asian",
    "eur": "European",
    "sas": "South Asian",
}


class ThousandGenomesLocalService:
    """PostgreSQL-backed 1000 Genomes Phase 3 lookup."""

    def __init__(self):
        self._variant_count: Optional[int] = None
        self._available: Optional[bool] = None

    @property
    def is_loaded(self) -> bool:
        return self._variant_count is not None and self._variant_count > 0

    @property
    def variant_count(self) -> int:
        return self._variant_count or 0

    async def ensure_loaded(self) -> bool:
        """Check that the thousand_genomes_variants table has data."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(ThousandGenomesVariant)
                )
                self._variant_count = result.scalar() or 0

            self._available = self._variant_count > 0
            if self._available:
                logger.info("1000G PG: %d variants available", self._variant_count)
            else:
                logger.warning("1000G PG: table empty — run ETL import")
            return self._available
        except Exception as e:
            logger.warning("1000G PG check failed: %s", e)
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Core lookups
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a variant by rsID."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(ThousandGenomesVariant).where(ThousandGenomesVariant.rsid == rsid)
            )
            rows = result.scalars().all()

            if not rows:
                return {"found": False, "source": "1000genomes", "rsid": rsid}

            if len(rows) == 1:
                return self._format_variant(rows[0], rsid=rsid)
            else:
                # Multiple ALT alleles — return the one with highest MAF
                best = max(rows, key=lambda r: r.maf or 0)
                data = self._format_variant(best, rsid=rsid)
                data['other_alleles'] = [
                    {"alt": r.alt, "af_eur": r.af_eur, "maf": r.maf}
                    for r in rows if r.id != best.id
                ]
                return data

    async def lookup_by_position(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Look up by exact genomic coordinates."""
        chrom = chrom.replace("chr", "")
        async with async_session_factory() as session:
            result = await session.execute(
                select(ThousandGenomesVariant).where(
                    ThousandGenomesVariant.chrom == chrom,
                    ThousandGenomesVariant.pos == pos,
                    ThousandGenomesVariant.ref == ref,
                    ThousandGenomesVariant.alt == alt,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return {"found": False, "source": "1000genomes"}
            return self._format_variant(row)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by rsIDs using IN clause. Returns {rsid: result_or_none}."""
        if not rsids:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        batch_size = 2000
        total = len(rsids)
        total_batches = (total + batch_size - 1) // batch_size
        found_count = 0
        import time as _time
        t0 = _time.monotonic()
        async with async_session_factory() as session:
            for i in range(0, len(rsids), batch_size):
                chunk = rsids[i:i + batch_size]
                batch_num = i // batch_size + 1
                # Yield to event loop between chunks so HTTP handlers can run
                if i > 0:
                    await asyncio.sleep(0.01)
                result = await session.execute(
                    select(ThousandGenomesVariant).where(
                        ThousandGenomesVariant.rsid.in_(chunk)
                    )
                )
                rows = result.scalars().all()
                by_rsid: Dict[str, list] = {}
                for row in rows:
                    by_rsid.setdefault(row.rsid, []).append(row)
                for rsid_key in chunk:
                    row_list = by_rsid.get(rsid_key)
                    if not row_list:
                        results[rsid_key] = None
                    elif len(row_list) == 1:
                        results[rsid_key] = self._format_variant(row_list[0], rsid=rsid_key)
                        found_count += 1
                    else:
                        best = max(row_list, key=lambda r: r.maf or 0)
                        data = self._format_variant(best, rsid=rsid_key)
                        data['other_alleles'] = [
                            {"alt": r.alt, "af_eur": r.af_eur, "maf": r.maf}
                            for r in row_list if r.id != best.id
                        ]
                        results[rsid_key] = data
                        found_count += 1

                if batch_num % 10 == 0 or batch_num == total_batches:
                    elapsed = _time.monotonic() - t0
                    rate = (i + len(chunk)) / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"  1000G batch {batch_num}/{total_batches}: "
                        f"{i + len(chunk)}/{total} queried, {found_count} found "
                        f"({rate:.0f} rsids/s, {elapsed:.1f}s elapsed)"
                    )

        elapsed = _time.monotonic() - t0
        logger.info(f"  1000G complete: {found_count}/{total} found in {elapsed:.1f}s")
        return results

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_variant(self, row: ThousandGenomesVariant, rsid: Optional[str] = None) -> Dict[str, Any]:
        """Format a DB row into the standard thousand_genomes_data dict."""
        pop_freqs = {}
        for code, name in _POP_NAMES.items():
            val = getattr(row, f'af_{code}', None)
            if val is not None:
                pop_freqs[code] = {"name": name, "af": val}

        return {
            "found": True,
            "source": "1000genomes_local",
            "rsid": rsid or row.rsid,
            "chrom": row.chrom,
            "pos": row.pos,
            "ref": row.ref,
            "alt": row.alt,
            "variant_type": row.variant_type,
            "minor_allele": row.minor_allele,
            "maf": row.maf,
            "mac": row.mac,
            "ancestral_allele": row.ancestral_allele,
            "population_frequencies": pop_freqs,
        }


# Singleton
_instance: Optional[ThousandGenomesLocalService] = None


def get_thousand_genomes_service() -> ThousandGenomesLocalService:
    global _instance
    if _instance is None:
        _instance = ThousandGenomesLocalService()
    return _instance
