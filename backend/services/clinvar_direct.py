"""
ClinVar direct file reader — SQLite cache from variant_summary.txt.gz.

When the clinvar_variants PostgreSQL table is empty (ETL not run), this
service builds a lightweight SQLite cache directly from the local
variant_summary.txt.gz file, keyed by rsid.

It follows the same cache-on-first-use pattern as ensembl_vep_local.py:
  • Cold start  : scan variant_summary.txt.gz, store rsid→JSON in SQLite.
                  Only rsids present in genetic_markers are stored.
  • Warm start  : fingerprint check → open existing SQLite in <1s.
  • Position lookup : uses pysam.TabixFile against clinvar.vcf.gz (.tbi).

Usage (via clinvar_local.py fallback layer — not called directly):
    svc = get_clinvar_direct_service()
    await svc.ensure_loaded()
    result = await svc.lookup("rs1234")
    results = await svc.lookup_batch(["rs1234", "rs5678"])
"""
from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import json
import logging
import os
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func

from ..db.database import async_session_factory
from ..db.datasource_models import ClinVarSummaryRecord, ClinVarVcfRecord, _parse_vcf_info
from ..db.models import GeneticMarker

logger = logging.getLogger(__name__)

_CLINVAR_DATA_DIR = Path(os.environ.get(
    "CLINVAR_DATA_DIR",
    "/app/data_sources/clinvar",
))
_CACHE_DIR = _CLINVAR_DATA_DIR / ".clinvar_cache"
_SQLITE_FILE = _CACHE_DIR / "clinvar_direct.db"
_META_FILE = _CACHE_DIR / "clinvar_direct_meta.json"

_BATCH_SIZE = 5_000


