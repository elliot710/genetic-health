"""
Local Ensembl VEP lookup service backed by VCF files on disk.

Scans per-chromosome VCF files once, stores results in a SQLite cache
(rsid → compressed JSON vep_data) for fast lookups.  Uses <100MB RAM
instead of 6+ GB, which prevents OOM kills in memory-constrained
Docker environments.

Cold scan: ~15min (sequential VCF read → SQLite write)
Warm restart: <3s (validate fingerprint → open SQLite)

Usage:
    svc = get_ensembl_vep_service()
    await svc.ensure_loaded()
    result = await svc.lookup('rs1234')
    batch = await svc.lookup_batch(['rs1234', 'rs5678'])
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func

from ..db.database import async_session_factory
from ..db.models import GeneticMarker

logger = logging.getLogger(__name__)

_ENSEMBL_DATA_DIR = Path(os.environ.get(
    'ENSEMBL_DATA_DIR',
    '/app/data_sources/ensembl/homo_sapiens',
))
_VCF_VEP_DIR = _ENSEMBL_DATA_DIR / 'variation' / 'vcf_vep'
_CACHE_DIR = Path(os.environ.get('VEP_CACHE_DIR', '/app/data_sources/ensembl/.vep_cache'))
_SQLITE_FILE = _CACHE_DIR / 'vep_cache.db'
_META_FILE = _CACHE_DIR / 'vep_cache_meta.json'

_CHR_PATTERN = re.compile(r'homo_sapiens_incl_consequences-chr\w+\.vcf\.gz$')

# SQLite batch size for inserts
_BATCH_SIZE = 2000


class EnsemblVepLocalService:
    """VCF-file-backed Ensembl VEP lookup service with SQLite cache.

    On first use, checks for a valid SQLite cache.  If stale or missing,
    scans all VCF files sequentially and writes results to SQLite.
    Lookups read from SQLite — total RAM usage stays under 100 MB.
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
                logger.error(f"Failed to load Ensembl VEP cache: {e}", exc_info=True)
            self._loaded = True
        return self._db is not None

    # ------------------------------------------------------------------
    # Fingerprinting for cache invalidation
    # ------------------------------------------------------------------

    async def _get_marker_fingerprint(self) -> str:
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(GeneticMarker.id))
            )
            count = result.scalar() or 0
        return str(count)

    def _get_vcf_fingerprint(self, vcf_files: List[Path]) -> str:
        parts = []
        for p in sorted(vcf_files):
            try:
                parts.append(f"{p.name}:{p.stat().st_size}")
            except OSError:
                parts.append(p.name)
        return hashlib.md5('|'.join(parts).encode()).hexdigest()

    # ------------------------------------------------------------------
    # SQLite cache management
    # ------------------------------------------------------------------

    def _open_db(self, path: Path) -> sqlite3.Connection:
        """Open SQLite in WAL mode for concurrent reads."""
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-65536")  # 64 MB page cache
        return conn

    def _create_db(self, path: Path) -> sqlite3.Connection:
        """Create a new SQLite cache DB."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        if tmp.exists():
            tmp.unlink()
        conn = sqlite3.connect(str(tmp), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")  # faster during bulk insert
        conn.execute("""
            CREATE TABLE vep_data (
                rsid TEXT PRIMARY KEY,
                data BLOB NOT NULL
            )
        """)
        return conn

    def _finalize_db(self, conn: sqlite3.Connection, tmp: Path, final: Path):
        """Finalize the DB: checkpoint WAL, close, rename."""
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        if final.exists():
            final.unlink()
        # Clean WAL/SHM files from temp before rename
        for suffix in ['-wal', '-shm']:
            f = tmp.with_name(tmp.name + suffix)
            if f.exists():
                f.unlink()
        tmp.rename(final)

    def _is_cache_valid(self, marker_fp: str, vcf_fp: str) -> bool:
        """Check if the existing SQLite cache matches current fingerprints."""
        if not _SQLITE_FILE.exists() or not _META_FILE.exists():
            return False
        try:
            meta = json.loads(_META_FILE.read_text())
            if meta.get('marker_fingerprint') != marker_fp:
                logger.info("VEP SQLite cache stale: genetic_markers changed")
                return False
            if meta.get('vcf_fingerprint') != vcf_fp:
                logger.info("VEP SQLite cache stale: VCF files changed")
                return False
            return True
        except Exception:
            return False

    def _save_meta(self, marker_fp: str, vcf_fp: str, count: int):
        meta = {
            'marker_fingerprint': marker_fp,
            'vcf_fingerprint': vcf_fp,
            'variant_count': count,
            'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        _META_FILE.write_text(json.dumps(meta, indent=2))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def _load_known_rsids(self) -> Set[str]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticMarker.rsid).where(GeneticMarker.rsid.isnot(None))
            )
            rsids = {r[0] for r in result.all()}
        logger.info(f"Ensembl VEP file service: {len(rsids)} known rsids for filtering")
        return rsids

    async def _load_cache(self):
        """Open existing SQLite cache or build from VCF files."""
        if not _VCF_VEP_DIR.exists():
            logger.warning(f"VCF VEP directory not found: {_VCF_VEP_DIR}")
            return

        vcf_files = self._discover_vcf_files()
        if not vcf_files:
            logger.warning(f"No VCF files found in {_VCF_VEP_DIR}")
            return

        marker_fp = await self._get_marker_fingerprint()
        vcf_fp = self._get_vcf_fingerprint(vcf_files)

        # Try existing cache
        if self._is_cache_valid(marker_fp, vcf_fp):
            t0 = time.time()
            self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
            row = self._db.execute("SELECT COUNT(*) FROM vep_data").fetchone()
            self._variant_count = row[0] if row else 0
            elapsed = time.time() - t0
            logger.info(
                f"Ensembl VEP: opened SQLite cache with {self._variant_count} "
                f"variants in {elapsed:.1f}s"
            )
            return

        # Cold scan
        logger.info(f"VEP cache miss — scanning {len(vcf_files)} VCF files into SQLite...")
        known_rsids = await self._load_known_rsids()
        if not known_rsids:
            logger.info("No known rsids — skipping VCF scan")
            return

        count = await asyncio.to_thread(
            self._scan_vcf_to_sqlite, vcf_files, known_rsids
        )
        self._save_meta(marker_fp, vcf_fp, count)
        self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
        self._variant_count = count

    def _discover_vcf_files(self) -> List[Path]:
        vcf_files = sorted(
            p for p in _VCF_VEP_DIR.iterdir()
            if _CHR_PATTERN.match(p.name)
        )
        for name in [
            'homo_sapiens_clinically_associated.vcf.gz',
            'homo_sapiens_phenotype_associated.vcf.gz',
        ]:
            p = _VCF_VEP_DIR / name
            if p.exists():
                vcf_files.append(p)
        return vcf_files

    # ------------------------------------------------------------------
    # VCF scanning → SQLite (runs in background thread)
    # ------------------------------------------------------------------

    def _scan_vcf_to_sqlite(
        self, vcf_files: List[Path], known_rsids: Set[str]
    ) -> int:
        """Scan VCF files and write to SQLite. Returns total variant count."""
        from .ensembl_vep_etl import parse_vcf_line

        tmp_path = _SQLITE_FILE.with_suffix('.tmp')
        conn = self._create_db(_SQLITE_FILE)
        t0 = time.time()
        total = 0
        batch: list = []

        for i, vcf_path in enumerate(vcf_files, 1):
            file_t0 = time.time()
            file_count = 0
            print(f"[VEP] Starting [{i}/{len(vcf_files)}] {vcf_path.name}", flush=True)

            try:
                with gzip.open(vcf_path, 'rt', encoding='utf-8', errors='replace') as fh:
                    for line in fh:
                        if line.startswith('#'):
                            continue
                        parts = line.split('\t', 4)
                        if len(parts) < 3:
                            continue
                        rsid = parts[2]
                        if not rsid.startswith('rs') or rsid not in known_rsids:
                            continue
                        parsed = parse_vcf_line(line, known_rsids)
                        if parsed and parsed.get('rsid'):
                            # Store compressed JSON blob
                            raw = parsed['vep_data'].encode('utf-8')
                            blob = zlib.compress(raw, level=1)
                            batch.append((parsed['rsid'], blob))
                            file_count += 1

                            if len(batch) >= _BATCH_SIZE:
                                conn.executemany(
                                    "INSERT OR REPLACE INTO vep_data (rsid, data) VALUES (?, ?)",
                                    batch,
                                )
                                conn.commit()
                                batch.clear()
            except Exception as e:
                print(f"[VEP] ERROR {vcf_path.name}: {e}", flush=True)
                continue

            # Flush remaining batch for this file
            if batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO vep_data (rsid, data) VALUES (?, ?)",
                    batch,
                )
                conn.commit()
                batch.clear()

            total += file_count
            elapsed = time.time() - file_t0
            print(
                f"[VEP]   [{i}/{len(vcf_files)}] {vcf_path.name}: "
                f"{file_count} variants in {elapsed:.1f}s (total: {total})",
                flush=True,
            )
            logger.info(
                f"  [{i}/{len(vcf_files)}] {vcf_path.name}: "
                f"{file_count} variants in {elapsed:.1f}s"
            )

        elapsed = time.time() - t0
        msg = (
            f"VEP scan complete: {total} variants from "
            f"{len(vcf_files)} files in {elapsed:.1f}s"
        )
        print(f"[VEP] {msg}", flush=True)
        logger.info(msg)

        self._finalize_db(conn, tmp_path, _SQLITE_FILE)
        return total

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not await self.ensure_loaded():
            return None
        row = await asyncio.to_thread(self._lookup_one, rsid)
        if row:
            return row
        return {'found': False, 'source': 'ensembl'}

    def _lookup_one(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not self._db:
            return None
        row = self._db.execute(
            "SELECT data FROM vep_data WHERE rsid = ?", (rsid,)
        ).fetchone()
        if row:
            return json.loads(zlib.decompress(row[0]))
        return None

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not rsids:
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, rsids)

    def _lookup_batch_sync(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not self._db:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        total = len(rsids)
        total_batches = (total + 499) // 500
        import time as _time
        t0 = _time.monotonic()
        # SQLite has a variable limit (~999), so batch the query
        for start in range(0, len(rsids), 500):
            chunk = rsids[start:start + 500]
            batch_num = start // 500 + 1
            placeholders = ','.join('?' * len(chunk))
            rows = self._db.execute(
                f"SELECT rsid, data FROM vep_data WHERE rsid IN ({placeholders})",
                chunk,
            ).fetchall()
            for rsid, blob in rows:
                results[rsid] = json.loads(zlib.decompress(blob))

            if batch_num % 20 == 0 or batch_num == total_batches:
                elapsed = _time.monotonic() - t0
                rate = (start + len(chunk)) / elapsed if elapsed > 0 else 0
                logger.info(
                    f"  Ensembl VEP batch {batch_num}/{total_batches}: "
                    f"{start + len(chunk)}/{total} queried, {len(results)} found "
                    f"({rate:.0f} rsids/s, {elapsed:.1f}s elapsed)"
                )

        elapsed = _time.monotonic() - t0
        logger.info(f"  Ensembl VEP complete: {len(results)}/{total} found in {elapsed:.1f}s")
        return results


# Singleton
_instance: Optional[EnsemblVepLocalService] = None


def get_ensembl_vep_service() -> EnsemblVepLocalService:
    global _instance
    if _instance is None:
        _instance = EnsemblVepLocalService()
    return _instance
