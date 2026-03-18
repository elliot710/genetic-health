"""
Local gnomAD CADD lookup service backed by tabix-indexed TSV files on disk.

Uses pysam.TabixFile for O(log n) random-access position lookups on the
CADD-annotated gnomAD TSV, then caches results in SQLite for fast rsid-based
batch lookups (matching the Ensembl VEP cache pattern).

Cold scan: ~2-5 min (targeted tabix reads for known variant positions → SQLite)
Warm restart: <1s (validate fingerprint → open SQLite)

The SQLite cache is keyed by rsid and stores compressed JSON blobs of
pathogenicity data (CADD, SIFT, PolyPhen, PhyloP, SpliceAI, gene, consequence).

Usage:
    svc = get_gnomad_cache_service()
    await svc.ensure_loaded()
    result = await svc.lookup('rs1234')
    batch = await svc.lookup_batch(['rs1234', 'rs5678'])
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
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func

from ..db.database import async_session_factory
from ..db.models import GeneticMarker

logger = logging.getLogger(__name__)

_GNOMAD_DATA_DIR = Path(os.environ.get(
    'GNOMAD_DATA_DIR',
    '/app/data_sources/gnomad',
))
_CACHE_DIR = Path(os.environ.get(
    'GNOMAD_CACHE_DIR',
    '/app/data_sources/gnomad/.gnomad_cache',
))
_SQLITE_FILE = _CACHE_DIR / 'gnomad_cache.db'
_META_FILE = _CACHE_DIR / 'gnomad_cache_meta.json'

_BATCH_SIZE = 2000
_TABIX_BATCH = 500  # positions per tabix scan batch


class GnomadCacheService:
    """SQLite-backed gnomAD CADD cache built from tabix-indexed TSV files.

    On first use, scans TSV files at known variant positions using tabix,
    stores results in SQLite keyed by rsid.  Subsequent lookups read from
    SQLite — total RAM stays under 50 MB.
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
                logger.error("Failed to load gnomAD cache: %s", e, exc_info=True)
            self._loaded = True
        return self._db is not None

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    async def _get_marker_fingerprint(self) -> str:
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(GeneticMarker.id))
            )
            count = result.scalar() or 0
        return str(count)

    def _get_file_fingerprint(self, tsv_files: List[Path]) -> str:
        parts = []
        for p in sorted(tsv_files):
            try:
                parts.append(f"{p.name}:{p.stat().st_size}")
            except OSError:
                parts.append(p.name)
        return hashlib.md5('|'.join(parts).encode()).hexdigest()

    # ------------------------------------------------------------------
    # SQLite cache management
    # ------------------------------------------------------------------

    def _open_db(self, path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32768")  # 32 MB page cache
        return conn

    def _create_db(self, path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        if tmp.exists():
            tmp.unlink()
        conn = sqlite3.connect(str(tmp), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("""
            CREATE TABLE gnomad_data (
                rsid TEXT PRIMARY KEY,
                data BLOB NOT NULL
            )
        """)
        return conn

    def _finalize_db(self, conn: sqlite3.Connection, tmp: Path, final: Path):
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        if final.exists():
            final.unlink()
        for suffix in ['-wal', '-shm']:
            f = tmp.with_name(tmp.name + suffix)
            if f.exists():
                f.unlink()
        tmp.rename(final)

    def _is_cache_valid(self, marker_fp: str, file_fp: str) -> bool:
        if not _SQLITE_FILE.exists() or not _META_FILE.exists():
            return False
        try:
            meta = json.loads(_META_FILE.read_text())
            if meta.get('marker_fingerprint') != marker_fp:
                logger.info("gnomAD cache stale: genetic_markers changed")
                return False
            if meta.get('file_fingerprint') != file_fp:
                logger.info("gnomAD cache stale: TSV files changed")
                return False
            return True
        except Exception:
            return False

    def _save_meta(self, marker_fp: str, file_fp: str, count: int):
        meta = {
            'marker_fingerprint': marker_fp,
            'file_fingerprint': file_fp,
            'variant_count': count,
            'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        _META_FILE.write_text(json.dumps(meta, indent=2))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _discover_tsv_files(self) -> List[Path]:
        """Find all tabix-indexed gnomAD TSV files (bgzip + .tbi pairs)."""
        files = []
        if not _GNOMAD_DATA_DIR.exists():
            return files
        for p in sorted(_GNOMAD_DATA_DIR.iterdir()):
            if p.name.endswith('.tsv.gz') and 'constraint' not in p.name.lower():
                tbi = Path(str(p) + '.tbi')
                if tbi.exists():
                    files.append(p)
        return files

    def _detect_genome_build(self, tsv_path: Path) -> Optional[str]:
        """Read gzip header lines to detect the genome build annotation.

        Returns 'GRCh38-v1.7' / 'GRCh37-v1.6' style token, or None.
        """
        try:
            with gzip.open(str(tsv_path), 'rt', encoding='utf-8', errors='replace') as fh:
                for i, line in enumerate(fh):
                    if i > 60:
                        break
                    if not line.startswith('#'):
                        break  # past header section
                    for build_tag in ('GRCh38', 'GRCh37', 'hg38', 'hg19'):
                        if build_tag in line:
                            for token in line.split():
                                if build_tag in token:
                                    return token.strip().strip(',')
                            return build_tag
        except Exception as e:
            logger.debug("gnomAD build detection failed for %s: %s", tsv_path.name, e)
        return None

    async def _load_known_positions(self) -> Dict[Tuple[str, int], List[Tuple[str, str, str]]]:
        """Load all (chrom, pos) → [(rsid, ref, alt), ...] from genetic_markers.

        Returns a dict mapping (chromosome, position) to a list of known
        variants at that position (for matching ref/alt alleles).
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    GeneticMarker.rsid,
                    GeneticMarker.chromosome,
                    GeneticMarker.position,
                    GeneticMarker.ref_allele,
                    GeneticMarker.alt_alleles,
                ).where(
                    GeneticMarker.rsid.isnot(None),
                    GeneticMarker.chromosome.isnot(None),
                    GeneticMarker.position.isnot(None),
                )
            )
            pos_map: Dict[Tuple[str, int], List[Tuple[str, str, str]]] = {}
            for rsid, chrom, pos, ref, alt in result.all():
                chrom_clean = str(chrom).replace('chr', '').strip()
                key = (chrom_clean, int(pos))
                pos_map.setdefault(key, []).append((rsid, ref or '', alt or ''))
            logger.info("gnomAD cache: %d unique positions from %d markers",
                        len(pos_map), sum(len(v) for v in pos_map.values()))
            return pos_map

    async def _load_cache(self):
        """Open existing SQLite cache or build from tabix TSV files."""
        tsv_files = self._discover_tsv_files()
        if not tsv_files:
            logger.warning("No tabix-indexed gnomAD TSV files found in %s", _GNOMAD_DATA_DIR)
            return

        # BUG-16: Detect genome build from the file header before scanning.
        # User variant positions are on GRCh37 (23andMe/AncestryDNA chips).
        # gnomAD CADD v4.x files are GRCh38 — position matching would yield 0 hits.
        build = self._detect_genome_build(tsv_files[0])
        if build and 'GRCh38' in build:
            logger.error(
                "gnomAD CADD file '%s' is annotated on %s but user variant "
                "positions are GRCh37/hg19.  Cache would always build empty.\n"
                "  \u2192 Download the GRCh37 version from:\n"
                "    https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh37/"
                "gnomad.genomes.r2.1.1.snv_inclAnno.tsv.gz\n"
                "  Then delete the existing cache to force a rebuild.",
                tsv_files[0].name, build,
            )
            return

        marker_fp = await self._get_marker_fingerprint()
        file_fp = self._get_file_fingerprint(tsv_files)

        # Try existing cache
        if self._is_cache_valid(marker_fp, file_fp):
            t0 = time.time()
            self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
            row = self._db.execute("SELECT COUNT(*) FROM gnomad_data").fetchone()
            self._variant_count = row[0] if row else 0
            elapsed = time.time() - t0
            logger.info(
                "gnomAD: opened SQLite cache with %d variants in %.1fs",
                self._variant_count, elapsed,
            )
            return

        # Cold scan using tabix
        logger.info("gnomAD cache miss — scanning %d TSV files at known positions...",
                     len(tsv_files))
        pos_map = await self._load_known_positions()
        if not pos_map:
            logger.info("No known variant positions — skipping gnomAD cache build")
            return

        count = await asyncio.to_thread(
            self._scan_tabix_to_sqlite, tsv_files, pos_map,
        )
        self._save_meta(marker_fp, file_fp, count)
        self._db = await asyncio.to_thread(self._open_db, _SQLITE_FILE)
        self._variant_count = count

    # ------------------------------------------------------------------
    # Tabix scanning → SQLite (runs in background thread)
    # ------------------------------------------------------------------

    def _scan_tabix_to_sqlite(
        self,
        tsv_files: List[Path],
        pos_map: Dict[Tuple[str, int], List[Tuple[str, str, str]]],
    ) -> int:
        """Scan gnomAD TSV files and match against known variant positions.

        Iterates each chromosome sequentially (one pass per contig) and checks
        each row against the known-positions set.  This is vastly faster than
        doing 700K individual tabix.fetch() calls.
        """
        import pysam

        conn = self._create_db(_SQLITE_FILE)
        t0 = time.time()
        total = 0
        batch: list = []

        # Pre-build a fast lookup set of known positions per chromosome
        pos_set: Dict[str, Set[int]] = {}
        for (chrom, pos), _ in pos_map.items():
            pos_set.setdefault(chrom, set()).add(pos)

        for fi, tsv_path in enumerate(tsv_files, 1):
            file_t0 = time.time()
            file_count = 0
            rows_scanned = 0
            print(f"[gnomAD] Starting [{fi}/{len(tsv_files)}] {tsv_path.name}", flush=True)

            try:
                tabix = pysam.TabixFile(str(tsv_path))
            except Exception as e:
                print(f"[gnomAD] ERROR opening {tsv_path.name}: {e}", flush=True)
                continue

            # Discover available contigs in the tabix file
            try:
                available_contigs = list(tabix.contigs)
            except Exception:
                available_contigs = []

            # Parse header to build column map
            col_map = self._parse_header(tabix)
            if not col_map:
                print(f"[gnomAD] ERROR: could not parse header from {tsv_path.name}", flush=True)
                tabix.close()
                continue

            # Determine column indices for chrom/pos (fast pre-check before full parse)
            chrom_idx = col_map.get('chrom', col_map.get('chr', col_map.get('#chrom')))
            pos_idx = col_map.get('pos', col_map.get('position'))

            # Iterate each contig sequentially — single pass per chromosome
            for contig in available_contigs:
                # Normalize contig to match our pos_map keys (strip 'chr' prefix)
                chrom_key = contig.replace('chr', '') if contig.startswith('chr') else contig
                known_positions = pos_set.get(chrom_key)
                if not known_positions:
                    continue

                chrom_t0 = time.time()
                chrom_count = 0

                try:
                    for row_str in tabix.fetch(contig):
                        rows_scanned += 1

                        # Fast pre-check: extract position before full parse
                        if pos_idx is not None:
                            fields = row_str.split('\t', pos_idx + 2)
                            if len(fields) > pos_idx:
                                try:
                                    row_pos = int(fields[pos_idx])
                                except (ValueError, TypeError):
                                    continue
                                if row_pos not in known_positions:
                                    continue

                        # Full parse only for matching positions
                        parsed = self._parse_cadd_row(row_str, col_map)
                        if parsed is None:
                            continue

                        row_pos = parsed['pos']
                        variants_at_pos = pos_map.get((chrom_key, row_pos))
                        if not variants_at_pos:
                            continue

                        # Match against known variants at this position
                        for rsid, ref, alt in variants_at_pos:
                            if self._alleles_match(parsed['ref'], parsed['alt'], ref, alt):
                                data = self._format_result(parsed, rsid)
                                raw = json.dumps(data).encode('utf-8')
                                blob = zlib.compress(raw, level=1)
                                batch.append((rsid, blob))
                                chrom_count += 1

                                if len(batch) >= _BATCH_SIZE:
                                    conn.executemany(
                                        "INSERT OR REPLACE INTO gnomad_data (rsid, data) VALUES (?, ?)",
                                        batch,
                                    )
                                    conn.commit()
                                    batch.clear()
                except Exception as e:
                    logger.debug("gnomAD tabix contig %s error: %s", contig, e)
                    continue

                file_count += chrom_count
                if chrom_count > 0:
                    elapsed = time.time() - chrom_t0
                    print(
                        f"[gnomAD]   chr{chrom_key}: {chrom_count} matches in {elapsed:.1f}s",
                        flush=True,
                    )

            tabix.close()

            if batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO gnomad_data (rsid, data) VALUES (?, ?)",
                    batch,
                )
                conn.commit()
                batch.clear()

            total += file_count
            elapsed = time.time() - file_t0
            print(
                f"[gnomAD]   [{fi}/{len(tsv_files)}] {tsv_path.name}: "
                f"{rows_scanned:,} rows scanned, {file_count} matches in {elapsed:.1f}s",
                flush=True,
            )

        elapsed = time.time() - t0
        msg = f"gnomAD scan complete: {total} variants from {len(tsv_files)} files in {elapsed:.1f}s"
        print(f"[gnomAD] {msg}", flush=True)
        logger.info(msg)

        self._finalize_db(conn, _SQLITE_FILE.with_suffix('.tmp'), _SQLITE_FILE)
        return total

    # ------------------------------------------------------------------
    # CADD TSV parsing helpers
    # ------------------------------------------------------------------

    def _parse_header(self, tabix) -> Optional[Dict[str, int]]:
        """Extract header from the tabix file and build column index map."""
        try:
            header_line = tabix.header
            if header_line:
                # tabix.header returns a list of header lines
                for line in header_line:
                    line = line if isinstance(line, str) else line.decode('utf-8')
                    if not line.startswith('##'):
                        parts = line.strip().split('\t')
                        return {name.strip().lstrip('#').lower(): i for i, name in enumerate(parts)}
        except Exception:
            pass

        # Fallback: try reading the first non-comment line from the gzipped file
        try:
            path = tabix.filename if isinstance(tabix.filename, str) else tabix.filename.decode('utf-8')
            with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    if line.startswith('##'):
                        continue
                    parts = line.strip().split('\t')
                    return {name.strip().lstrip('#').lower(): i for i, name in enumerate(parts)}
        except Exception as e:
            logger.error("Failed to parse gnomAD TSV header: %s", e)

        return None

    def _parse_cadd_row(self, row_str: str, idx: Dict[str, int]) -> Optional[Dict[str, Any]]:
        """Parse a single CADD TSV row into a dict of relevant fields."""
        fields = row_str.split('\t')

        def _get(name: str) -> Optional[str]:
            i = idx.get(name)
            if i is None or i >= len(fields):
                return None
            v = fields[i].strip()
            return v if v and v not in ('.', 'NA', 'nan', '') else None

        def _float(name: str) -> Optional[float]:
            v = _get(name)
            if not v:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        # Try common column name variants
        chrom = _get('chrom') or _get('chr') or _get('#chrom')
        if not chrom:
            return None
        chrom = chrom.replace('chr', '')

        pos_str = _get('pos') or _get('position')
        if not pos_str:
            return None
        try:
            pos = int(pos_str)
        except (ValueError, TypeError):
            return None

        ref = _get('ref') or _get('reference')
        alt = _get('alt') or _get('alternate')
        if not ref or not alt:
            return None

        return {
            'chrom': chrom,
            'pos': pos,
            'ref': ref,
            'alt': alt,
            'variant_type': _get('type'),
            'gene': _get('genename') or _get('gene') or _get('gene_symbol'),
            'consequence': _get('consequence'),
            'cadd_raw': _float('rawscore'),
            'cadd_phred': _float('phred'),
            'sift_cat': _get('siftcat'),
            'sift_val': _float('siftval'),
            'polyphen_cat': _get('polyphencat'),
            'polyphen_val': _float('polyphenval'),
            'phylop_primate': _float('priphylop'),
            'phylop_mammal': _float('mamphylop'),
            'phylop_vertebrate': _float('verphylop'),
            'splice_ai_acc_gain': _float('spliceai-acc-gain'),
            'splice_ai_acc_loss': _float('spliceai-acc-loss'),
            'splice_ai_don_gain': _float('spliceai-don-gain'),
            'splice_ai_don_loss': _float('spliceai-don-loss'),
        }

    @staticmethod
    def _alleles_match(row_ref: str, row_alt: str, marker_ref: str, marker_alt: str) -> bool:
        """Check if CADD row alleles match the user's marker alleles.

        Handles cases where the marker alt_alleles may be comma-separated.
        """
        if row_ref.upper() != marker_ref.upper():
            return False
        # marker_alt may be comma-separated (e.g. "A,G")
        for alt in marker_alt.split(','):
            if row_alt.upper() == alt.strip().upper():
                return True
        return False

    @staticmethod
    def _interpret_cadd(phred: Optional[float]) -> Optional[str]:
        if phred is None:
            return None
        if phred >= 30:
            return "Very high pathogenicity (top 0.1%)"
        if phred >= 20:
            return "High pathogenicity (top 1%)"
        if phred >= 15:
            return "Moderate pathogenicity (top ~3%)"
        if phred >= 10:
            return "Low pathogenicity (top ~10%)"
        return "Likely benign"

    def _format_result(self, parsed: Dict[str, Any], rsid: str) -> Dict[str, Any]:
        """Format parsed CADD row into the standard gnomad_data dict."""
        data: Dict[str, Any] = {
            'found': True,
            'source': 'gnomad_local',
            'rsid': rsid,
            'chrom': parsed['chrom'],
            'pos': parsed['pos'],
            'ref': parsed['ref'],
            'alt': parsed['alt'],
            'variant_id': f"{parsed['chrom']}-{parsed['pos']}-{parsed['ref']}-{parsed['alt']}",
            'variant_type': parsed.get('variant_type'),
            'gene': parsed.get('gene'),
            'consequence': parsed.get('consequence'),
        }

        # CADD scores
        cadd_phred = parsed.get('cadd_phred')
        cadd_raw = parsed.get('cadd_raw')
        if cadd_phred is not None or cadd_raw is not None:
            data['cadd'] = {
                'raw': cadd_raw,
                'phred': cadd_phred,
                'interpretation': self._interpret_cadd(cadd_phred),
            }

        # Functional predictions
        predictions = {}
        if parsed.get('sift_cat') is not None:
            predictions['sift'] = {'category': parsed['sift_cat'], 'score': parsed.get('sift_val')}
        if parsed.get('polyphen_cat') is not None:
            predictions['polyphen'] = {'category': parsed['polyphen_cat'], 'score': parsed.get('polyphen_val')}
        if predictions:
            data['predictions'] = predictions

        # Conservation
        conservation = {}
        for key, field in [('primate', 'phylop_primate'), ('mammal', 'phylop_mammal'), ('vertebrate', 'phylop_vertebrate')]:
            if parsed.get(field) is not None:
                conservation[key] = parsed[field]
        if conservation:
            data['conservation'] = conservation

        # SpliceAI
        splice_fields = {
            'acceptor_gain': 'splice_ai_acc_gain',
            'acceptor_loss': 'splice_ai_acc_loss',
            'donor_gain': 'splice_ai_don_gain',
            'donor_loss': 'splice_ai_don_loss',
        }
        splice = {}
        for out_key, src_key in splice_fields.items():
            if parsed.get(src_key) is not None:
                splice[out_key] = parsed[src_key]
        if splice:
            scores = [v for v in splice.values() if v is not None]
            splice['max_score'] = max(scores) if scores else None
            data['splice_ai'] = splice

        return data

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not await self.ensure_loaded():
            return None
        row = await asyncio.to_thread(self._lookup_one, rsid)
        if row:
            return row
        return None

    def _lookup_one(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not self._db:
            return None
        row = self._db.execute(
            "SELECT data FROM gnomad_data WHERE rsid = ?", (rsid,)
        ).fetchone()
        if row:
            return json.loads(zlib.decompress(row[0]))
        return None

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not rsids:
            return {}
        if not await self.ensure_loaded():
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, rsids)

    def _lookup_batch_sync(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not self._db:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for start in range(0, len(rsids), 500):
            chunk = rsids[start:start + 500]
            placeholders = ','.join('?' * len(chunk))
            rows = self._db.execute(
                f"SELECT rsid, data FROM gnomad_data WHERE rsid IN ({placeholders})",
                chunk,
            ).fetchall()
            for rsid, blob in rows:
                results[rsid] = json.loads(zlib.decompress(blob))
        return results


# Singleton
_instance: Optional[GnomadCacheService] = None


def get_gnomad_cache_service() -> GnomadCacheService:
    global _instance
    if _instance is None:
        _instance = GnomadCacheService()
    return _instance
