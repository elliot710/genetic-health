"""gnomAD SQLite cache built from tabix-indexed CADD TSV files.

Split out of gnomad_local.py; see the package __init__ for the public surface.
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
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, text as sa_text

from backend.db.database import async_session_factory
from backend.db.models import GeneticMarker
from backend.services.datasource_utils import (
    interpret_cadd,
    get_multi_file_fingerprint,
    save_cache_meta,
    open_cache_db,
    create_cache_db,
    finalize_cache_db,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# gnomAD cache constants (formerly gnomad_cache.py)
# ---------------------------------------------------------------------------

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

_CACHE_BATCH_SIZE = 2000
_TABIX_BATCH = 500


# ---------------------------------------------------------------------------
# GnomadCacheService — SQLite cache built from tabix-indexed gnomAD CADD TSVs
# ---------------------------------------------------------------------------

class GnomadCacheService:
    """SQLite-backed gnomAD CADD cache built from tabix-indexed TSV files."""

    def __init__(self):
        self._db: Optional[sqlite3.Connection] = None
        self._variant_count: int = 0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._tsv_files: Optional[List[Path]] = None
        self._genome_build: Optional[str] = None
        self._is_grch38: bool = False
        self._is_indel_only: bool = False
        # True after a full tabix→SQLite scan was completed (or loaded from disk).
        # When True, any rsid not in the SQLite cache is guaranteed NOT to be in
        # gnomAD — no need to re-run the expensive tabix fallback path.
        self._full_scan_done: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._db is not None

    @property
    def variant_count(self) -> int:
        return self._variant_count

    async def ensure_loaded(self) -> bool:
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

    async def _get_marker_fingerprint(self) -> str:
        async with async_session_factory() as session:
            result = await session.execute(select(func.count(GeneticMarker.id)))
            marker_count = result.scalar() or 0
            r2 = await session.execute(sa_text(
                "SELECT COUNT(*) FROM shared_variant_annotations "
                "WHERE ensembl_data IS NOT NULL "
                "AND ensembl_data::text != 'null' "
                "AND (ensembl_data::jsonb)->>'found' = 'true'"
            ))
            ensembl_count = r2.scalar() or 0
        return f"{marker_count}:{ensembl_count}"

    def _discover_tsv_files(self) -> List[Path]:
        files = []
        if not _GNOMAD_DATA_DIR.exists():
            return files
        for p in sorted(_GNOMAD_DATA_DIR.iterdir()):
            if p.name.endswith('.tsv.gz') and 'constraint' not in p.name.lower():
                if Path(str(p) + '.tbi').exists():
                    files.append(p)
        return files

    def _detect_genome_build(self, tsv_path: Path) -> Optional[str]:
        try:
            with gzip.open(str(tsv_path), 'rt', encoding='utf-8', errors='replace') as fh:
                for i, line in enumerate(fh):
                    if i > 60:
                        break
                    if not line.startswith('#'):
                        break
                    for build_tag in ('GRCh38', 'GRCh37', 'hg38', 'hg19'):
                        if build_tag in line:
                            for token in line.split():
                                if build_tag in token:
                                    return token.strip().strip(',')
                            return build_tag
        except Exception as e:
            logger.debug("gnomAD build detection failed for %s: %s", tsv_path.name, e)
        return None

    async def _load_known_positions(
        self, genome_build: Optional[str] = None,
    ) -> Dict[Tuple[str, int], List[Tuple[str, str, str]]]:
        need_liftover = genome_build is not None and 'GRCh38' in genome_build
        if need_liftover:
            return await self._load_grch38_positions_from_ensembl()
        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    GeneticMarker.rsid, GeneticMarker.chromosome,
                    GeneticMarker.position, GeneticMarker.ref_allele, GeneticMarker.alt_alleles,
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

    async def _load_grch38_positions_from_ensembl(
        self,
    ) -> Dict[Tuple[str, int], List[Tuple[str, str, str]]]:
        pos_map: Dict[Tuple[str, int], List[Tuple[str, str, str]]] = {}
        BATCH = 50000
        async with async_session_factory() as session:
            r = await session.execute(sa_text(
                "SELECT COUNT(*) FROM shared_variant_annotations "
                "WHERE ensembl_data IS NOT NULL AND ensembl_data::text != 'null' "
                "AND (ensembl_data::jsonb)->>'found' = 'true'"
            ))
            total = r.scalar() or 0
            logger.info("gnomAD GRCh38 bridge: extracting positions from %d Ensembl annotations", total)

            offset = 0
            extracted = 0
            while offset < total:
                rows = await session.execute(sa_text(
                    "SELECT rsid, "
                    "  (ensembl_data::jsonb)->'data'->0->>'seq_region_name' AS chrom, "
                    "  ((ensembl_data::jsonb)->'data'->0->>'start')::int AS pos, "
                    "  (ensembl_data::jsonb)->'data'->0->>'allele_string' AS allele_str "
                    "FROM shared_variant_annotations "
                    "WHERE ensembl_data IS NOT NULL AND ensembl_data::text != 'null' "
                    "AND (ensembl_data::jsonb)->>'found' = 'true' "
                    "ORDER BY rsid LIMIT :limit OFFSET :offset"
                ).bindparams(limit=BATCH, offset=offset))
                batch_rows = rows.all()
                if not batch_rows:
                    break
                for rsid, chrom, pos, allele_str in batch_rows:
                    if not chrom or not pos or not allele_str:
                        continue
                    chrom_clean = str(chrom).replace('chr', '').strip()
                    parts = allele_str.split('/')
                    if len(parts) < 2:
                        continue
                    ref = parts[0].strip()
                    is_indel = ref == '-' or any(
                        a.strip() == '-' for p in parts[1:] for a in p.split(',')
                    )
                    vcf_pos = int(pos) - 1 if is_indel else int(pos)
                    for alt_part in parts[1:]:
                        for alt in alt_part.split(','):
                            alt = alt.strip()
                            if alt:
                                pos_map.setdefault((chrom_clean, vcf_pos), []).append((rsid, ref, alt))
                                extracted += 1
                offset += BATCH
                if offset % 200000 == 0:
                    logger.info("  GRCh38 bridge: %d/%d processed, %d positions extracted",
                                offset, total, len(pos_map))
                await asyncio.sleep(0)
        logger.info("gnomAD GRCh38 bridge: %d unique positions from %d variant-allele pairs",
                    len(pos_map), extracted)
        return pos_map

    async def _load_cache(self):
        tsv_files = self._discover_tsv_files()
        if not tsv_files:
            logger.warning("No tabix-indexed gnomAD TSV files found in %s", _GNOMAD_DATA_DIR)
            return
        self._tsv_files = tsv_files
        # Detect whether available files are indel-only (e.g. gnomAD CADD indel TSV).
        # When True, tabix lookups for SNP variants are skipped — they can never match.
        self._is_indel_only = all('indel' in f.name.lower() for f in tsv_files)
        build = self._detect_genome_build(tsv_files[0])
        is_grch38 = build is not None and 'GRCh38' in build
        self._genome_build = build
        self._is_grch38 = is_grch38
        if is_grch38:
            logger.info("gnomAD CADD file '%s' is %s — will bridge via Ensembl VEP GRCh38 positions",
                        tsv_files[0].name, build)
        if self._is_indel_only:
            logger.info("gnomAD CADD: indel-only data — SNP tabix lookups will be skipped")
        file_fp = get_multi_file_fingerprint(tsv_files)

        # Use existing cache if TSV files are unchanged (marker_fp not required).
        if _SQLITE_FILE.exists() and _META_FILE.exists():
            try:
                meta = json.loads(_META_FILE.read_text())
                if meta.get("file_fingerprint") == file_fp and meta.get("variant_count", 0) > 0:
                    t0 = time.time()
                    self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE, cache_size_mb=32)
                    row = self._db.execute("SELECT COUNT(*) FROM gnomad_data").fetchone()
                    self._variant_count = row[0] if row else 0
                    # Do NOT set _full_scan_done=True here. The disk cache was built
                    # incrementally and covers only a subset of current markers.
                    # Leaving it False allows tabix fallback to run for uncached variants
                    # and grow the SQLite cache with new hits over time.
                    logger.info("gnomAD: opened SQLite cache with %d variants in %.1fs",
                                self._variant_count, time.time() - t0)
                    return
            except Exception:
                pass

        # No valid SQLite cache — files and tabix indexes are available for
        # on-demand queries.  Cache building from genetic_markers positions is
        # no longer performed here; local_annotation.py uses lookup_batch_by_position
        # with variant positions from the current analysis.
        if self._tsv_files:
            logger.info(
                "gnomAD: no pre-built SQLite cache — %d CADD TSV file(s) available for tabix queries",
                len(self._tsv_files),
            )
        return

    async def build_full_cache(self, *, progress_callback=None) -> Dict[str, Any]:
        """Build (or rebuild) the SQLite cache with a sequential chromosome scan.

        This is far faster than per-variant tabix seeks for large marker sets:
        - Sequential scan: read 19 GB once per file (~38s at 500 MB/s)
        - Random seeks:    609 K seeks × ~0.5 ms = ~5 min per file

        After this completes, all analysis lookups hit SQLite (sub-second).
        Called by the admin worker job 'gnomad_build_cadd_cache'.
        """
        if not self._tsv_files:
            raise RuntimeError("No gnomAD CADD TSV files found — cannot build cache")

        t0 = time.time()
        logger.info("gnomAD CADD cache build: loading marker positions from database…")
        if self._is_grch38:
            pos_map = await self._load_grch38_positions_from_ensembl()
        else:
            pos_map = await self._load_known_positions(genome_build=None)

        total_markers = sum(len(v) for v in pos_map.values())
        logger.info(
            "gnomAD CADD cache build: %d unique positions / %d marker-allele pairs",
            len(pos_map), total_markers,
        )
        if progress_callback:
            progress_callback("positions_loaded", len(pos_map), time.time() - t0)

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        variant_count = await asyncio.to_thread(
            self._scan_tabix_to_sqlite, self._tsv_files, pos_map,
        )

        # Persist metadata so _load_cache() opens this cache on next startup.
        file_fp = get_multi_file_fingerprint(self._tsv_files)
        save_cache_meta(_META_FILE, marker_fp="full_build", file_fp=file_fp, count=variant_count)

        # Hot-reload the freshly built cache into memory.
        self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE, cache_size_mb=64)
        self._variant_count = variant_count
        self._full_scan_done = True
        elapsed = time.time() - t0
        logger.info(
            "gnomAD CADD cache build complete: %d variants cached in %.1fs",
            variant_count, elapsed,
        )
        if progress_callback:
            progress_callback("complete", variant_count, elapsed)
        return {"variant_count": variant_count, "positions_scanned": len(pos_map), "elapsed_s": round(elapsed, 1)}

    def _scan_tabix_to_sqlite(
        self, tsv_files: List[Path], pos_map: Dict[Tuple[str, int], List[Tuple[str, str, str]]]
    ) -> int:
        import pysam
        conn = create_cache_db(_SQLITE_FILE, "CREATE TABLE gnomad_data (rsid TEXT PRIMARY KEY, data BLOB NOT NULL)")
        t0 = time.time()
        total = 0
        batch: list = []
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
            try:
                available_contigs = list(tabix.contigs)
            except Exception:
                available_contigs = []
            col_map = self._parse_header(tabix)
            if not col_map:
                tabix.close()
                continue
            chrom_idx = col_map.get('chrom', col_map.get('chr', col_map.get('#chrom')))
            pos_idx = col_map.get('pos', col_map.get('position'))

            for contig in available_contigs:
                chrom_key = contig.replace('chr', '') if contig.startswith('chr') else contig
                known_positions = pos_set.get(chrom_key)
                if not known_positions:
                    continue
                chrom_t0 = time.time()
                chrom_count = 0
                try:
                    for row_str in tabix.fetch(contig):
                        rows_scanned += 1
                        if pos_idx is not None:
                            fields = row_str.split('\t', pos_idx + 2)
                            if len(fields) > pos_idx:
                                try:
                                    row_pos = int(fields[pos_idx])
                                except (ValueError, TypeError):
                                    continue
                                if row_pos not in known_positions:
                                    continue
                        parsed = self._parse_cadd_row(row_str, col_map)
                        if parsed is None:
                            continue
                        variants_at_pos = pos_map.get((chrom_key, parsed['pos']))
                        if not variants_at_pos:
                            continue
                        for rsid, ref, alt in variants_at_pos:
                            if self._alleles_match(parsed['ref'], parsed['alt'], ref, alt):
                                data = self._format_result(parsed, rsid)
                                blob = zlib.compress(json.dumps(data).encode('utf-8'), level=1)
                                batch.append((rsid, blob))
                                chrom_count += 1
                                if len(batch) >= _CACHE_BATCH_SIZE:
                                    conn.executemany("INSERT OR REPLACE INTO gnomad_data (rsid, data) VALUES (?, ?)", batch)
                                    conn.commit()
                                    batch.clear()
                except Exception as e:
                    logger.debug("gnomAD tabix contig %s error: %s", contig, e)
                    continue
                file_count += chrom_count
                if chrom_count > 0:
                    print(f"[gnomAD]   chr{chrom_key}: {chrom_count} matches in {time.time() - chrom_t0:.1f}s", flush=True)

            tabix.close()
            if batch:
                conn.executemany("INSERT OR REPLACE INTO gnomad_data (rsid, data) VALUES (?, ?)", batch)
                conn.commit()
                batch.clear()
            total += file_count
            print(f"[gnomAD]   [{fi}/{len(tsv_files)}] {tsv_path.name}: {rows_scanned:,} rows scanned, {file_count} matches in {time.time() - file_t0:.1f}s", flush=True)

        msg = f"gnomAD scan complete: {total} variants from {len(tsv_files)} files in {time.time() - t0:.1f}s"
        print(f"[gnomAD] {msg}", flush=True)
        logger.info(msg)
        finalize_cache_db(conn, _SQLITE_FILE.with_suffix('.tmp'), _SQLITE_FILE)
        try:
            db = open_cache_db(_SQLITE_FILE, cache_size_mb=32)
            row = db.execute("SELECT COUNT(*) FROM gnomad_data").fetchone()
            unique_count = row[0] if row else total
            db.close()
        except Exception:
            unique_count = total
        return unique_count

    def _parse_header(self, tabix) -> Optional[Dict[str, int]]:
        try:
            header_line = tabix.header
            if header_line:
                for line in header_line:
                    line = line if isinstance(line, str) else line.decode('utf-8')
                    if not line.startswith('##'):
                        parts = line.strip().split('\t')
                        return {name.strip().lstrip('#').lower(): i for i, name in enumerate(parts)}
        except Exception:
            pass
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
            'chrom': chrom, 'pos': pos, 'ref': ref, 'alt': alt,
            'variant_type': _get('type'),
            'gene': _get('genename') or _get('gene') or _get('gene_symbol'),
            'consequence': _get('consequence'),
            'cadd_raw': _float('rawscore'), 'cadd_phred': _float('phred'),
            'sift_cat': _get('siftcat'), 'sift_val': _float('siftval'),
            'polyphen_cat': _get('polyphencat'), 'polyphen_val': _float('polyphenval'),
            'phylop_primate': _float('priphylop'), 'phylop_mammal': _float('mamphylop'),
            'phylop_vertebrate': _float('verphylop'),
            'splice_ai_acc_gain': _float('spliceai-acc-gain'),
            'splice_ai_acc_loss': _float('spliceai-acc-loss'),
            'splice_ai_don_gain': _float('spliceai-don-gain'),
            'splice_ai_don_loss': _float('spliceai-don-loss'),
        }

    @staticmethod
    def _alleles_match(row_ref: str, row_alt: str, marker_ref: str, marker_alt: str) -> bool:
        rr, ra, mr = row_ref.upper(), row_alt.upper(), marker_ref.upper()
        if mr == '-':
            for alt in marker_alt.split(','):
                alt = alt.strip().upper()
                if alt and alt != '-' and ra == rr + alt:
                    return True
            return False
        alts = [a.strip().upper() for a in marker_alt.split(',')]
        if '-' in alts:
            if rr == ra + mr:
                return True
            for alt in alts:
                if alt != '-' and ra == alt:
                    return True
            return False
        if rr != mr:
            return False
        return any(ra == a for a in alts)

    def _format_result(self, parsed: Dict[str, Any], rsid: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            'found': True, 'source': 'gnomad_local', 'rsid': rsid,
            'chrom': parsed['chrom'], 'pos': parsed['pos'], 'ref': parsed['ref'], 'alt': parsed['alt'],
            'variant_id': f"{parsed['chrom']}-{parsed['pos']}-{parsed['ref']}-{parsed['alt']}",
            'variant_type': parsed.get('variant_type'),
            'gene': parsed.get('gene'), 'consequence': parsed.get('consequence'),
        }
        cadd_phred, cadd_raw = parsed.get('cadd_phred'), parsed.get('cadd_raw')
        if cadd_phred is not None or cadd_raw is not None:
            data['cadd'] = {'raw': cadd_raw, 'phred': cadd_phred, 'interpretation': interpret_cadd(cadd_phred)}
        predictions = {}
        if parsed.get('sift_cat') is not None:
            predictions['sift'] = {'category': parsed['sift_cat'], 'score': parsed.get('sift_val')}
        if parsed.get('polyphen_cat') is not None:
            predictions['polyphen'] = {'category': parsed['polyphen_cat'], 'score': parsed.get('polyphen_val')}
        if predictions:
            data['predictions'] = predictions
        conservation = {k: parsed[f] for k, f in [('primate', 'phylop_primate'), ('mammal', 'phylop_mammal'), ('vertebrate', 'phylop_vertebrate')] if parsed.get(f) is not None}
        if conservation:
            data['conservation'] = conservation
        splice = {k: parsed[f] for k, f in [('acceptor_gain', 'splice_ai_acc_gain'), ('acceptor_loss', 'splice_ai_acc_loss'), ('donor_gain', 'splice_ai_don_gain'), ('donor_loss', 'splice_ai_don_loss')] if parsed.get(f) is not None}
        if splice:
            scores = [v for v in splice.values() if v is not None]
            splice['max_score'] = max(scores) if scores else None
            data['splice_ai'] = splice
        return data

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not await self.ensure_loaded():
            return None
        return await asyncio.to_thread(self._lookup_one, rsid)

    def _lookup_one(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not self._db:
            return None
        row = self._db.execute("SELECT data FROM gnomad_data WHERE rsid = ?", (rsid,)).fetchone()
        return json.loads(zlib.decompress(row[0])) if row else None

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
                f"SELECT rsid, data FROM gnomad_data WHERE rsid IN ({placeholders})", chunk
            ).fetchall()
            for rsid, blob in rows:
                results[rsid] = json.loads(zlib.decompress(blob))
        return results

    @property
    def has_tabix_files(self) -> bool:
        return bool(self._tsv_files)

    async def tabix_lookup(
        self, rsid: str, chrom: str, pos: int, ref: str, alt: str,
    ) -> Optional[Dict[str, Any]]:
        if not self._tsv_files:
            return None
        result = await asyncio.to_thread(self._tabix_fetch_one, rsid, chrom, pos, ref, alt)
        if result:
            await asyncio.to_thread(self._cache_tabix_results, [(rsid, result)])
        return result

    async def tabix_lookup_batch(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        if not variants or not self._tsv_files:
            return {}
        results = await asyncio.to_thread(self._tabix_fetch_batch, variants)
        to_cache = [(rsid, data) for rsid, data in results.items() if data and data.get('found')]
        if to_cache:
            await asyncio.to_thread(self._cache_tabix_results, to_cache)
        return results

    def _tabix_fetch_one(self, rsid: str, chrom: str, pos: int, ref: str, alt: str) -> Optional[Dict[str, Any]]:
        import pysam
        chrom_clean = chrom.replace('chr', '')
        for tsv_path in (self._tsv_files or []):
            try:
                tabix = pysam.TabixFile(str(tsv_path))
                col_map = self._parse_header(tabix)
                if not col_map:
                    tabix.close()
                    continue
                contigs = set(tabix.contigs)
                contig = next((c for c in [chrom_clean, f'chr{chrom_clean}'] if c in contigs), None)
                if contig is None:
                    tabix.close()
                    continue
                try:
                    for row_str in tabix.fetch(contig, max(0, pos - 1), pos + 1):
                        parsed = self._parse_cadd_row(row_str, col_map)
                        if parsed is None or parsed['pos'] != pos:
                            continue
                        for a in alt.split(','):
                            a = a.strip()
                            if a and self._alleles_match(parsed['ref'], parsed['alt'], ref, a):
                                tabix.close()
                                return self._format_result(parsed, rsid)
                except ValueError:
                    pass
                tabix.close()
            except Exception as e:
                logger.debug("tabix on-demand error for %s in %s: %s", rsid, tsv_path.name, e)
        return None

    def _tabix_fetch_batch(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        import pysam
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        pos_map: Dict[Tuple[str, int], List[Tuple[str, str, str]]] = {}
        for rsid, chrom, pos, ref, alt in variants:
            pos_map.setdefault((chrom.replace('chr', ''), int(pos)), []).append((rsid, ref, alt))
        for tsv_path in (self._tsv_files or []):
            try:
                tabix = pysam.TabixFile(str(tsv_path))
                col_map = self._parse_header(tabix)
                if not col_map:
                    tabix.close()
                    continue
                contigs = set(tabix.contigs)
                for (chrom_clean, pos), variant_list in pos_map.items():
                    if all(r in results for r, _, _ in variant_list):
                        continue
                    contig = next((c for c in [chrom_clean, f'chr{chrom_clean}'] if c in contigs), None)
                    if contig is None:
                        continue
                    try:
                        for row_str in tabix.fetch(contig, max(0, pos - 1), pos + 1):
                            parsed = self._parse_cadd_row(row_str, col_map)
                            if parsed is None or parsed['pos'] != pos:
                                continue
                            for rsid, ref, alt in variant_list:
                                if rsid in results:
                                    continue
                                for a in alt.split(','):
                                    a = a.strip()
                                    if a and self._alleles_match(parsed['ref'], parsed['alt'], ref, a):
                                        results[rsid] = self._format_result(parsed, rsid)
                                        break
                    except ValueError:
                        pass
                tabix.close()
            except Exception as e:
                logger.debug("tabix batch error in %s: %s", tsv_path.name, e)
        return results

    def _cache_tabix_results(self, entries: List[Tuple[str, Dict[str, Any]]]):
        if not self._db or not entries:
            return
        try:
            batch = [(rsid, zlib.compress(json.dumps(data).encode('utf-8'), level=1)) for rsid, data in entries]
            self._db.executemany("INSERT OR REPLACE INTO gnomad_data (rsid, data) VALUES (?, ?)", batch)
            self._db.commit()
            self._variant_count += len(batch)
            logger.info("gnomAD: cached %d on-demand tabix results to SQLite", len(batch))
        except Exception as e:
            logger.debug("Failed to cache tabix results: %s", e)


_cache_instance: Optional[GnomadCacheService] = None


def get_gnomad_cache_service() -> GnomadCacheService:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = GnomadCacheService()
    return _cache_instance
