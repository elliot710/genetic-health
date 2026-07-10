"""
gnomAD v2.1.1 ETL — import exome population AFs from per-chromosome VCF files.

Parses the gnomad.exomes.r2.1.1.sites.{chrom}.vcf.bgz files (GRCh37),
extracting per-superpopulation allele frequencies and streaming them into
gnomad_v2_variants via asyncpg COPY protocol.

Target table:
  gnomad_v2_variants — population allele frequencies (GRCh37, exome)

Run via admin endpoint: POST /api/admin/gnomad-v2-etl/import
"""

from __future__ import annotations

import asyncio
import asyncpg
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text

from ..db.database import async_session_factory

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50_000

_DATA_DIR = Path(os.environ.get(
    "GNOMAD_V2_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "gnomad_v2"),
))

_DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
).replace("postgresql+asyncpg://", "postgresql://")

VARIANT_COLUMNS = [
    "chrom", "pos", "ref", "alt", "rsid", "af",
    "af_afr", "af_amr", "af_eas", "af_nfe", "af_sas",
    "af_fin", "af_asj", "ac", "an",
    "data_source",
]

# Population AF fields to extract from INFO
_SUPER_POPS = ["AFR", "AMR", "EAS", "NFE", "SAS"]
_OTHER_POPS = ["FIN", "ASJ"]


def _safe_float(val: str) -> Optional[float]:
    if not val or val in (".", "NA"):
        return None
    try:
        return float(val.split(",")[0])
    except (ValueError, TypeError):
        return None


def _safe_int(val: str) -> Optional[int]:
    if not val or val in (".", "NA"):
        return None
    try:
        return int(val.split(",")[0])
    except (ValueError, TypeError):
        return None


