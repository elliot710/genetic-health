"""
1000 Genomes Phase 3 lookup service — PostgreSQL-backed with direct VCF fallback.

Looks up variants in the local thousand_genomes_variants table (populated by ETL).
Falls back to a SQLite cache built from the local 1000GENOMES-phase_3.vcf.gz when
the PG table is empty.

Provides per-superpopulation allele frequencies (AFR, AMR, EAS, EUR, SAS).

Usage:
    svc = get_thousand_genomes_service()
    result = await svc.lookup("rs1234")
    results = await svc.lookup_batch(["rs1234", "rs5678"])
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.datasource_models import ThousandGenomesRecord
from ..db.models import ThousandGenomesVariant
from .datasource_utils import (
    load_known_rsids, get_marker_fingerprint, get_file_fingerprint,
    is_cache_valid, save_cache_meta, open_cache_db, parse_vcf_info,
    safe_float, safe_int, clean_str,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Direct-cache constants (ThousandGenomesDirectService)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(os.environ.get(
    "TKG_DATA_DIR",
    "/app/data_sources/1000G",
))
_CACHE_DIR = _DATA_DIR / ".tkg_cache"
_SQLITE_FILE = _CACHE_DIR / "tkg_direct.db"
_META_FILE = _CACHE_DIR / "tkg_direct_meta.json"

_BATCH_SIZE = 5_000

# Superpopulation code → human-readable name
_POP_NAMES = {
    "afr": "African",
    "amr": "Admixed American",
    "eas": "East Asian",
    "eur": "European",
    "sas": "South Asian",
}


class ThousandGenomesDirectService:
    """SQLite-backed 1000 Genomes lookup built from local VCF.

    On first load the entire SQLite cache is decompressed into an in-memory dict
    so that bulk lookups during analysis become pure O(1) dict access with no
    per-query DB round-trips or zlib decompressions.
    """

    def __init__(self):
        self._db: Optional[sqlite3.Connection] = None
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._variant_count: int = 0
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded and bool(self._memory)

    @property
    def variant_count(self) -> int:
        return self._variant_count

    async def ensure_loaded(self) -> bool:
        if self._loaded:
            return bool(self._memory)
        async with self._lock:
            if self._loaded:
                return bool(self._memory)
            try:
                await self._load_cache()
            except Exception as e:
                logger.error("1000G direct cache failed: %s", e, exc_info=True)
            self._loaded = True
        return bool(self._memory)

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not await self.ensure_loaded():
            return None
        return self._memory.get(rsid)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not rsids:
            return {}
        if not await self.ensure_loaded():
            return {}
        # Run dict lookups in a thread to avoid blocking the event loop for
        # large batches (600K+ items would stall the worker for ~100ms).
        mem = self._memory
        return await asyncio.to_thread(lambda: {r: mem.get(r) for r in rsids})

    async def lookup_by_position(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Position-based lookup using pysam.VariantFile (supports CSI index)."""
        vcf_path = self._find_vcf()
        if not vcf_path:
            return None
        return await asyncio.to_thread(
            self._variant_file_lookup, vcf_path, chrom, pos, ref, alt
        )

    async def _load_cache(self):
        vcf_path = self._find_vcf()
        if not vcf_path:
            logger.warning("1000G direct: no VCF file found in %s", _DATA_DIR)
            return

        marker_fp = await get_marker_fingerprint()
        file_fp = get_file_fingerprint(vcf_path)

        if is_cache_valid(_SQLITE_FILE, _META_FILE, marker_fp, file_fp):
            self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE)
        else:
            logger.info("1000G direct: building cache from %s ...", vcf_path.name)
            known_rsids = await load_known_rsids()
            if not known_rsids:
                logger.warning("1000G direct: no rsids in genetic_markers — skipping build")
                return

            count = await asyncio.to_thread(self._scan_vcf_to_sqlite, vcf_path, known_rsids)
            save_cache_meta(_META_FILE, marker_fp, file_fp, count)
            self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE)

        # Preload entire SQLite into memory for O(1) bulk lookups during analysis
        logger.info("1000G direct: preloading SQLite into memory...")
        t0 = time.time()
        self._memory = await asyncio.to_thread(self._preload_memory)
        self._variant_count = len(self._memory)
        logger.info(
            "1000G direct: preloaded %d variants into memory (%.1fs)",
            self._variant_count, time.time() - t0,
        )

    def _preload_memory(self) -> Dict[str, Dict[str, Any]]:
        """Load entire SQLite into an in-memory dict.  Called once at startup."""
        if not self._db:
            return {}
        rows = self._db.execute("SELECT rsid, data FROM tkg_data").fetchall()
        return {rsid: json.loads(zlib.decompress(blob)) for rsid, blob in rows}

    def _scan_vcf_to_sqlite(self, vcf_path: Path, known_rsids: set) -> int:
        """Stream-scan the 1000G VCF, store known rsid entries in SQLite."""
        tmp = _SQLITE_FILE.with_suffix(".tmp")
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            tmp.unlink()

        conn = sqlite3.connect(str(tmp), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("""
            CREATE TABLE tkg_data (
                rsid TEXT PRIMARY KEY,
                data BLOB NOT NULL
            )
        """)

        count = 0
        batch: list = []
        t0 = time.time()
        lines_scanned = 0

        with gzip.open(str(vcf_path), "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue

                lines_scanned += 1
                if lines_scanned % 2_000_000 == 0:
                    elapsed = time.time() - t0
                    print(
                        f"[1000G direct] {lines_scanned:,} lines scanned, "
                        f"{count} hits so far ({elapsed:.0f}s)",
                        flush=True,
                    )

                parts = line.rstrip("\n").split("\t", 8)
                if len(parts) < 8:
                    continue

                rsid = parts[2] if parts[2] != "." else None
                if not rsid or rsid not in known_rsids:
                    continue

                try:
                    rec = _parse_vcf_line(parts)
                except Exception:
                    continue

                if rec is None:
                    continue

                ann = rec.to_annotation()
                raw = json.dumps(ann).encode("utf-8")
                blob = zlib.compress(raw, level=1)
                batch.append((rsid, blob))
                count += 1

                if len(batch) >= _BATCH_SIZE:
                    conn.executemany(
                        "INSERT OR REPLACE INTO tkg_data (rsid, data) VALUES (?, ?)",
                        batch,
                    )
                    conn.commit()
                    batch.clear()

        if batch:
            conn.executemany(
                "INSERT OR REPLACE INTO tkg_data (rsid, data) VALUES (?, ?)",
                batch,
            )
            conn.commit()

        elapsed = time.time() - t0
        print(
            f"[1000G direct] Scanned {lines_scanned:,} lines: {count} rsids cached in {elapsed:.1f}s",
            flush=True,
        )

        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        for suffix in ["-wal", "-shm"]:
            f = tmp.with_name(tmp.name + suffix)
            if f.exists():
                f.unlink()
        if _SQLITE_FILE.exists():
            _SQLITE_FILE.unlink()
        tmp.rename(_SQLITE_FILE)
        return count

    def _variant_file_lookup(
        self, vcf_path: Path, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        try:
            import pysam
        except ImportError:
            logger.debug("pysam not available for 1000G position lookup")
            return None

        chrom_clean = chrom.replace("chr", "")
        ref_upper = ref.upper()
        alt_upper = alt.upper()

        try:
            vcf = pysam.VariantFile(str(vcf_path))
        except Exception as e:
            logger.debug("1000G VariantFile open failed: %s", e)
            return None

        try:
            for rec in vcf.fetch(chrom_clean, pos - 1, pos):
                if rec.ref.upper() != ref_upper:
                    continue
                for allele in rec.alts or []:
                    if allele.upper() == alt_upper:
                        info = dict(rec.info)
                        rsid = rec.id if rec.id and rec.id != "." else None
                        af_field = (
                            _get_af(info, "AFR"), _get_af(info, "AMR"),
                            _get_af(info, "EAS"), _get_af(info, "EUR"), _get_af(info, "SAS"),
                        )
                        tkg_rec = ThousandGenomesRecord(
                            chrom=chrom_clean,
                            pos=pos,
                            ref=rec.ref,
                            alt=allele,
                            rsid=rsid,
                            variant_type=clean_str(info.get("TSA")),
                            minor_allele=clean_str(info.get("MA")),
                            maf=safe_float(info.get("MAF")),
                            mac=safe_int(info.get("MAC")),
                            ancestral_allele=clean_str(info.get("AA")),
                            af_afr=af_field[0],
                            af_amr=af_field[1],
                            af_eas=af_field[2],
                            af_eur=af_field[3],
                            af_sas=af_field[4],
                        )
                        return tkg_rec.to_annotation()
        except ValueError:
            pass  # contig not in file
        except Exception as e:
            logger.debug("1000G VariantFile fetch error: %s", e)
        finally:
            vcf.close()

        return None

    def _find_vcf(self) -> Optional[Path]:
        patterns = [
            "1000GENOMES-phase_3.vcf.gz",
            "1000GENOMES*.vcf.gz",
            "*1000genomes*.vcf.gz",
        ]
        for pat in patterns:
            for p in sorted(_DATA_DIR.glob(pat)):
                return p
        return None


# ---------------------------------------------------------------------------
# VCF parsing helpers
# ---------------------------------------------------------------------------

def _parse_vcf_line(parts: List[str]) -> Optional[ThousandGenomesRecord]:
    """Parse a split VCF line into ThousandGenomesRecord."""
    chrom = parts[0].replace("chr", "")
    try:
        pos = int(parts[1])
    except (ValueError, TypeError):
        return None

    rsid = parts[2] if parts[2] != "." else None
    ref = parts[3]
    alt_str = parts[4]
    info_str = parts[7] if len(parts) > 7 else ""

    if not ref or not alt_str or alt_str == ".":
        return None

    alt = alt_str.split(",")[0]
    info = parse_vcf_info(info_str)

    return ThousandGenomesRecord(
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        rsid=rsid,
        variant_type=clean_str(info.get("TSA")),
        minor_allele=clean_str(info.get("MA")),
        maf=safe_float(info.get("MAF")),
        mac=safe_int(info.get("MAC")),
        ancestral_allele=clean_str(info.get("AA")),
        af_afr=_get_af(info, "AFR"),
        af_amr=_get_af(info, "AMR"),
        af_eas=_get_af(info, "EAS"),
        af_eur=_get_af(info, "EUR"),
        af_sas=_get_af(info, "SAS"),
    )


def _get_af(info: Dict, key: str) -> Optional[float]:
    """Extract allele frequency for a population (Number=A — first value)."""
    val = info.get(key)
    if val is None:
        return None
    first = val.split(",")[0].strip()
    return safe_float(first)


# Singleton for direct service
_direct_instance: Optional[ThousandGenomesDirectService] = None


def get_thousand_genomes_direct_service() -> ThousandGenomesDirectService:
    global _direct_instance
    if _direct_instance is None:
        _direct_instance = ThousandGenomesDirectService()
    return _direct_instance


# ---------------------------------------------------------------------------


class ThousandGenomesLocalService:
    """PostgreSQL-backed 1000 Genomes Phase 3 lookup."""

    def __init__(self):
        self._variant_count: Optional[int] = None
        self._available: Optional[bool] = None
        self._direct = None  # ThousandGenomesDirectService fallback when PG is empty

    @property
    def is_loaded(self) -> bool:
        return self._variant_count is not None and self._variant_count > 0

    @property
    def variant_count(self) -> int:
        return self._variant_count or 0

    async def ensure_loaded(self) -> bool:
        """Check that the thousand_genomes_variants table has data.
        Falls back to direct file cache when PG is empty.
        """
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
                logger.warning(
                    "1000G PG: table empty — trying direct file cache"
                )
                direct = get_thousand_genomes_direct_service()
                ok = await direct.ensure_loaded()
                if ok:
                    self._direct = direct
                    self._variant_count = direct.variant_count
                    self._available = True
                    logger.info(
                        "1000G direct cache: %d variants available",
                        direct.variant_count,
                    )
            return self._available
        except Exception as e:
            logger.warning("1000G PG check failed: %s", e)
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Core lookups
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a variant by rsID. Tries PG first, then direct cache."""
        direct = self._direct
        # If we only have the direct cache (PG empty), skip PG
        if direct and not (self._variant_count and self._variant_count > direct.variant_count):
            result = await direct.lookup(rsid)
            if result and result.get("found"):
                return result
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
        batch_size = 500
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
                    await asyncio.sleep(0.05)
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

                if batch_num % 50 == 0 or batch_num == total_batches:
                    elapsed = _time.monotonic() - t0
                    rate = (i + len(chunk)) / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"  1000G batch {batch_num}/{total_batches}: "
                        f"{i + len(chunk)}/{total} queried, {found_count} found "
                        f"({rate:.0f} rsids/s, {elapsed:.1f}s elapsed)"
                    )

        elapsed = _time.monotonic() - t0
        logger.info(f"  1000G complete: {found_count}/{total} found in {elapsed:.1f}s")

        # If PG returned nothing, fill from direct-file cache
        direct = self._direct
        if direct and found_count == 0:
            missed = [r for r, v in results.items() if v is None]
            if missed:
                direct_results = await direct.lookup_batch(missed)
                for rsid_key, val in direct_results.items():
                    if val and val.get("found"):
                        results[rsid_key] = val
                        found_count += 1
                logger.info("  1000G direct fallback: %d/%d found", found_count, len(missed))

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

        # Compute global AF as simple mean of available population AFs
        pop_af_vals = [v["af"] for v in pop_freqs.values() if v.get("af") is not None]
        global_af = sum(pop_af_vals) / len(pop_af_vals) if pop_af_vals else row.maf

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
            "global_af": global_af,
        }


# Singleton
_instance: Optional[ThousandGenomesLocalService] = None


def get_thousand_genomes_service() -> ThousandGenomesLocalService:
    global _instance
    if _instance is None:
        _instance = ThousandGenomesLocalService()
    return _instance
