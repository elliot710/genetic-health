"""
gnomAD BigQuery service — on-demand lookups against the public gnomAD v3 dataset
in Google BigQuery (bigquery-public-data.gnomAD).

Schema notes (v3_genomes):
  - Per-chromosome tables: v3_genomes__chr{1..22,X,Y}
  - Columns: reference_name, start_position, reference_bases,
             alternate_bases (REPEATED RECORD), names (REPEATED STRING), AN, ...
  - alternate_bases contains: alt, AC, AF, nhomalt, population AFs, vep (REPEATED RECORD)
  - names = rsID array (e.g. ['rs7412'])
  - vep subfields: allele, Consequence, IMPACT, SYMBOL, Gene, Feature_type, Feature, BIOTYPE, EXON, INTRON

Requires:
  - google-cloud-bigquery Python package
  - GOOGLE_APPLICATION_CREDENTIALS env var (service account JSON)

Falls back gracefully if credentials/package not available.
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
from .datasource_utils import safe_float, safe_int

logger = logging.getLogger(__name__)

# Population ancestry mapping for gnomAD v3 BigQuery tables
_POP_FIELDS = {
    "afr": "African/African-American",
    "ami": "Amish",
    "amr": "Latino/Admixed American",
    "asj": "Ashkenazi Jewish",
    "eas": "East Asian",
    "fin": "Finnish",
    "nfe": "Non-Finnish European",
    "oth": "Other",
    "sas": "South Asian",
}

# BigQuery dataset version
_DATASET_VERSION = "v3_genomes"


class GnomadBigQueryService:
    """On-demand gnomAD lookups via Google BigQuery public dataset (v3 genomes)."""

    def __init__(self):
        self._client = None
        self._available: Optional[bool] = None

    async def is_available(self) -> bool:
        """Check if BigQuery credentials and package are available."""
        if self._available is not None:
            return self._available

        try:
            from google.cloud import bigquery
            self._client = await asyncio.to_thread(bigquery.Client)
            self._available = True
            logger.info("gnomAD BigQuery: client initialized successfully")
        except ImportError:
            logger.info("gnomAD BigQuery: google-cloud-bigquery not installed — BigQuery disabled")
            self._available = False
        except Exception as e:
            logger.info("gnomAD BigQuery: credentials not available (%s) — BigQuery disabled", e)
            self._available = False

        return self._available

    def _table(self, chrom: str) -> str:
        """Get the BigQuery table name for a chromosome."""
        return f"bigquery-public-data.gnomAD.{_DATASET_VERSION}__chr{chrom}"

    async def lookup_variant(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Look up a single variant from gnomAD BigQuery by position.

        Uses the gnomAD v3 genomes dataset with UNNEST on alternate_bases.
        Returns structured dict matching our gnomad_data format, or None on error."""
        if not await self.is_available():
            return None

        from google.cloud import bigquery

        chrom_clean = chrom.replace("chr", "")
        table = self._table(chrom_clean)

        query = f"""
        SELECT
            v.start_position,
            v.reference_bases,
            v.AN,
            v.names,
            ab.alt,
            ab.AC,
            ab.AF,
            ab.nhomalt,
            {self._pop_af_select("ab")},
            ab.vep
        FROM `{table}` v, UNNEST(v.alternate_bases) ab
        WHERE v.start_position = @pos
          AND v.reference_bases = @ref
          AND ab.alt = @alt
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("pos", "INT64", pos),
                bigquery.ScalarQueryParameter("ref", "STRING", ref),
                bigquery.ScalarQueryParameter("alt", "STRING", alt),
            ],
            maximum_bytes_billed=10 * 1024**3,
        )

        try:
            result = await asyncio.to_thread(
                self._client.query, query, job_config=job_config
            )
            rows = await asyncio.to_thread(lambda: list(result))

            if not rows:
                return {
                    "found": False,
                    "source": "gnomad_bigquery",
                    "chrom": chrom_clean,
                    "pos": pos,
                    "ref": ref,
                    "alt": alt,
                }

            return self._format_result(rows[0], chrom_clean)

        except Exception as e:
            logger.warning("gnomAD BigQuery lookup failed for %s:%d %s>%s: %s",
                           chrom_clean, pos, ref, alt, e)
            return None

    async def lookup_rsid(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a variant by rsID. Searches chromosome tables sequentially.

        Returns first match. Prefer lookup_variant when position is known."""
        if not await self.is_available():
            return None

        from google.cloud import bigquery

        chroms = [str(i) for i in range(1, 23)] + ['X', 'Y']

        for chrom in chroms:
            table = self._table(chrom)
            # Exclude ab.vep from rsid scans — full table scan + VEP RECORD
            # exceeds 10GB byte budget. VEP is only fetched on positional lookups.
            query = f"""
            SELECT
                v.start_position,
                v.reference_bases,
                v.AN,
                v.names,
                ab.alt,
                ab.AC,
                ab.AF,
                ab.nhomalt,
                {self._pop_af_select("ab")}
            FROM `{table}` v, UNNEST(v.alternate_bases) ab
            WHERE @rsid IN UNNEST(v.names)
            LIMIT 1
            """

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("rsid", "STRING", rsid),
                ],
                maximum_bytes_billed=15 * 1024**3,  # rsid scans need ~13GB
            )

            try:
                result = await asyncio.to_thread(
                    self._client.query, query, job_config=job_config
                )
                rows = await asyncio.to_thread(lambda: list(result))

                if rows:
                    data = self._format_result(rows[0], chrom)
                    data['rsid'] = rsid
                    return data
            except Exception:
                continue

        return {"found": False, "source": "gnomad_bigquery", "rsid": rsid}

    async def lookup_batch(
        self, variants: List[Dict[str, str]]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup multiple variants grouped by chromosome.

        Each variant dict should have: {chrom, pos, ref, alt, rsid(optional)}."""
        if not await self.is_available():
            return {}

        from google.cloud import bigquery

        by_chrom: Dict[str, List[Dict]] = {}
        for v in variants:
            c = v.get('chrom', '').replace('chr', '')
            by_chrom.setdefault(c, []).append(v)

        results: Dict[str, Optional[Dict[str, Any]]] = {}

        for chrom, chrom_variants in by_chrom.items():
            if not chrom:
                continue

            table = self._table(chrom)
            positions = [int(v['pos']) for v in chrom_variants]

            query = f"""
            SELECT
                v.start_position,
                v.reference_bases,
                v.AN,
                v.names,
                ab.alt,
                ab.AC,
                ab.AF,
                ab.nhomalt,
                {self._pop_af_select("ab")},
                ab.vep
            FROM `{table}` v, UNNEST(v.alternate_bases) ab
            WHERE v.start_position IN UNNEST(@positions)
            """

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("positions", "INT64", positions),
                ],
                maximum_bytes_billed=10 * 1024**3,
            )

            try:
                result = await asyncio.to_thread(
                    self._client.query, query, job_config=job_config
                )
                rows = await asyncio.to_thread(lambda: list(result))

                bq_map: Dict[str, Any] = {}
                for row in rows:
                    key = f"{chrom}-{row['start_position']}-{row['reference_bases']}-{row['alt']}"
                    bq_map[key] = row

                for v in chrom_variants:
                    key = f"{chrom}-{v['pos']}-{v['ref']}-{v['alt']}"
                    rsid = v.get('rsid', key)
                    if key in bq_map:
                        results[rsid] = self._format_result(bq_map[key], chrom)
                    else:
                        results[rsid] = {"found": False, "source": "gnomad_bigquery"}
            except Exception as e:
                logger.warning("gnomAD BigQuery batch for chr%s failed: %s", chrom, e)

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pop_af_select(alias: str) -> str:
        """Build the SELECT fragment for population allele frequencies."""
        cols = []
        for pop in _POP_FIELDS:
            cols.append(f"{alias}.AF_{pop}")
            cols.append(f"{alias}.nhomalt_{pop}")
        return ", ".join(cols)

    def _format_result(self, row: Any, chrom: str) -> Dict[str, Any]:
        """Format a BigQuery row (after UNNEST) into our standard gnomad_data dict."""
        def _get(key):
            if isinstance(row, dict):
                return row.get(key)
            return getattr(row, key, None)

        pos = safe_int(_get('start_position'))
        ref = _get('reference_bases') or ''
        alt = _get('alt') or ''

        # Population frequencies
        pop_freqs = {}
        for pop_code, pop_name in _POP_FIELDS.items():
            af_val = safe_float(_get(f'AF_{pop_code}'))
            if af_val is not None:
                pop_freqs[pop_code] = {
                    "name": pop_name,
                    "af": af_val,
                    "nhomalt": safe_int(_get(f'nhomalt_{pop_code}')),
                }

        # VEP annotations — nested REPEATED RECORD
        gene = None
        consequence = None
        impact = None
        vep_data = _get('vep')
        if vep_data:
            # vep_data is a list of dicts/objects from the REPEATED RECORD
            if isinstance(vep_data, (list, tuple)) and len(vep_data) > 0:
                first = vep_data[0]
                if isinstance(first, dict):
                    gene = first.get('SYMBOL')
                    consequence = first.get('Consequence')
                    impact = first.get('IMPACT')
                else:
                    gene = getattr(first, 'SYMBOL', None)
                    consequence = getattr(first, 'Consequence', None)
                    impact = getattr(first, 'IMPACT', None)

        # rsid from names array
        names = _get('names')
        rsid = None
        if names and isinstance(names, (list, tuple)):
            for n in names:
                if n and n.startswith('rs'):
                    rsid = n
                    break

        return {
            "found": True,
            "source": "gnomad_bigquery",
            "rsid": rsid,
            "chrom": chrom,
            "pos": pos,
            "ref": ref,
            "alt": alt,
            "variant_id": f"{chrom}-{pos}-{ref}-{alt}",
            "af": safe_float(_get('AF')),
            "ac": safe_int(_get('AC')),
            "an": safe_int(_get('AN')),
            "nhomalt": safe_int(_get('nhomalt')),
            "population_frequencies": pop_freqs,
            "gene": gene,
            "consequence": consequence,
            "impact": impact,
        }

    async def close(self):
        """Close the BigQuery client."""
        if self._client:
            try:
                await asyncio.to_thread(self._client.close)
            except Exception:
                pass
            self._client = None


# Singleton
_instance: Optional[GnomadBigQueryService] = None


def get_gnomad_bigquery_service() -> GnomadBigQueryService:
    global _instance
    if _instance is None:
        _instance = GnomadBigQueryService()
    return _instance


# ===========================================================================
# BigQuery backfill service (merged from gnomad_backfill.py)
# ===========================================================================

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
_backfill_stats: Optional[BackfillStats] = None
_backfill_running = False


class GnomadBackfillService:
    """Enriches local gnomad_variants with BigQuery population frequencies."""

    MAX_BYTES_BILLED = 10 * (1024 ** 3)  # 10 GB per query budget
    QUERY_DELAY_SECONDS = 0.5

    async def get_backfill_status(self) -> Dict[str, Any]:
        global _backfill_stats, _backfill_running

        async with async_session_factory() as session:
            total = await session.execute(
                select(func.count()).select_from(GnomadVariant)
            )
            total_count = total.scalar() or 0
            missing_af = await session.execute(
                select(func.count()).select_from(GnomadVariant).where(
                    GnomadVariant.af.is_(None)
                )
            )
            missing_count = missing_af.scalar() or 0
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
            "is_running": _backfill_running,
            "current_run": _backfill_stats.to_dict() if _backfill_stats else None,
            "bigquery_available": await self._check_bq_available(),
        }

    async def backfill(
        self,
        batch_size: int = 200,
        max_variants: int = 10000,
        chromosome: Optional[str] = None,
    ) -> Dict[str, Any]:
        global _backfill_stats, _backfill_running

        if _backfill_running:
            return {"error": "Backfill already in progress",
                    "current": _backfill_stats.to_dict() if _backfill_stats else None}

        if not await self._check_bq_available():
            return {"error": "BigQuery not available — set GOOGLE_APPLICATION_CREDENTIALS"}

        _backfill_running = True
        stats = BackfillStats(status="running", chromosome=chromosome)
        _backfill_stats = stats
        start = time.time()

        try:
            bq = get_gnomad_bigquery_service()
            candidates = await self._get_candidates(max_variants, chromosome)
            stats.total_candidates = len(candidates)

            if not candidates:
                stats.status = "completed"
                stats.elapsed_seconds = time.time() - start
                return stats.to_dict()

            by_chrom: Dict[str, List] = {}
            for v in candidates:
                by_chrom.setdefault(v.chrom, []).append(v)

            for chrom, chrom_variants in by_chrom.items():
                for i in range(0, len(chrom_variants), batch_size):
                    batch = chrom_variants[i:i + batch_size]
                    await self._process_batch(bq, chrom, batch, stats)
                    await asyncio.sleep(self.QUERY_DELAY_SECONDS)
                    stats.elapsed_seconds = time.time() - start

            stats.status = "completed"
            stats.elapsed_seconds = time.time() - start
            logging.getLogger(__name__).info(
                "Backfill completed: %d processed, %d enriched, %d not found, %d errors in %.1fs",
                stats.processed, stats.enriched, stats.not_found, stats.errors, stats.elapsed_seconds,
            )
            return stats.to_dict()

        except Exception as e:
            stats.status = f"error: {e}"
            stats.elapsed_seconds = time.time() - start
            logging.getLogger(__name__).error("Backfill failed: %s", e, exc_info=True)
            return stats.to_dict()
        finally:
            _backfill_running = False

    async def _get_candidates(self, limit: int, chromosome: Optional[str] = None) -> List:
        async with async_session_factory() as session:
            q = select(GnomadVariant).where(GnomadVariant.af.is_(None))
            if chromosome:
                q = q.where(GnomadVariant.chrom == chromosome.replace("chr", ""))
            q = q.limit(limit)
            result = await session.execute(q)
            return list(result.scalars().all())

    async def _process_batch(self, bq, chrom: str, batch: List, stats: BackfillStats):
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
            result = await asyncio.to_thread(bq._client.query, query, job_config=job_config)
            rows = await asyncio.to_thread(lambda: list(result))

            bq_map: Dict[str, Any] = {}
            for row in rows:
                key = f"{row['pos']}-{row['ref']}-{row['alt']}"
                bq_map[key] = row

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
                                af=safe_float(bq_row.get('af')),
                                ac=safe_int(bq_row.get('ac')),
                                an=safe_int(bq_row.get('an')),
                                nhomalt=safe_int(bq_row.get('nhomalt')),
                                af_afr=safe_float(bq_row.get('AF_afr')),
                                af_ami=safe_float(bq_row.get('AF_ami')),
                                af_amr=safe_float(bq_row.get('AF_amr')),
                                af_asj=safe_float(bq_row.get('AF_asj')),
                                af_eas=safe_float(bq_row.get('AF_eas')),
                                af_fin=safe_float(bq_row.get('AF_fin')),
                                af_nfe=safe_float(bq_row.get('AF_nfe')),
                                af_sas=safe_float(bq_row.get('AF_sas')),
                            )
                        )
                        stats.enriched += 1
                    else:
                        stats.not_found += 1

                await session.commit()

        except Exception as e:
            logging.getLogger(__name__).warning(
                "BigQuery batch for chr%s failed: %s", chrom, e)
            stats.errors += len(batch)
            stats.processed += len(batch)

    @staticmethod
    async def _check_bq_available() -> bool:
        try:
            bq = get_gnomad_bigquery_service()
            return await bq.is_available()
        except Exception:
            return False