class GnomadV2ETL:
    """Import gnomAD v2.1.1 exome VCFs into PostgreSQL using streaming COPY."""

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else _DATA_DIR

    async def get_import_status(self) -> Dict[str, Any]:
        """Get current gnomAD v2 import status (row counts + file availability)."""
        async with async_session_factory() as session:
            total = (await session.execute(text("SELECT COUNT(*) FROM gnomad_v2_variants"))).scalar() or 0
            has_rsid = 0
            if total > 0:
                has_rsid = (await session.execute(
                    text("SELECT COUNT(*) FROM gnomad_v2_variants WHERE rsid IS NOT NULL")
                )).scalar() or 0

        vcf_files = self._find_vcf_files()
        return {
            "gnomad_v2_variants": total,
            "with_rsid": has_rsid,
            "vcf_files": [f.name for f in vcf_files],
            "vcf_file_count": len(vcf_files),
            "data_dir": str(self._data_dir),
        }

    async def run_full_import(self, *, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Run the full ETL pipeline. Returns summary stats."""
        total_start = time.time()
        stats: Dict[str, Any] = {"steps": []}

        def _report(step: str, count: int, elapsed: float):
            entry = {"step": step, "count": count, "elapsed_s": round(elapsed, 1)}
            stats["steps"].append(entry)
            if progress_callback:
                progress_callback(step, count, elapsed)
            logger.info("gnomAD v2 ETL %s: %d rows in %.1fs", step, count, elapsed)

        # 1. Truncate
        t0 = time.time()
        await self._truncate_table()
        _report("truncate", 0, time.time() - t0)

        # 2. Drop non-PK indexes
        t0 = time.time()
        await self._drop_indexes()
        _report("drop_indexes", 0, time.time() - t0)

        # 3. Import VCF files
        vcf_files = self._find_vcf_files()
        total_variants = 0
        for vcf_file in vcf_files:
            t0 = time.time()
            n = await self._stream_import(vcf_file)
            total_variants += n
            _report(f"variants:{vcf_file.name}", n, time.time() - t0)

        if not vcf_files:
            logger.warning("No gnomAD v2 VCF files found in %s", self._data_dir)
            stats["error"] = f"No VCF files found in {self._data_dir}"

        # 4. Recreate indexes
        t0 = time.time()
        await self._create_indexes()
        _report("create_indexes", 0, time.time() - t0)

        # 5. ANALYZE
        t0 = time.time()
        await self._analyze_table()
        _report("analyze", 0, time.time() - t0)

        counts = await self.get_import_status()
        stats["final_counts"] = counts
        stats["total_elapsed_s"] = round(time.time() - total_start, 1)
        logger.info("gnomAD v2 ETL complete in %.1fs — %d variants", stats["total_elapsed_s"], total_variants)
        return stats

    def _find_vcf_files(self) -> List[Path]:
        """Find all gnomAD v2 per-chromosome VCF files."""
        if not self._data_dir.exists():
            return []
        files = sorted(self._data_dir.glob("gnomad.exomes.r2.1.1.sites.*.vcf.bgz"))
        # Filter out empty files
        return [f for f in files if f.stat().st_size > 0]

    async def _truncate_table(self):
        async with async_session_factory() as session:
            await session.execute(text("TRUNCATE gnomad_v2_variants RESTART IDENTITY"))
            await session.commit()

    async def _drop_indexes(self):
        async with async_session_factory() as session:
            await session.execute(text("DROP INDEX IF EXISTS ix_gnomad_v2_rsid"))
            await session.execute(text("DROP INDEX IF EXISTS ix_gnomad_v2_chrom_pos"))
            await session.commit()

    async def _create_indexes(self):
        async with async_session_factory() as session:
            await session.execute(text("CREATE INDEX ix_gnomad_v2_rsid ON gnomad_v2_variants (rsid)"))
            await session.execute(text("CREATE INDEX ix_gnomad_v2_chrom_pos ON gnomad_v2_variants (chrom, pos)"))
            await session.commit()

    async def _analyze_table(self):
        conn = await asyncpg.connect(_DB_DSN)
        try:
            await conn.execute("ANALYZE gnomad_v2_variants")
        finally:
            await conn.close()

    async def _stream_import(self, vcf_path: Path) -> int:
        """Stream-parse a single VCF file and COPY-insert chunks."""
        q: queue.Queue = queue.Queue(maxsize=4)

        def _produce():
            try:
                for chunk in self._parse_vcf_chunks(vcf_path):
                    q.put(chunk)
            except Exception as exc:
                logger.error("Parser error for %s: %s", vcf_path.name, exc)
                q.put(exc)
            finally:
                q.put(None)

        thread = threading.Thread(target=_produce, daemon=True)
        thread.start()

        conn = await asyncpg.connect(_DB_DSN)
        total = 0
        try:
            while True:
                item = await asyncio.to_thread(q.get)
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                await conn.copy_records_to_table(
                    "gnomad_v2_variants", records=item, columns=VARIANT_COLUMNS,
                )
                total += len(item)
                if total % 500_000 < CHUNK_SIZE:
                    logger.info("  gnomad_v2_variants (%s): %d rows", vcf_path.name, total)
        finally:
            await conn.close()

        thread.join(timeout=10)
        return total

    def _parse_vcf_chunks(self, vcf_path: Path):
        """Yield chunks of tuples from a gnomAD v2 VCF file.

        INFO fields contain:
          AF_afr, AF_amr, AF_eas, AF_nfe, AF_sas — super-population AFs
          AF_fin, AF_asj — additional sub-populations
          AC, AN — total allele count/number
          AF — overall allele frequency
        """
        import pysam

        chunk: list = []
        tbx = pysam.TabixFile(str(vcf_path))

        try:
            for row in tbx.fetch():
                fields = row.split("\t", 8)
                if len(fields) < 8:
                    continue

                chrom = fields[0].replace("chr", "")
                try:
                    pos = int(fields[1])
                except (ValueError, TypeError):
                    continue

                rsid_raw = fields[2]
                rsid = None
                if rsid_raw and rsid_raw != ".":
                    # Take first rsid if multiple are semicolon-separated
                    parts = rsid_raw.split(";")
                    for p in parts:
                        if p.startswith("rs"):
                            rsid = p
                            break
                    if rsid is None:
                        rsid = parts[0]

                ref = fields[3]
                alt = fields[4]
                if not ref or not alt or alt == ".":
                    continue

                # For multi-allelic, take first ALT
                if "," in alt:
                    alt = alt.split(",")[0]

                info_str = fields[7]
                info = {}
                for kv in info_str.split(";"):
                    if "=" in kv:
                        k, _, v = kv.partition("=")
                        info[k] = v

                af = _safe_float(info.get("AF", ""))
                af_afr = _safe_float(info.get("AF_afr", ""))
                af_amr = _safe_float(info.get("AF_amr", ""))
                af_eas = _safe_float(info.get("AF_eas", ""))
                af_nfe = _safe_float(info.get("AF_nfe", ""))
                af_sas = _safe_float(info.get("AF_sas", ""))
                af_fin = _safe_float(info.get("AF_fin", ""))
                af_asj = _safe_float(info.get("AF_asj", ""))
                ac = _safe_int(info.get("AC", ""))
                an = _safe_int(info.get("AN", ""))

                chunk.append((
                    chrom, pos, ref, alt, rsid, af,
                    af_afr, af_amr, af_eas, af_nfe, af_sas,
                    af_fin, af_asj, ac, an,
                    "gnomad_v2_vcf",
                ))

                if len(chunk) >= CHUNK_SIZE:
                    yield chunk
                    chunk = []
        finally:
            tbx.close()

        if chunk:
            yield chunk