class ClinVarDirectService:
    """SQLite-backed ClinVar lookup built from variant_summary.txt.gz.

    Activated automatically when the clinvar_variants PG table is empty.
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
        """Open or build the SQLite cache (runs once)."""
        if self._loaded:
            return self._db is not None
        async with self._lock:
            if self._loaded:
                return self._db is not None
            try:
                await self._load_cache()
            except Exception as e:
                logger.error("ClinVar direct cache failed: %s", e, exc_info=True)
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
        """Position-based lookup via tabix against clinvar.vcf.gz."""
        vcf_path = self._find_vcf()
        tbi_path = Path(str(vcf_path) + ".tbi") if vcf_path else None
        if not vcf_path or not vcf_path.exists() or not (tbi_path and tbi_path.exists()):
            return None
        return await asyncio.to_thread(
            self._tabix_lookup, vcf_path, chrom, pos, ref, alt
        )

    # ------------------------------------------------------------------
    # SQLite operations
    # ------------------------------------------------------------------

    def _lookup_one(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not self._db:
            return None
        row = self._db.execute(
            "SELECT data FROM clinvar_data WHERE rsid = ?", (rsid,)
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
                f"SELECT rsid, data FROM clinvar_data WHERE rsid IN ({placeholders})",
                chunk,
            ).fetchall()
            for rsid, blob in rows:
                results[rsid] = json.loads(zlib.decompress(blob))
        return results

    # ------------------------------------------------------------------
    # Cache build
    # ------------------------------------------------------------------

    async def _load_cache(self):
        tsv_path = self._find_tsv()
        if not tsv_path:
            logger.warning(
                "ClinVar direct: variant_summary.txt.gz not found in %s", _CLINVAR_DATA_DIR
            )
            return

        marker_fp = await self._get_marker_fingerprint()
        file_fp = self._get_file_fingerprint(tsv_path)

        if self._is_cache_valid(marker_fp, file_fp):
            self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
            row = self._db.execute("SELECT COUNT(*) FROM clinvar_data").fetchone()
            self._variant_count = row[0] if row else 0
            logger.info(
                "ClinVar direct: opened cache with %d variants", self._variant_count
            )
            return

        logger.info("ClinVar direct: building cache from %s ...", tsv_path.name)
        known_rsids = await self._load_known_rsids()
        if not known_rsids:
            logger.warning("ClinVar direct: no rsids in genetic_markers — skipping build")
            return

        count = await asyncio.to_thread(self._scan_tsv_to_sqlite, tsv_path, known_rsids)
        self._save_meta(marker_fp, file_fp, count)
        self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
        self._variant_count = count
        logger.info("ClinVar direct cache built: %d variants", count)

    def _scan_tsv_to_sqlite(self, tsv_path: Path, known_rsids: set) -> int:
        """Scan variant_summary.txt.gz, store matching rsids in SQLite."""
        tmp = _SQLITE_FILE.with_suffix(".tmp")
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            tmp.unlink()

        conn = sqlite3.connect(str(tmp), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("""
            CREATE TABLE clinvar_data (
                rsid TEXT PRIMARY KEY,
                data BLOB NOT NULL
            )
        """)

        count = 0
        batch: list = []
        t0 = time.time()

        assembly_pref = "GRCh37"  # prefer GRCh37 to match user data

        # Group rows by rsid to aggregate multiple ClinVar entries
        aggregated: Dict[str, Dict] = {}

        with gzip.open(str(tsv_path), "rt", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    rec = ClinVarSummaryRecord.from_row(row)
                except Exception:
                    continue
                if not rec.rsid or rec.rsid not in known_rsids:
                    continue
                # Prefer GRCh37 rows; store first hit per rsid
                ann = rec.to_annotation()
                if rec.rsid not in aggregated:
                    aggregated[rec.rsid] = ann
                else:
                    # Merge: prefer GRCh37 assembly info; aggregate sigs/conditions
                    existing = aggregated[rec.rsid]
                    if rec.assembly == assembly_pref:
                        aggregated[rec.rsid] = ann  # overwrite with GRCh37 row
                    elif rec.clinical_significance:
                        sigs = existing.get("clinical_significances", [])
                        if rec.clinical_significance not in sigs:
                            sigs.append(rec.clinical_significance)
                        existing["clinical_significances"] = sigs
                    for cond in ann.get("conditions", []):
                        if cond not in existing.get("conditions", []):
                            existing.setdefault("conditions", []).append(cond)

        for rsid, ann in aggregated.items():
            raw = json.dumps(ann).encode("utf-8")
            blob = zlib.compress(raw, level=1)
            batch.append((rsid, blob))
            count += 1
            if len(batch) >= _BATCH_SIZE:
                conn.executemany(
                    "INSERT OR REPLACE INTO clinvar_data (rsid, data) VALUES (?, ?)",
                    batch,
                )
                conn.commit()
                batch.clear()

        if batch:
            conn.executemany(
                "INSERT OR REPLACE INTO clinvar_data (rsid, data) VALUES (?, ?)",
                batch,
            )
            conn.commit()

        elapsed = time.time() - t0
        print(f"[ClinVar direct] Scanned {tsv_path.name}: {count} rsids cached in {elapsed:.1f}s")

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
    # Position lookup via tabix (clinvar.vcf.gz)
    # ------------------------------------------------------------------

    def _tabix_lookup(
        self, vcf_path: Path, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        try:
            import pysam
        except ImportError:
            logger.debug("pysam not available for ClinVar tabix lookup")
            return None

        chrom_clean = chrom.replace("chr", "")
        ref_upper = ref.upper()
        alt_upper = alt.upper()

        try:
            tabix = pysam.TabixFile(str(vcf_path))
        except Exception as e:
            logger.debug("ClinVar tabix open failed: %s", e)
            return None

        try:
            for row_str in tabix.fetch(chrom_clean, pos - 1, pos):
                parts = row_str.split("\t", 9)
                if len(parts) < 8:
                    continue
                row_ref = parts[3].upper()
                row_alt = parts[4].upper()
                if row_ref != ref_upper or row_alt != alt_upper:
                    continue
                try:
                    rec = ClinVarVcfRecord.from_vcf_fields(
                        parts[0], int(parts[1]), parts[2], parts[3], parts[4], parts[7]
                    )
                    return rec.to_annotation()
                except Exception:
                    continue
        except ValueError:
            pass  # contig not in tabix
        except Exception as e:
            logger.debug("ClinVar tabix fetch error: %s", e)
        finally:
            tabix.close()

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_tsv(self) -> Optional[Path]:
        candidates = [
            _CLINVAR_DATA_DIR / "tsv" / "variant_summary.txt.gz",
            _CLINVAR_DATA_DIR / "variant_summary.txt.gz",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    def _find_vcf(self) -> Optional[Path]:
        candidates = [
            _CLINVAR_DATA_DIR / "vcf" / "clinvar.vcf.gz",
            _CLINVAR_DATA_DIR / "clinvar.vcf.gz",
        ]
        for p in candidates:
            if p.exists() and Path(str(p) + ".tbi").exists():
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

    def _get_file_fingerprint(self, tsv_path: Path) -> str:
        try:
            return f"{tsv_path.name}:{tsv_path.stat().st_size}"
        except OSError:
            return tsv_path.name

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


# Singleton
_instance: Optional[ClinVarDirectService] = None


def get_clinvar_direct_service() -> ClinVarDirectService:
    global _instance
    if _instance is None:
        _instance = ClinVarDirectService()
    return _instance
