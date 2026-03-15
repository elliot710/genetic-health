"""
1000 Genomes Phase 3 ETL — import population allele frequencies from Ensembl VCF.

Parses the 1000GENOMES-phase_3.vcf.gz file distributed by Ensembl, which
contains per-superpopulation allele frequencies (AFR, AMR, EAS, EUR, SAS)
for variants observed in the 1000 Genomes Project Phase 3.

Uses streaming producer-consumer pattern with asyncpg COPY protocol,
matching the gnomAD/ClinVar ETL architecture.

Target table:
  thousand_genomes_variants — population allele frequencies

Run via admin endpoint: POST /api/admin/1kg-etl/import
"""

from __future__ import annotations

import asyncio
import asyncpg
import gzip
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
    "TKG_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "ensembl",
                 "homo_sapiens", "variation", "vcf_vep"),
))

_DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
).replace("postgresql+asyncpg://", "postgresql://")

VARIANT_COLUMNS = [
    "chrom", "pos", "ref", "alt", "rsid", "variant_type",
    "minor_allele", "maf", "mac", "ancestral_allele",
    "af_afr", "af_amr", "af_eas", "af_eur", "af_sas",
    "is_clinvar", "is_1000g",
    "data_source",
]


class ThousandGenomesETL:
    """Import 1000 Genomes Phase 3 VCF into PostgreSQL using streaming COPY."""

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else _DATA_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_full_import(self, *, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Run the full ETL pipeline. Returns summary stats."""
        total_start = time.time()
        stats: Dict[str, Any] = {"steps": []}

        def _report(step: str, count: int, elapsed: float):
            entry = {"step": step, "count": count, "elapsed_s": round(elapsed, 1)}
            stats["steps"].append(entry)
            if progress_callback:
                progress_callback(step, count, elapsed)
            logger.info("1000G ETL %s: %d rows in %.1fs", step, count, elapsed)

        # 1. Truncate
        t0 = time.time()
        await self._truncate_tables()
        _report("truncate", 0, time.time() - t0)

        # 2. Drop non-PK indexes
        t0 = time.time()
        await self._drop_indexes()
        _report("drop_indexes", 0, time.time() - t0)

        # 3. Import VCF file
        vcf_file = self._find_vcf_file()
        total_variants = 0
        if vcf_file:
            t0 = time.time()
            n = await self._stream_import(
                vcf_file, self._parse_vcf_chunks, "thousand_genomes_variants", VARIANT_COLUMNS,
            )
            total_variants = n
            _report(f"variants:{vcf_file.name}", n, time.time() - t0)
        else:
            logger.warning("No 1000 Genomes VCF file found in %s", self._data_dir)
            stats["error"] = f"No VCF file found in {self._data_dir}"

        # 4. Recreate indexes
        t0 = time.time()
        await self._create_indexes()
        _report("create_indexes", 0, time.time() - t0)

        # 5. ANALYZE
        t0 = time.time()
        await self._analyze_tables()
        _report("analyze", 0, time.time() - t0)

        counts = await self.get_import_status()
        stats["final_counts"] = counts
        stats["total_elapsed_s"] = round(time.time() - total_start, 1)
        logger.info("1000G ETL complete in %.1fs — %d variants", stats["total_elapsed_s"], total_variants)
        return stats

    def _find_vcf_file(self) -> Optional[Path]:
        """Find the 1000 Genomes VCF file."""
        patterns = [
            "1000GENOMES-phase_3.vcf.gz",
            "1000GENOMES*.vcf.gz",
            "*1000genomes*.vcf.gz",
        ]
        for pat in patterns:
            for p in sorted(self._data_dir.glob(pat)):
                return p
        return None

    # ------------------------------------------------------------------
    # Streaming producer-consumer import
    # ------------------------------------------------------------------

    async def _stream_import(self, fpath, parser_func, table_name, columns):
        """Stream-parse a file in a thread and COPY-insert each chunk."""
        q: queue.Queue = queue.Queue(maxsize=4)

        def _produce():
            try:
                for chunk in parser_func(fpath):
                    q.put(chunk)
            except Exception as exc:
                logger.error("Parser error for %s: %s", fpath, exc)
                q.put(exc)
            finally:
                q.put(None)  # sentinel

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
                    table_name, records=item, columns=columns,
                )
                total += len(item)
                if total % 500_000 < CHUNK_SIZE:
                    logger.info("  %s: %d rows inserted", table_name, total)
        finally:
            await conn.close()

        thread.join(timeout=10)
        return total

    # ------------------------------------------------------------------
    # VCF parser (sync generator yielding chunks of tuples)
    # ------------------------------------------------------------------

    def _parse_vcf_chunks(self, fpath: Path):
        """Yield chunks of tuples from the 1000 Genomes Phase 3 VCF.

        VCF INFO fields contain:
          AFR, AMR, EAS, EUR, SAS — population AFs (Number=A: one per ALT allele)
          MA — minor allele
          MAF — minor allele frequency
          MAC — minor allele count
          AA — ancestral allele
          TSA — type of sequence alteration
          Various evidence/clinical flags
        """
        chunk: list = []

        open_fn = gzip.open if str(fpath).endswith('.gz') else open

        with open_fn(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue

                parts = line.rstrip("\n").split("\t", 8)
                if len(parts) < 8:
                    continue

                chrom = parts[0].replace("chr", "")
                try:
                    pos = int(parts[1])
                except (ValueError, TypeError):
                    continue

                rsid = parts[2] if parts[2] != "." else None
                ref = parts[3]
                alt_str = parts[4]
                info_str = parts[7]

                if not ref or not alt_str or alt_str == ".":
                    continue

                # Parse INFO field
                info = self._parse_info(info_str)

                # Parse population AFs — Number=A means one value per ALT allele
                afr_vals = self._parse_af_field(info.get("AFR"))
                amr_vals = self._parse_af_field(info.get("AMR"))
                eas_vals = self._parse_af_field(info.get("EAS"))
                eur_vals = self._parse_af_field(info.get("EUR"))
                sas_vals = self._parse_af_field(info.get("SAS"))

                # Metadata
                minor_allele = info.get("MA")
                maf = self._safe_float(info.get("MAF"))
                mac = self._safe_int(info.get("MAC"))
                ancestral_allele = info.get("AA")
                variant_type = info.get("TSA")
                is_clinvar = "ClinVar_202502" in info or any(
                    k.startswith("ClinVar") for k in info
                )
                is_1000g = "E_1000G" in info

                # Emit one row per ALT allele
                alts = alt_str.split(",")
                for alt_idx, alt in enumerate(alts):
                    if not alt or alt == ".":
                        continue

                    row = (
                        chrom,
                        pos,
                        ref,
                        alt,
                        rsid,
                        variant_type,
                        minor_allele,
                        maf,
                        mac,
                        ancestral_allele,
                        self._get_af(afr_vals, alt_idx),
                        self._get_af(amr_vals, alt_idx),
                        self._get_af(eas_vals, alt_idx),
                        self._get_af(eur_vals, alt_idx),
                        self._get_af(sas_vals, alt_idx),
                        is_clinvar,
                        is_1000g,
                        "ensembl_vcf",
                    )
                    chunk.append(row)

                    if len(chunk) >= CHUNK_SIZE:
                        yield chunk
                        chunk = []

        if chunk:
            yield chunk

    @staticmethod
    def _parse_info(info_str: str) -> Dict[str, str]:
        """Parse VCF INFO field into a dict. Flags become key→key."""
        info: Dict[str, str] = {}
        for field in info_str.split(";"):
            if "=" in field:
                k, v = field.split("=", 1)
                info[k] = v
            else:
                info[field] = field  # Flag
        return info

    @staticmethod
    def _parse_af_field(val: Optional[str]) -> Optional[List[Optional[float]]]:
        """Parse a comma-separated AF field (Number=A: one per ALT)."""
        if not val:
            return None
        result = []
        for v in val.split(","):
            v = v.strip()
            if v and v not in (".", "NA", ""):
                try:
                    result.append(float(v))
                except (ValueError, TypeError):
                    result.append(None)
            else:
                result.append(None)
        return result

    @staticmethod
    def _get_af(vals: Optional[List[Optional[float]]], idx: int) -> Optional[float]:
        """Get AF for a specific ALT allele index."""
        if vals is None or idx >= len(vals):
            return None
        return vals[idx]

    @staticmethod
    def _safe_float(val: Optional[str]) -> Optional[float]:
        if not val or val in (".", "NA", ""):
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val: Optional[str]) -> Optional[int]:
        if not val or val in (".", "NA", ""):
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    _CUSTOM_INDEXES = [
        ("ix_1kg_rsid", "thousand_genomes_variants", "(rsid)"),
        ("ix_1kg_chrom_pos", "thousand_genomes_variants", "(chrom, pos)"),
        ("ix_1kg_chrom_pos_ref_alt", "thousand_genomes_variants", "(chrom, pos, ref, alt)"),
        ("ix_1kg_maf", "thousand_genomes_variants", "(maf)"),
    ]

    async def _drop_indexes(self):
        async with async_session_factory() as session:
            for name, _, _ in self._CUSTOM_INDEXES:
                await session.execute(text(f"DROP INDEX IF EXISTS {name}"))
            await session.commit()
        logger.info("Dropped 1000G indexes for bulk load")

    async def _create_indexes(self):
        async with async_session_factory() as session:
            for name, table, cols in self._CUSTOM_INDEXES:
                await session.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}"
                ))
            await session.commit()
        logger.info("Recreated 1000G indexes")

    # ------------------------------------------------------------------
    # Table management
    # ------------------------------------------------------------------

    async def _truncate_tables(self):
        async with async_session_factory() as session:
            await session.execute(text("TRUNCATE thousand_genomes_variants RESTART IDENTITY CASCADE"))
            await session.commit()
        logger.info("Truncated 1000G tables")

    async def _analyze_tables(self):
        async with async_session_factory() as session:
            await session.execute(text("ANALYZE thousand_genomes_variants"))
            await session.commit()

    # ------------------------------------------------------------------
    # Status / counts
    # ------------------------------------------------------------------

    async def get_import_status(self) -> Dict[str, Any]:
        """Return counts from 1000G table + file availability."""
        async with async_session_factory() as session:
            count = (await session.execute(
                text("SELECT count(*) FROM thousand_genomes_variants")
            )).scalar()

        vcf_file = self._find_vcf_file()
        return {
            "thousand_genomes_variants": count,
            "vcf_file": vcf_file.name if vcf_file else None,
            "data_dir": str(self._data_dir),
        }
