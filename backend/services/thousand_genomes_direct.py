"""
1000 Genomes Phase 3 direct file reader — SQLite cache from VCF.

When the thousand_genomes_variants PostgreSQL table is empty (ETL not run yet),
this service builds a lightweight SQLite cache directly from the local
1000GENOMES-phase_3.vcf.gz file, storing only variants whose rsid exists in
genetic_markers.

File notes:
  • Uses a CSI index (not TBI) → tabix random-access via pysam.TabixFile is
    not available.  For cold-cache building we stream the gzip file linearly.
  • For position lookups after cache build we use pysam.VariantFile which
    supports both .csi and .tbi indexes.

Cache pattern (same as gnomad_cache / ensembl_vep_local):
  Cold start  : stream VCF, insert known rsids into SQLite (~10–30 min for 1.5 GB)
  Warm restart : fingerprint check → open SQLite in <1s
  Position    : pysam.VariantFile.fetch(contig, start, stop)

Usage (via thousand_genomes_local.py fallback — not called directly):
    svc = get_thousand_genomes_direct_service()
    await svc.ensure_loaded()
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

from ..db.database import async_session_factory
from ..db.datasource_models import ThousandGenomesRecord
from ..db.models import GeneticMarker

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.environ.get(
    "TKG_DATA_DIR",
    "/app/data_sources/1000G",
))
_CACHE_DIR = _DATA_DIR / ".tkg_cache"
_SQLITE_FILE = _CACHE_DIR / "tkg_direct.db"
_META_FILE = _CACHE_DIR / "tkg_direct_meta.json"

_BATCH_SIZE = 5_000

_POP_NAMES = {
    "afr": "African",
    "amr": "Admixed American",
    "eas": "East Asian",
    "eur": "European",
    "sas": "South Asian",
}


class ThousandGenomesDirectService:
    """SQLite-backed 1000 Genomes lookup built from local VCF.

    Activated when the thousand_genomes_variants PG table is empty.
    """

    def __init__(self):
        self._db: Optional[sqlite3.Connection] = None
        self._variant_count: int = 0
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._db is not None

    @property
    def variant_count(self) -> int:
        return self._variant_count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ensure_loaded(self) -> bool:
        if self._loaded:
            return self._db is not None
        async with self._lock:
            if self._loaded:
                return self._db is not None
            try:
                await self._load_cache()
            except Exception as e:
                logger.error("1000G direct cache failed: %s", e, exc_info=True)
            self._loaded = True
        return self._db is not None

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not await self.ensure_loaded():
            return None
        return await asyncio.to_thread(self._lookup_one, rsid)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not rsids:
            return {}
        if not await self.ensure_loaded():
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, rsids)

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

    # ------------------------------------------------------------------
    # SQLite operations
    # ------------------------------------------------------------------

    def _lookup_one(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not self._db:
            return None
        row = self._db.execute(
            "SELECT data FROM tkg_data WHERE rsid = ?", (rsid,)
        ).fetchone()
        if row:
            return json.loads(zlib.decompress(row[0]))
        return None

    def _lookup_batch_sync(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not self._db:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for start in range(0, len(rsids), 500):
            chunk = rsids[start:start + 500]
            placeholders = ",".join("?" * len(chunk))
            rows = self._db.execute(
                f"SELECT rsid, data FROM tkg_data WHERE rsid IN ({placeholders})",
                chunk,
            ).fetchall()
            for rsid, blob in rows:
                results[rsid] = json.loads(zlib.decompress(blob))
        return results

    # ------------------------------------------------------------------
    # Cache build
    # ------------------------------------------------------------------

    async def _load_cache(self):
        vcf_path = self._find_vcf()
        if not vcf_path:
            logger.warning("1000G direct: no VCF file found in %s", _DATA_DIR)
            return

        marker_fp = await self._get_marker_fingerprint()
        file_fp = self._get_file_fingerprint(vcf_path)

        if self._is_cache_valid(marker_fp, file_fp):
            self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
            row = self._db.execute("SELECT COUNT(*) FROM tkg_data").fetchone()
            self._variant_count = row[0] if row else 0
            logger.info("1000G direct: opened cache with %d variants", self._variant_count)
            return

        logger.info("1000G direct: building cache from %s ...", vcf_path.name)
        known_rsids = await self._load_known_rsids()
        if not known_rsids:
            logger.warning("1000G direct: no rsids in genetic_markers — skipping build")
            return

        count = await asyncio.to_thread(self._scan_vcf_to_sqlite, vcf_path, known_rsids)
        self._save_meta(marker_fp, file_fp, count)
        self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
        self._variant_count = count
        logger.info("1000G direct cache built: %d variants", count)

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

    # ------------------------------------------------------------------
    # Position lookup via pysam.VariantFile (supports CSI index)
    # ------------------------------------------------------------------

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

        # pysam.VariantFile uses bcftools/htslib which supports .csi
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
                        # Parse the record into our model
                        info = dict(rec.info)
                        rsid = rec.id if rec.id and rec.id != "." else None
                        af_field = _get_af(info, "AFR"), _get_af(info, "AMR"), _get_af(info, "EAS"), _get_af(info, "EUR"), _get_af(info, "SAS")
                        tkg_rec = ThousandGenomesRecord(
                            chrom=chrom_clean,
                            pos=pos,
                            ref=rec.ref,
                            alt=allele,
                            rsid=rsid,
                            variant_type=_clean_info_str(info.get("TSA")),
                            minor_allele=_clean_info_str(info.get("MA")),
                            maf=_safe_af(info.get("MAF")),
                            mac=_safe_int_info(info.get("MAC")),
                            ancestral_allele=_clean_info_str(info.get("AA")),
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    async def _load_known_rsids(self) -> set:
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticMarker.rsid).where(GeneticMarker.rsid.isnot(None))
            )
            return {row[0] for row in result.all()}

    async def _get_marker_fingerprint(self) -> str:
        async with async_session_factory() as session:
            result = await session.execute(select(func.count(GeneticMarker.id)))
            count = result.scalar() or 0
        return str(count)

    def _get_file_fingerprint(self, vcf_path: Path) -> str:
        try:
            return f"{vcf_path.name}:{vcf_path.stat().st_size}"
        except OSError:
            return vcf_path.name

    def _is_cache_valid(self, marker_fp: str, file_fp: str) -> bool:
        if not _SQLITE_FILE.exists() or not _META_FILE.exists():
            return False
        try:
            meta = json.loads(_META_FILE.read_text())
            return (
                meta.get("marker_fingerprint") == marker_fp
                and meta.get("file_fingerprint") == file_fp
            )
        except Exception:
            return False

    def _save_meta(self, marker_fp: str, file_fp: str, count: int):
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        meta = {
            "marker_fingerprint": marker_fp,
            "file_fingerprint": file_fp,
            "variant_count": count,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _META_FILE.write_text(json.dumps(meta, indent=2))

    @staticmethod
    def _open_db(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-16384")
        return conn


# ---------------------------------------------------------------------------
# VCF parsing helpers (sync, used from thread)
# ---------------------------------------------------------------------------

def _parse_vcf_line(parts: List[str]) -> Optional[ThousandGenomesRecord]:
    """Parse a split VCF line into ThousandGenomesRecord.

    Handles multi-allelic ALT by taking the first ALT allele (the one with rsid).
    """
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

    # Take first alt allele (these records are usually split)
    alt = alt_str.split(",")[0]

    info = _parse_info_field(info_str)

    return ThousandGenomesRecord(
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        rsid=rsid,
        variant_type=_clean_info_str(info.get("TSA")),
        minor_allele=_clean_info_str(info.get("MA")),
        maf=_safe_af(info.get("MAF")),
        mac=_safe_int_info(info.get("MAC")),
        ancestral_allele=_clean_info_str(info.get("AA")),
        af_afr=_get_af(info, "AFR"),
        af_amr=_get_af(info, "AMR"),
        af_eas=_get_af(info, "EAS"),
        af_eur=_get_af(info, "EUR"),
        af_sas=_get_af(info, "SAS"),
    )


def _parse_info_field(info_str: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for token in info_str.split(";"):
        if "=" in token:
            k, _, v = token.partition("=")
            result[k.strip()] = v.strip()
    return result


def _get_af(info: Dict, key: str) -> Optional[float]:
    """Extract allele frequency for a population (Number=A — first value)."""
    val = info.get(key)
    if val is None:
        return None
    # Number=A: may be comma-separated list; take first
    first = val.split(",")[0].strip()
    return _safe_af(first)


def _safe_af(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        import math
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int_info(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _clean_info_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s in (".", "NA", "", "-") else s


# Singleton
_instance: Optional[ThousandGenomesDirectService] = None


def get_thousand_genomes_direct_service() -> ThousandGenomesDirectService:
    global _instance
    if _instance is None:
        _instance = ThousandGenomesDirectService()
    return _instance
