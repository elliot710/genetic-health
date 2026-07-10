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
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, text

from ..db.database import async_session_factory
from ..db.models import GeneticMarker, EnsemblGene
from .datasource_utils import (
    get_multi_file_fingerprint,
    open_cache_db,
)

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
        self._vcf_available: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and (self._db is not None or self._vcf_available)

    @property
    def variant_count(self) -> int:
        return self._variant_count

    async def ensure_loaded(self) -> bool:
        """Open or build the SQLite cache (runs once)."""
        if self._loaded:
            return self._db is not None or self._vcf_available
        async with self._lock:
            if self._loaded:
                return self._db is not None or self._vcf_available
            try:
                await self._load_cache()
            except Exception as e:
                logger.error(f"Failed to load Ensembl VEP cache: {e}", exc_info=True)
            self._loaded = True
        return self._db is not None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def _load_cache(self):
        """Open existing SQLite cache or build from VCF files."""
        if not _VCF_VEP_DIR.exists():
            logger.warning(f"VCF VEP directory not found: {_VCF_VEP_DIR}")
            return

        vcf_files = self._discover_vcf_files()
        if not vcf_files:
            logger.warning(f"No VCF files found in {_VCF_VEP_DIR}")
            return

        # Mark VCF dir as available for tabix position queries if indexed files exist
        indexed = [f for f in vcf_files if Path(str(f) + '.tbi').exists()]
        if indexed:
            self._vcf_available = True
            logger.info("Ensembl VEP: %d indexed VCF files available for tabix queries", len(indexed))

        vcf_fp = get_multi_file_fingerprint(vcf_files)

        # Load existing SQLite cache if VCF files are unchanged.
        if _SQLITE_FILE.exists() and _META_FILE.exists():
            try:
                meta = json.loads(_META_FILE.read_text())
                if meta.get("vcf_fingerprint") == vcf_fp and meta.get("variant_count", 0) > 0:
                    t0 = time.time()
                    self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE)
                    row = self._db.execute("SELECT COUNT(*) FROM vep_data").fetchone()
                    self._variant_count = row[0] if row else 0
                    logger.info(
                        f"Ensembl VEP: opened SQLite cache with {self._variant_count} "
                        f"variants in {time.time() - t0:.1f}s"
                    )
                    return
            except Exception:
                pass

        # No valid SQLite cache — rely on per-chromosome VCF tabix for position queries.
        # Cache builds from filtered rsid sets are no longer performed here;
        # position fallback in local_annotation.py handles uncached variants.
        if self._vcf_available:
            logger.info("Ensembl VEP: no SQLite cache — tabix position queries will be used for analysis")
        else:
            logger.warning("Ensembl VEP: no SQLite cache and no indexed VCFs — annotation unavailable")

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
        conn = create_cache_db(_SQLITE_FILE, """
            CREATE TABLE vep_data (
                rsid TEXT PRIMARY KEY,
                data BLOB NOT NULL
            )
        """)
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

        finalize_cache_db(conn, tmp_path, _SQLITE_FILE)
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

    async def lookup_or_scan(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Try SQLite cache first; if not found (or cache not ready), scan VCF files directly.

        Results found in the VCF scan are cached into SQLite immediately so
        subsequent lookups for the same rsid are fast.
        """
        # 1. Try SQLite cache
        if self._db is not None:
            row = await asyncio.to_thread(self._lookup_one, rsid)
            if row:
                return row

        # 2. No cache hit — scan VCF files directly
        if _VCF_VEP_DIR.exists():
            result = await asyncio.to_thread(self._scan_single_rsid, rsid)
            if result:
                return result

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

    def _scan_single_rsid(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Linear scan of all VCF files for a single rsid.

        Stops at the first hit, parses the line, caches the result into
        the SQLite DB (if open) and returns the VEP data dict.
        """
        from .ensembl_vep_etl import parse_vcf_line

        vcf_files = self._discover_vcf_files()
        for vcf_path in vcf_files:
            try:
                with gzip.open(vcf_path, 'rt', encoding='utf-8', errors='replace') as fh:
                    for line in fh:
                        if line.startswith('#'):
                            continue
                        # Fast pre-filter before full parse
                        parts = line.split('\t', 3)
                        if len(parts) < 3 or parts[2] != rsid:
                            continue
                        # Found the rsid — parse it
                        parsed = parse_vcf_line(line, {rsid})
                        if not parsed or parsed.get('rsid') != rsid:
                            continue
                        vep_dict = json.loads(parsed['vep_data'])
                        # Cache into SQLite so next hit is instant
                        if self._db is not None:
                            try:
                                blob = zlib.compress(
                                    parsed['vep_data'].encode('utf-8'), level=1
                                )
                                self._db.execute(
                                    "INSERT OR REPLACE INTO vep_data (rsid, data) VALUES (?, ?)",
                                    (rsid, blob),
                                )
                                self._db.commit()
                                self._variant_count += 1
                            except Exception:
                                pass
                        logger.debug(
                            f"[VEP] Direct VCF scan hit for {rsid} in {vcf_path.name}"
                        )
                        return vep_dict
            except Exception as e:
                logger.debug(f"[VEP scan] error reading {vcf_path.name}: {e}")
                continue
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

    async def lookup_by_position(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Tabix-based position lookup on the per-chromosome VCF file."""
        vcf_file = self._find_chr_vcf(chrom)
        if not vcf_file:
            return None
        return await asyncio.to_thread(
            self._tabix_pos_lookup, vcf_file, chrom, pos, ref, alt
        )

    async def lookup_batch_by_position(
        self, variants: List[Tuple[str, str, int, str, str]]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch tabix position lookup for (rsid, chrom, pos, ref, alt) tuples.

        Groups variants by chromosome to minimise file opens.
        """
        if not variants:
            return {}
        return await asyncio.to_thread(self._tabix_batch_by_chr, variants)

    def _find_chr_vcf(self, chrom: str) -> Optional[Path]:
        """Return the per-chromosome VCF path if it exists and is tabix-indexed."""
        chrom_clean = chrom.replace('chr', '')
        p = _VCF_VEP_DIR / f'homo_sapiens_incl_consequences-chr{chrom_clean}.vcf.gz'
        if p.exists() and Path(str(p) + '.tbi').exists():
            return p
        return None

    def _tabix_pos_lookup(
        self, vcf_path: Path, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Single-variant tabix query on a per-chromosome VCF. Returns VEP data dict."""
        from .ensembl_vep_etl import parse_vcf_line
        try:
            import pysam
        except ImportError:
            return None
        chrom_clean = chrom.replace('chr', '')
        ref_upper, alt_upper = ref.upper(), alt.upper()
        try:
            tabix = pysam.TabixFile(str(vcf_path))
            for row_str in tabix.fetch(chrom_clean, pos - 1, pos):
                parts = row_str.split('\t', 8)
                if len(parts) < 5:
                    continue
                if parts[3].upper() != ref_upper:
                    continue
                row_alts = parts[4].split(',')
                if not any(a.strip().upper() == alt_upper for a in row_alts):
                    continue
                rsid = parts[2] if parts[2].startswith('rs') else f"{chrom_clean}:{pos}:{ref}:{alt}"
                parsed = parse_vcf_line(row_str, {rsid})
                if parsed and parsed.get('rsid'):
                    vep_dict = json.loads(parsed['vep_data'])
                    vep_dict['found'] = True
                    vep_dict['source'] = 'ensembl_vep_local'
                    tabix.close()
                    return vep_dict
            tabix.close()
        except Exception as e:
            logger.debug("VEP tabix pos lookup failed for %s:%d: %s", chrom, pos, e)
        return None

    def _tabix_batch_by_chr(
        self, variants: List[Tuple[str, str, int, str, str]]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch tabix queries grouped by chromosome to minimise file I/O."""
        from .ensembl_vep_etl import parse_vcf_line
        try:
            import pysam
        except ImportError:
            return {}
        # Group by chromosome
        by_chr: Dict[str, List[Tuple[str, str, int, str, str]]] = {}
        for item in variants:
            rsid, chrom, pos, ref, alt = item
            chrom_clean = chrom.replace('chr', '')
            by_chr.setdefault(chrom_clean, []).append(item)

        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for chrom_clean, chr_variants in by_chr.items():
            vcf_path = self._find_chr_vcf(chrom_clean)
            if not vcf_path:
                continue
            try:
                tabix = pysam.TabixFile(str(vcf_path))
                for rsid, chrom, pos, ref, alt in chr_variants:
                    ref_upper, alt_upper = ref.upper(), alt.upper()
                    try:
                        for row_str in tabix.fetch(chrom_clean, pos - 1, pos):
                            parts = row_str.split('\t', 8)
                            if len(parts) < 5:
                                continue
                            if parts[3].upper() != ref_upper:
                                continue
                            row_alts = parts[4].split(',')
                            if not any(a.strip().upper() == alt_upper for a in row_alts):
                                continue
                            row_rsid = parts[2] if parts[2].startswith('rs') else \
                                f"{chrom_clean}:{pos}:{ref}:{alt}"
                            parsed = parse_vcf_line(row_str, {row_rsid})
                            if parsed and parsed.get('rsid'):
                                vep_dict = json.loads(parsed['vep_data'])
                                vep_dict['found'] = True
                                vep_dict['source'] = 'ensembl_vep_local'
                                results[rsid] = vep_dict
                                break
                    except ValueError:
                        pass
                    except Exception as e:
                        logger.debug("VEP tabix fetch error %s:%d: %s", chrom_clean, pos, e)
                tabix.close()
            except Exception as e:
                logger.debug("VEP tabix open error for chr%s: %s", chrom_clean, e)
        return results



class EnsemblLocalService:
    """PostgreSQL-backed Ensembl gene lookup service."""

    def __init__(self):
        self._gene_count: Optional[int] = None

    @property
    def is_loaded(self) -> bool:
        return self._gene_count is not None and self._gene_count > 0

    @property
    def gene_count(self) -> int:
        return self._gene_count or 0

    async def ensure_loaded(self) -> bool:
        if self._gene_count is not None:
            return self._gene_count > 0
        try:
            async with async_session_factory() as session:
                row = (await session.execute(select(EnsemblGene.id).limit(1))).scalar_one_or_none()
                if row is not None:
                    self._gene_count = (await session.execute(text("SELECT COUNT(*) FROM ensembl_genes"))).scalar()
                    logger.info(f"Ensembl local: {self._gene_count} genes available")
                else:
                    self._gene_count = 0
                    logger.info("Ensembl local: no genes loaded (run ETL first)")
        except Exception as e:
            self._gene_count = 0
            logger.debug(f"Ensembl local: table not available: {e}")
        return self._gene_count > 0

    async def lookup_gene(self, gene_symbol: str) -> Dict[str, Any]:
        async with async_session_factory() as session:
            gene = (await session.execute(
                select(EnsemblGene).where(EnsemblGene.gene_symbol == gene_symbol)
            )).scalar_one_or_none()
            if not gene:
                return {"found": False, "gene_symbol": gene_symbol}
            return {
                "found": True, "source": "ensembl_local",
                "gene_id": gene.gene_id, "gene_symbol": gene.gene_symbol,
                "chromosome": gene.chromosome, "start": gene.start_pos, "end": gene.end_pos,
                "strand": gene.strand, "biotype": gene.biotype,
                "description": gene.description, "transcript_count": gene.transcript_count,
            }

    async def lookup_gene_by_position(self, chromosome: str, position: int) -> Dict[str, Any]:
        chrom = str(chromosome).replace('chr', '')
        async with async_session_factory() as session:
            genes = (await session.execute(
                select(EnsemblGene).where(
                    EnsemblGene.chromosome == chrom,
                    EnsemblGene.start_pos <= position,
                    EnsemblGene.end_pos >= position,
                ).order_by(
                    (EnsemblGene.biotype != 'protein_coding').asc(),
                    (EnsemblGene.end_pos - EnsemblGene.start_pos).asc(),
                ).limit(5)
            )).scalars().all()
            if not genes:
                return {"found": False, "chromosome": chrom, "position": position}
            best = genes[0]
            return {
                "found": True, "source": "ensembl_local",
                "gene_symbol": best.gene_symbol, "gene_id": best.gene_id,
                "biotype": best.biotype, "description": best.description,
                "overlapping_genes": len(genes),
            }

    async def batch_position_to_gene(self, positions: List[Tuple[str, int, str]]) -> Dict[str, str]:
        if not positions or not await self.ensure_loaded():
            return {}
        gene_map: Dict[str, str] = {}
        batch_size = 500
        for i in range(0, len(positions), batch_size):
            batch = positions[i:i + batch_size]
            if i > 0:
                await asyncio.sleep(0)
            by_chrom: Dict[str, List[Tuple[int, str]]] = {}
            for chrom, pos, rsid in batch:
                by_chrom.setdefault(str(chrom).replace('chr', ''), []).append((pos, rsid))
            async with async_session_factory() as session:
                for chrom, pos_rsids in by_chrom.items():
                    pos_list = [p for p, _ in pos_rsids]
                    rsid_by_pos: Dict[int, List[str]] = {}
                    for pos, rsid in pos_rsids:
                        rsid_by_pos.setdefault(pos, []).append(rsid)
                    chrom_genes = (await session.execute(
                        select(EnsemblGene).where(
                            EnsemblGene.chromosome == chrom,
                            EnsemblGene.start_pos <= max(pos_list),
                            EnsemblGene.end_pos >= min(pos_list),
                        ).order_by(
                            (EnsemblGene.biotype != 'protein_coding').asc(),
                            (EnsemblGene.end_pos - EnsemblGene.start_pos).asc(),
                        )
                    )).scalars().all()
                    for pos in set(pos_list):
                        for gene in chrom_genes:
                            if gene.start_pos <= pos <= gene.end_pos:
                                for rsid in rsid_by_pos.get(pos, []):
                                    if rsid not in gene_map:
                                        gene_map[rsid] = gene.gene_symbol
                                break
        return gene_map


_ensembl_local_instance: Optional[EnsemblLocalService] = None


def get_ensembl_local_service() -> EnsemblLocalService:
    global _ensembl_local_instance
    if _ensembl_local_instance is None:
        _ensembl_local_instance = EnsemblLocalService()
    return _ensembl_local_instance


# ---------------------------------------------------------------------------
# EnsemblVepLocalService singleton
# ---------------------------------------------------------------------------

_instance: Optional[EnsemblVepLocalService] = None


def get_ensembl_vep_service() -> EnsemblVepLocalService:
    global _instance
    if _instance is None:
        _instance = EnsemblVepLocalService()
    return _instance
