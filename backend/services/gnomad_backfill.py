"""
gnomAD BigQuery backfill service — enriches local gnomad_variants (CADD data)
with population allele frequencies from Google BigQuery.

The local ETL imports CADD-annotated data which has pathogenicity scores but
NO allele frequencies. BigQuery provides the population frequency data to
complement the local CADD scores.

Usage:
    svc = GnomadBackfillService()
    stats = await svc.backfill(batch_size=500, max_variants=10000, chromosome="1")
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, func

from ..db.database import async_session_factory
from ..db.models import GnomadVariant

logger = logging.getLogger(__name__)


@dataclass
class BackfillStats:
    """Tracks progress and results of a backfill run."""
    total_candidates: int = 0
    processed: int = 0
    enriched: int = 0
    not_found: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
    chromosome: Optional[str] = None
    status: str = "idle"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "processed": self.processed,
            "enriched": self.enriched,
            "not_found": self.not_found,
            "errors": self.errors,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "chromosome": self.chromosome,
            "status": self.status,
            "enrichment_rate": (
                f"{self.enriched / self.processed * 100:.1f}%"
                if self.processed > 0 else "0%"
            ),
        }


# Module-level backfill status (non-persistent, survives across requests)
_current_stats: Optional[BackfillStats] = None
_running = False


class GnomadBackfillService:
    """Enriches local gnomad_variants with BigQuery population frequencies."""

    # BigQuery cost control
    MAX_BYTES_BILLED = 10 * (1024 ** 3)  # 10 GB per query budget
    QUERY_DELAY_SECONDS = 0.5  # Delay between BQ queries to control cost

    async def get_backfill_status(self) -> Dict[str, Any]:
        """Get current backfill status + stats on un-enriched variants."""
        global _current_stats, _running

        async with async_session_factory() as session:
            # Count total variants
            total = await session.execute(
                select(func.count()).select_from(GnomadVariant)
            )
            total_count = total.scalar() or 0

            # Count variants missing allele frequency (need enrichment)
            missing_af = await session.execute(
                select(func.count()).select_from(GnomadVariant).where(
                    GnomadVariant.af.is_(None)
                )
            )
            missing_count = missing_af.scalar() or 0

            # Count per-chromosome breakdown of missing AFs
            chrom_counts = await session.execute(
                select(
                    GnomadVariant.chrom,
                    func.count().label('count')
                ).where(
                    GnomadVariant.af.is_(None)
                ).group_by(GnomadVariant.chrom).order_by(GnomadVariant.chrom)
            )
            by_chrom = {row.chrom: row.count for row in chrom_counts}

        return {
            "total_variants": total_count,
            "missing_af": missing_count,
            "enriched": total_count - missing_count,
            "enrichment_pct": (
                f"{(total_count - missing_count) / total_count * 100:.1f}%"
                if total_count > 0 else "0%"
            ),
            "by_chromosome": by_chrom,
            "is_running": _running,
            "current_run": _current_stats.to_dict() if _current_stats else None,
            "bigquery_available": await self._check_bq_available(),
        }

    async def backfill(
        self,
        batch_size: int = 200,
        max_variants: int = 10000,
        chromosome: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enrich local variants missing AF with BigQuery population data.

        Args:
            batch_size: Number of variants per BigQuery query (grouped by chromosome).
            max_variants: Maximum variants to process in this run.
            chromosome: If set, only backfill this chromosome.

        Returns:
            BackfillStats dict with results.
        """
        global _current_stats, _running

        if _running:
            return {"error": "Backfill already in progress", "current": _current_stats.to_dict() if _current_stats else None}

        # Check BigQuery availability
        if not await self._check_bq_available():
            return {"error": "BigQuery not available — set GOOGLE_APPLICATION_CREDENTIALS"}

        _running = True
        stats = BackfillStats(status="running", chromosome=chromosome)
        _current_stats = stats
        start = time.time()

        try:
            from .gnomad_bigquery import get_gnomad_bigquery_service
            bq = get_gnomad_bigquery_service()

            # Get candidate variants (missing AF)
            candidates = await self._get_candidates(max_variants, chromosome)
            stats.total_candidates = len(candidates)

            if not candidates:
                stats.status = "completed"
                stats.elapsed_seconds = time.time() - start
                return stats.to_dict()

            # Group by chromosome for efficient BQ queries
            by_chrom: Dict[str, List[GnomadVariant]] = {}
            for v in candidates:
                by_chrom.setdefault(v.chrom, []).append(v)

            # Process each chromosome
            for chrom, chrom_variants in by_chrom.items():
                for i in range(0, len(chrom_variants), batch_size):
                    batch = chrom_variants[i:i + batch_size]
                    await self._process_batch(bq, chrom, batch, stats)

                    # Rate limit between batches
                    await asyncio.sleep(self.QUERY_DELAY_SECONDS)

                    stats.elapsed_seconds = time.time() - start

            stats.status = "completed"
            stats.elapsed_seconds = time.time() - start
            logger.info(
                "Backfill completed: %d processed, %d enriched, %d not found, %d errors in %.1fs",
                stats.processed, stats.enriched, stats.not_found, stats.errors, stats.elapsed_seconds,
            )
            return stats.to_dict()

        except Exception as e:
            stats.status = f"error: {e}"
            stats.elapsed_seconds = time.time() - start
            logger.error("Backfill failed: %s", e, exc_info=True)
            return stats.to_dict()
        finally:
            _running = False

    async def _get_candidates(
        self, limit: int, chromosome: Optional[str] = None
    ) -> List[GnomadVariant]:
        """Get variants that need AF enrichment."""
        async with async_session_factory() as session:
            q = select(GnomadVariant).where(GnomadVariant.af.is_(None))
            if chromosome:
                q = q.where(GnomadVariant.chrom == chromosome.replace("chr", ""))
            q = q.limit(limit)

            result = await session.execute(q)
            return list(result.scalars().all())

    async def _process_batch(
        self,
        bq: Any,
        chrom: str,
        batch: List[GnomadVariant],
        stats: BackfillStats,
    ):
        """Process a batch of variants from the same chromosome via BigQuery.

        gnomAD v3 schema: alternate_bases is a REPEATED RECORD containing
        alt, AC, AF, nhomalt, per-population AFs.
        """
        from google.cloud import bigquery as bq_lib

        table = f"bigquery-public-data.gnomAD.v3_genomes__chr{chrom}"
        positions = [v.pos for v in batch]

        query = f"""
        SELECT
            v.start_position AS pos,
            v.reference_bases AS ref,
            v.AN AS an,
            ab.alt,
            ab.AC AS ac,
            ab.AF AS af,
            ab.nhomalt,
            ab.AF_afr, ab.AF_ami, ab.AF_amr, ab.AF_asj, ab.AF_eas,
            ab.AF_fin, ab.AF_nfe, ab.AF_oth, ab.AF_sas
        FROM `{table}` v, UNNEST(v.alternate_bases) ab
        WHERE v.start_position IN UNNEST(@positions)
        """

        job_config = bq_lib.QueryJobConfig(
            query_parameters=[
                bq_lib.ArrayQueryParameter("positions", "INT64", positions),
            ],
            maximum_bytes_billed=self.MAX_BYTES_BILLED,
        )

        try:
            result = await asyncio.to_thread(
                bq._client.query, query, job_config=job_config
            )
            rows = await asyncio.to_thread(lambda: list(result))

            # Index BQ results by pos-ref-alt
            bq_map: Dict[str, Any] = {}
            for row in rows:
                key = f"{row['pos']}-{row['ref']}-{row['alt']}"
                bq_map[key] = row

            # Update local variants
            async with async_session_factory() as session:
                for v in batch:
                    stats.processed += 1
                    key = f"{v.pos}-{v.ref}-{v.alt}"
                    bq_row = bq_map.get(key)

                    if bq_row:
                        await session.execute(
                            update(GnomadVariant)
                            .where(GnomadVariant.id == v.id)
                            .values(
                                af=self._safe_float(bq_row.get('af')),
                                ac=self._safe_int(bq_row.get('ac')),
                                an=self._safe_int(bq_row.get('an')),
                                nhomalt=self._safe_int(bq_row.get('nhomalt')),
                                af_afr=self._safe_float(bq_row.get('AF_afr')),
                                af_ami=self._safe_float(bq_row.get('AF_ami')),
                                af_amr=self._safe_float(bq_row.get('AF_amr')),
                                af_asj=self._safe_float(bq_row.get('AF_asj')),
                                af_eas=self._safe_float(bq_row.get('AF_eas')),
                                af_fin=self._safe_float(bq_row.get('AF_fin')),
                                af_nfe=self._safe_float(bq_row.get('AF_nfe')),
                                af_sas=self._safe_float(bq_row.get('AF_sas')),
                            )
                        )
                        stats.enriched += 1
                    else:
                        stats.not_found += 1

                await session.commit()

        except Exception as e:
            logger.warning("BigQuery batch for chr%s failed: %s", chrom, e)
            stats.errors += len(batch)
            stats.processed += len(batch)

    @staticmethod
    async def _check_bq_available() -> bool:
        try:
            from .gnomad_bigquery import get_gnomad_bigquery_service
            bq = get_gnomad_bigquery_service()
            return await bq.is_available()
        except Exception:
            return False

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None
