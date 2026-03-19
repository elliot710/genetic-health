"""
gnomAD service — SQLite cache (from tabix CADD TSV files) with PostgreSQL
and BigQuery fallback. Gene constraint lookups use PG.

Usage:
    svc = get_gnomad_service()
    result = await svc.lookup("rs1234")
    result = await svc.lookup_by_position("1", 12345, "A", "G")
"""

from __future__ import annotations

import asyncio
import csv
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
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.models import GnomadVariant, GnomadGeneConstraint, GeneticMarker
from .datasource_utils import (
    interpret_cadd,
    get_multi_file_fingerprint,
    is_cache_valid,
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
        build = self._detect_genome_build(tsv_files[0])
        is_grch38 = build is not None and 'GRCh38' in build
        self._genome_build = build
        self._is_grch38 = is_grch38
        if is_grch38:
            logger.info("gnomAD CADD file '%s' is %s — will bridge via Ensembl VEP GRCh38 positions",
                        tsv_files[0].name, build)
        marker_fp = await self._get_marker_fingerprint()
        file_fp = get_multi_file_fingerprint(tsv_files)
        if is_cache_valid(_SQLITE_FILE, _META_FILE, marker_fp, file_fp):
            t0 = time.time()
            self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE, cache_size_mb=32)
            row = self._db.execute("SELECT COUNT(*) FROM gnomad_data").fetchone()
            self._variant_count = row[0] if row else 0
            self._full_scan_done = True  # Loaded from disk → full scan already done
            logger.info("gnomAD: opened SQLite cache with %d variants in %.1fs",
                        self._variant_count, time.time() - t0)
            return
        logger.info("gnomAD cache miss — scanning %d TSV files at known positions...", len(tsv_files))
        pos_map = await self._load_known_positions(genome_build=build)
        if not pos_map:
            logger.info("No known variant positions — skipping gnomAD cache build")
            return
        count = await asyncio.to_thread(self._scan_tabix_to_sqlite, tsv_files, pos_map)
        save_cache_meta(_META_FILE, marker_fp, file_fp, count)
        self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE, cache_size_mb=32)
        self._variant_count = count
        self._full_scan_done = True  # Just completed a full scan

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


# ---------------------------------------------------------------------------
# GnomadLocalService — main gnomAD service (cache → PG → BigQuery)
# ---------------------------------------------------------------------------

# Population code → human-readable name
_POP_NAMES = {
    "afr": "African/African-American",
    "ami": "Amish",
    "amr": "Latino/Admixed American",
    "asj": "Ashkenazi Jewish",
    "eas": "East Asian",
    "fin": "Finnish",
    "mid": "Middle Eastern",
    "nfe": "Non-Finnish European",
    "sas": "South Asian",
    "remaining": "Remaining",
}


class GnomadLocalService:
    """SQLite-cached gnomAD lookup with PG and BigQuery fallback."""

    def __init__(self):
        self._variant_count: Optional[int] = None
        self._constraint_count: Optional[int] = None
        self._available: Optional[bool] = None
        self._cache = get_gnomad_cache_service()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        # Consider loaded if cache OR PG has data
        if self._cache.is_loaded and self._cache.variant_count > 0:
            return True
        return self._variant_count is not None and self._variant_count > 0

    @property
    def variant_count(self) -> int:
        cache_count = self._cache.variant_count if self._cache.is_loaded else 0
        pg_count = self._variant_count or 0
        return cache_count + pg_count

    @property
    def constraint_count(self) -> int:
        return self._constraint_count or 0

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    async def ensure_loaded(self) -> bool:
        """Check that gnomAD data is available (SQLite cache, PG, or both)."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(GnomadVariant)
                )
                self._variant_count = result.scalar() or 0

                result = await session.execute(
                    select(func.count()).select_from(GnomadGeneConstraint)
                )
                self._constraint_count = result.scalar() or 0

            self._available = self._variant_count > 0 or self._cache.is_loaded
            if self._variant_count > 0:
                logger.info("gnomAD PG: %d variants, %d gene constraints available",
                            self._variant_count, self._constraint_count)
            if self._cache.is_loaded:
                logger.info("gnomAD SQLite cache: %d variants available",
                            self._cache.variant_count)
            if not self._available:
                logger.warning("gnomAD: no data — run ETL import or place TSV files in data_sources/gnomad/")
            return self._available
        except Exception as e:
            logger.warning("gnomAD PG check failed: %s", e)
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Core lookups
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str, *, local_only: bool = False) -> Optional[Dict[str, Any]]:
        """Look up a variant by rsID. Tries cache → PG → tabix files → BigQuery."""
        # Try SQLite cache first (fastest)
        if self._cache.is_loaded:
            cached = await self._cache.lookup(rsid)
            if cached and cached.get('found'):
                return cached

        # Try local PG (skip when PG is known empty — PERF-01)
        if self._variant_count is None or self._variant_count > 0:
            async with async_session_factory() as session:
                result = await self._lookup_by_rsid(session, rsid)
                if result and result.get('found'):
                    return result

        # Try on-demand tabix file lookup (DATA-01 fix)
        if self._cache.has_tabix_files:
            tabix_result = await self._tabix_lookup_for_rsid(rsid)
            if tabix_result and tabix_result.get('found'):
                return tabix_result

        if local_only:
            return {"found": False, "source": "gnomad", "rsid": rsid}

        # Fall back to BigQuery
        bq_result = await self._try_bigquery_rsid(rsid)
        if bq_result:
            return bq_result

        return {"found": False, "source": "gnomad", "rsid": rsid}

    async def lookup_by_position(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Look up by genomic coordinates. Tries local PG → tabix files → BigQuery."""
        chrom = chrom.replace("chr", "")

        async with async_session_factory() as session:
            result = await self._lookup_by_pos(session, chrom, pos, ref, alt)
            if result and result.get('found'):
                return result

        # Try on-demand tabix file lookup (DATA-01 fix)
        if self._cache.has_tabix_files:
            tabix_result = await self._cache.tabix_lookup(
                f"{chrom}-{pos}-{ref}-{alt}", chrom, pos, ref, alt,
            )
            if tabix_result and tabix_result.get('found'):
                return tabix_result

        # Fall back to BigQuery
        bq_result = await self._try_bigquery_pos(chrom, pos, ref, alt)
        if bq_result:
            return bq_result

        return {"found": False, "source": "gnomad", "chrom": chrom, "pos": pos}

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by rsIDs. Tries cache → PG → tabix files. Returns {rsid: result_or_none}."""
        if not rsids:
            return {}

        results: Dict[str, Optional[Dict[str, Any]]] = {}

        # 1) Try SQLite cache first — returns all hits
        remaining = list(rsids)
        if self._cache.is_loaded:
            cached = await self._cache.lookup_batch(remaining)
            for rsid, data in cached.items():
                if data and data.get('found'):
                    results[rsid] = data
            remaining = [r for r in remaining if r not in results]

        if not remaining:
            return results

        # PERF-01: Skip PG lookup entirely when gnomAD PG table is empty.
        pg_skip = self._variant_count is not None and self._variant_count == 0

        if not pg_skip:
            # 2) Fallback to PG for anything not in cache
            import time as _time
            batch_size = 500
            total_remaining = len(remaining)
            total_batches = (total_remaining + batch_size - 1) // batch_size
            found_count = sum(1 for v in results.values() if v and v.get('found'))
            t0 = _time.monotonic()
            if total_remaining:
                logger.info(f"  gnomAD rsid PG lookup: {total_remaining} remaining after cache ({len(results)} cached hits)")
            async with async_session_factory() as session:
                for i in range(0, total_remaining, batch_size):
                    chunk = remaining[i:i + batch_size]
                    batch_num = i // batch_size + 1
                    if i > 0:
                        await asyncio.sleep(0.05)  # yield to other DB queries
                    result = await session.execute(
                        select(GnomadVariant).where(GnomadVariant.rsid.in_(chunk))
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
                            best = max(row_list, key=lambda r: r.af or 0)
                            data = self._format_variant(best, rsid=rsid_key)
                            data['other_alleles'] = [
                                {"alt": r.alt, "af": r.af, "ac": r.ac}
                                for r in row_list if r.id != best.id
                            ]
                            results[rsid_key] = data
                            found_count += 1

                    if batch_num % 50 == 0 or batch_num == total_batches:
                        elapsed = _time.monotonic() - t0
                        rate = (i + len(chunk)) / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"  gnomAD rsid batch {batch_num}/{total_batches}: "
                            f"{i + len(chunk)}/{total_remaining} queried, {found_count} found "
                            f"({rate:.0f} rsids/s, {elapsed:.1f}s elapsed)"
                        )

            if total_remaining:
                elapsed = _time.monotonic() - t0
                logger.info(f"  gnomAD rsid complete: {found_count}/{len(rsids)} found in {elapsed:.1f}s")

        # 3) DATA-01: Tabix file fallback for unfound rsids.
        # Skip when _full_scan_done=True — the SQLite cache was already built by scanning
        # tabix for ALL known positions, so any RSID miss is a true miss (not in gnomAD).
        if self._cache.has_tabix_files and not self._cache._full_scan_done:
            unfound = [r for r in rsids if not (results.get(r) and results[r] and results[r].get('found'))]
            if unfound:
                tabix_results = await self._tabix_batch_for_rsids(unfound)
                tabix_found = 0
                for rsid, data in tabix_results.items():
                    if data and data.get('found'):
                        results[rsid] = data
                        tabix_found += 1
                if tabix_found:
                    logger.info(f"  gnomAD tabix rsid fallback: {tabix_found} additional variants found")

        return results

    async def lookup_batch_by_position(
        self, variants: List[tuple]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by genomic coordinates using the (chrom,pos,ref,alt) unique index.

        Falls back to on-demand tabix file queries when PG is empty (DATA-01).

        Args:
            variants: list of (rsid, chrom, pos, ref_allele, alt_alleles_csv) tuples.
                alt_alleles_csv may contain comma-separated alternatives.

        Returns: {rsid: result_or_none}
        """
        if not variants:
            return {}

        from sqlalchemy import tuple_
        import time as _time

        results: Dict[str, Optional[Dict[str, Any]]] = {}

        # Build lookup entries: (rsid, chrom, pos, ref, alt) — one per alt allele
        entries = []
        key_to_rsid: Dict[tuple, str] = {}  # (chrom, pos, ref, alt) → rsid
        for rsid, chrom, pos, ref, alt_csv in variants:
            c = str(chrom).replace('chr', '')
            p = int(pos)
            r = str(ref)
            if alt_csv:
                for alt in str(alt_csv).split(','):
                    alt = alt.strip()
                    if alt:
                        key = (c, p, r, alt)
                        key_to_rsid.setdefault(key, rsid)
                        entries.append(key)
            # Also try without alt (some markers have no alt_alleles)

        if not entries:
            return results

        batch_size = 500
        total = len(entries)
        total_batches = (total + batch_size - 1) // batch_size
        found_count = 0
        t0 = _time.monotonic()

        # PERF-01: Skip PG lookup entirely when gnomAD PG table is empty.
        pg_skip = self._variant_count is not None and self._variant_count == 0
        if pg_skip:
            logger.debug("gnomAD pos lookup: skipping PG (table empty)")
        else:
            async with async_session_factory() as session:
                for i in range(0, len(entries), batch_size):
                    chunk = entries[i:i + batch_size]
                    batch_num = i // batch_size + 1
                    if i > 0:
                        await asyncio.sleep(0.05)  # yield to other DB queries

                    result = await session.execute(
                        select(GnomadVariant).where(
                            tuple_(
                                GnomadVariant.chrom,
                                GnomadVariant.pos,
                                GnomadVariant.ref,
                                GnomadVariant.alt,
                            ).in_(chunk)
                        )
                    )
                    rows = result.scalars().all()
                    for row in rows:
                        key = (row.chrom, row.pos, row.ref, row.alt)
                        rsid = key_to_rsid.get(key)
                        if rsid and rsid not in results:
                            results[rsid] = self._format_variant(row, rsid=rsid)
                            found_count += 1

                    if batch_num % 50 == 0 or batch_num == total_batches:
                        elapsed = _time.monotonic() - t0
                        rate = (i + len(chunk)) / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"  gnomAD pos batch {batch_num}/{total_batches}: "
                            f"{i + len(chunk)}/{total} queried, {found_count} found "
                            f"({rate:.0f} pos/s, {elapsed:.1f}s elapsed)"
                        )

        # DATA-01: Tabix file fallback for unfound variants.
        # Skip when the cache full_scan_done flag is set — the SQLite cache was already
        # built by scanning tabix for ALL known positions, so any miss is a true miss.
        if self._cache.has_tabix_files and not self._cache._full_scan_done:
            unfound_tuples = []
            for rsid, chrom, pos, ref, alt_csv in variants:
                if rsid in results and results[rsid] and results[rsid].get('found'):
                    continue
                c = str(chrom).replace('chr', '')
                p = int(pos)
                r = str(ref)
                for alt in str(alt_csv or '').split(','):
                    alt = alt.strip()
                    if alt:
                        unfound_tuples.append((rsid, c, p, r, alt))
                        break

            if unfound_tuples:
                # GRCh38 files need coordinate translation
                if self._cache._is_grch38:
                    unfound_tuples = await self._translate_to_grch38(unfound_tuples)

                if unfound_tuples:
                    tabix_results = await self._cache.tabix_lookup_batch(unfound_tuples)
                    tabix_found = 0
                    for rsid, data in tabix_results.items():
                        if data and data.get('found'):
                            results[rsid] = data
                            found_count += 1
                            tabix_found += 1
                    if tabix_found:
                        logger.info("  gnomAD tabix fallback: %d additional variants found",
                                    tabix_found)

        elapsed = _time.monotonic() - t0
        logger.info(f"  gnomAD complete: {found_count}/{total} found in {elapsed:.1f}s")
        return results

    async def get_gene_constraint(self, gene: str) -> Optional[Dict[str, Any]]:
        """Get gene-level constraint metrics."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(GnomadGeneConstraint).where(GnomadGeneConstraint.gene == gene)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            return {
                "gene": row.gene,
                "transcript": row.transcript,
                "pli": row.pli,
                "loeuf": row.loeuf,
                "mis_z": row.mis_z,
                "syn_z": row.syn_z,
                "obs_lof": row.obs_lof,
                "exp_lof": row.exp_lof,
                "obs_mis": row.obs_mis,
                "exp_mis": row.exp_mis,
                "obs_syn": row.obs_syn,
                "exp_syn": row.exp_syn,
                "interpretation": self._interpret_constraint(row.pli, row.loeuf),
            }

    # ------------------------------------------------------------------
    # Tabix file fallback helpers (DATA-01)
    # ------------------------------------------------------------------

    async def _tabix_batch_for_rsids(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Get coordinates from genetic_markers for a batch of rsids and do tabix lookup."""
        from ..db.models import GeneticMarker

        # Fetch coordinates for all unfound rsids
        tuples: List[tuple] = []
        batch_size = 2000
        for i in range(0, len(rsids), batch_size):
            chunk = rsids[i:i + batch_size]
            if i > 0:
                await asyncio.sleep(0)
            async with async_session_factory() as session:
                result = await session.execute(
                    select(
                        GeneticMarker.rsid,
                        GeneticMarker.chromosome,
                        GeneticMarker.position,
                        GeneticMarker.ref_allele,
                        GeneticMarker.alt_alleles,
                    ).where(
                        GeneticMarker.rsid.in_(chunk),
                        GeneticMarker.chromosome.isnot(None),
                        GeneticMarker.position.isnot(None),
                    )
                )
                for row in result.all():
                    chrom = str(row.chromosome).replace('chr', '')
                    ref = str(row.ref_allele or '')
                    alt = str(row.alt_alleles or '')
                    if alt and ref != alt:  # Skip ambiguous markers
                        tuples.append((row.rsid, chrom, int(row.position), ref, alt))

        if not tuples:
            return {}

        # GRCh38 coordinate translation if needed
        if self._cache._is_grch38:
            tuples = await self._translate_to_grch38(tuples)

        if not tuples:
            return {}

        return await self._cache.tabix_lookup_batch(tuples)

    async def _tabix_lookup_for_rsid(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get coordinates from genetic_markers and do on-demand tabix lookup."""
        from ..db.models import GeneticMarker

        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    GeneticMarker.chromosome,
                    GeneticMarker.position,
                    GeneticMarker.ref_allele,
                    GeneticMarker.alt_alleles,
                ).where(GeneticMarker.rsid == rsid)
            )
            row = result.first()
            if not row or not row.chromosome or not row.position:
                return None

            chrom = str(row.chromosome).replace('chr', '')
            pos = int(row.position)
            ref = str(row.ref_allele or '')
            alt = str(row.alt_alleles or '')

            # If tabix files are GRCh38 but marker positions are GRCh37,
            # try to get GRCh38 coordinates from Ensembl VEP annotations
            if self._cache._is_grch38:
                translated = await self._translate_to_grch38(
                    [(rsid, chrom, pos, ref, alt)]
                )
                if not translated:
                    return None
                _, chrom, pos, ref, alt = translated[0]

            return await self._cache.tabix_lookup(rsid, chrom, pos, ref, alt)

    async def _translate_to_grch38(
        self,
        variants: List[tuple],
    ) -> List[tuple]:
        """Translate GRCh37 variant positions to GRCh38 using Ensembl VEP annotations.

        Returns: [(rsid, chrom_38, pos_38, ref_38, alt_38), ...]
        Only variants with available Ensembl VEP data are returned.
        """
        from ..db.models import SharedVariantAnnotation

        rsids = list({v[0] for v in variants})
        translated = []

        async with async_session_factory() as session:
            for i in range(0, len(rsids), 500):
                chunk = rsids[i:i + 500]
                result = await session.execute(
                    select(
                        SharedVariantAnnotation.rsid,
                        SharedVariantAnnotation.ensembl_data,
                    ).where(
                        SharedVariantAnnotation.rsid.in_(chunk),
                        SharedVariantAnnotation.ensembl_data.isnot(None),
                    )
                )
                for row in result.all():
                    ensembl = row.ensembl_data
                    if not ensembl or not isinstance(ensembl, dict):
                        continue
                    found_val = ensembl.get('found')
                    if found_val not in ('true', True):
                        continue
                    data = ensembl.get('data', [])
                    if not data:
                        continue
                    entry = data[0] if isinstance(data, list) else data
                    e_chrom = entry.get('seq_region_name')
                    e_pos = entry.get('start')
                    allele_str = entry.get('allele_string', '')
                    parts = allele_str.split('/')
                    if not e_chrom or not e_pos or len(parts) < 2:
                        continue
                    chrom_clean = str(e_chrom).replace('chr', '').strip()
                    ref = parts[0].strip()
                    alt = parts[1].strip()
                    is_indel = ref == '-' or alt == '-'
                    vcf_pos = int(e_pos) - 1 if is_indel else int(e_pos)
                    translated.append((row.rsid, chrom_clean, vcf_pos, ref, alt))

        if translated:
            logger.info(
                "gnomAD GRCh38 bridge: translated %d/%d variants for tabix lookup",
                len(translated), len(variants),
            )
        return translated

    # ------------------------------------------------------------------
    # Internal PG lookups
    # ------------------------------------------------------------------

    async def _lookup_by_rsid(self, session: AsyncSession, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up all gnomAD rows for an rsID."""
        result = await session.execute(
            select(GnomadVariant).where(GnomadVariant.rsid == rsid)
        )
        rows = result.scalars().all()

        if not rows:
            return None

        # Take the first row (most common case: one variant per rsID)
        # If multiple alleles, aggregate
        if len(rows) == 1:
            return self._format_variant(rows[0], rsid=rsid)
        else:
            # Multiple alt alleles — return the most common one
            best = max(rows, key=lambda r: r.af or 0)
            data = self._format_variant(best, rsid=rsid)
            data['other_alleles'] = [
                {"alt": r.alt, "af": r.af, "ac": r.ac}
                for r in rows if r.id != best.id
            ]
            return data

    async def _lookup_by_pos(
        self, session: AsyncSession, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Look up by exact chrom-pos-ref-alt."""
        result = await session.execute(
            select(GnomadVariant).where(
                GnomadVariant.chrom == chrom,
                GnomadVariant.pos == pos,
                GnomadVariant.ref == ref,
                GnomadVariant.alt == alt,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return self._format_variant(row)

    # ------------------------------------------------------------------
    # BigQuery fallback
    # ------------------------------------------------------------------

    async def _try_bigquery_rsid(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Try BigQuery lookup by rsID, cache result locally if found."""
        try:
            from .gnomad_bigquery import get_gnomad_bigquery_service
            bq = get_gnomad_bigquery_service()
            if not await bq.is_available():
                return None

            result = await bq.lookup_rsid(rsid)
            if result and result.get('found'):
                result['source'] = 'gnomad_bigquery'
                # Cache locally for future lookups
                await self._cache_bigquery_result(result, rsid=rsid)
            return result
        except Exception as e:
            logger.debug("BigQuery rsid fallback failed for %s: %s", rsid, e)
            return None

    async def _try_bigquery_pos(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        """Try BigQuery lookup by position, cache result locally if found."""
        try:
            from .gnomad_bigquery import get_gnomad_bigquery_service
            bq = get_gnomad_bigquery_service()
            if not await bq.is_available():
                return None

            result = await bq.lookup_variant(chrom, pos, ref, alt)
            if result and result.get('found'):
                result['source'] = 'gnomad_bigquery'
                await self._cache_bigquery_result(result)
            return result
        except Exception as e:
            logger.debug("BigQuery pos fallback failed for %s:%d: %s", chrom, pos, e)
            return None

    async def _cache_bigquery_result(
        self, data: Dict[str, Any], rsid: Optional[str] = None
    ):
        """Cache a BigQuery result into the local gnomad_variants table."""
        try:
            async with async_session_factory() as session:
                chrom = data.get('chrom', '')
                pos = data.get('pos', 0)
                ref = data.get('ref', '')
                alt = data.get('alt', '')

                # Check if already exists
                existing = await session.execute(
                    select(GnomadVariant).where(
                        GnomadVariant.chrom == chrom,
                        GnomadVariant.pos == pos,
                        GnomadVariant.ref == ref,
                        GnomadVariant.alt == alt,
                    )
                )
                if existing.scalar_one_or_none():
                    return  # Already cached

                pop = data.get('population_frequencies', {})
                variant = GnomadVariant(
                    chrom=chrom,
                    pos=pos,
                    ref=ref,
                    alt=alt,
                    rsid=rsid or data.get('rsid'),
                    variant_id=data.get('variant_id', f"{chrom}-{pos}-{ref}-{alt}"),
                    af=data.get('af'),
                    ac=data.get('ac'),
                    an=data.get('an'),
                    nhomalt=data.get('nhomalt'),
                    af_afr=pop.get('afr', {}).get('af'),
                    af_ami=pop.get('ami', {}).get('af'),
                    af_amr=pop.get('amr', {}).get('af'),
                    af_asj=pop.get('asj', {}).get('af'),
                    af_eas=pop.get('eas', {}).get('af'),
                    af_fin=pop.get('fin', {}).get('af'),
                    af_mid=pop.get('mid', {}).get('af'),
                    af_nfe=pop.get('nfe', {}).get('af'),
                    af_sas=pop.get('sas', {}).get('af'),
                    af_remaining=pop.get('remaining', {}).get('af'),
                    gene=data.get('gene'),
                    consequence=data.get('consequence'),
                    impact=data.get('impact'),
                    data_source='bigquery',
                )
                session.add(variant)
                await session.commit()
                logger.debug("Cached BigQuery result for %s-%s-%s-%s", chrom, pos, ref, alt)
        except Exception as e:
            logger.debug("Failed to cache BigQuery result: %s", e)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_variant(self, row: GnomadVariant, rsid: Optional[str] = None) -> Dict[str, Any]:
        """Format a DB row into the standard gnomad_data dict."""
        pop_freqs = {}
        for code, name in _POP_NAMES.items():
            val = getattr(row, f'af_{code}', None)
            if val is not None:
                pop_freqs[code] = {"name": name, "af": val}

        data: Dict[str, Any] = {
            "found": True,
            "source": "gnomad_local" if row.data_source in ('tsv', None) else f"gnomad_{row.data_source}",
            "rsid": rsid or row.rsid,
            "chrom": row.chrom,
            "pos": row.pos,
            "ref": row.ref,
            "alt": row.alt,
            "variant_id": row.variant_id or f"{row.chrom}-{row.pos}-{row.ref}-{row.alt}",
            "variant_type": row.variant_type,
            "filter_status": row.filter_status,
            "af": row.af,
            "ac": row.ac,
            "an": row.an,
            "nhomalt": row.nhomalt,
            "population_frequencies": pop_freqs,
            "gene": row.gene,
            "consequence": row.consequence,
            "impact": row.impact,
            "hgvsc": row.hgvsc,
            "hgvsp": row.hgvsp,
        }

        # CADD pathogenicity scores
        if row.cadd_phred is not None or row.cadd_raw is not None:
            data["cadd"] = {
                "raw": row.cadd_raw,
                "phred": row.cadd_phred,
                "interpretation": interpret_cadd(row.cadd_phred),
            }

        # Functional predictions
        if row.sift_cat is not None or row.polyphen_cat is not None:
            data["predictions"] = {}
            if row.sift_cat is not None:
                data["predictions"]["sift"] = {"category": row.sift_cat, "score": row.sift_val}
            if row.polyphen_cat is not None:
                data["predictions"]["polyphen"] = {"category": row.polyphen_cat, "score": row.polyphen_val}

        # Conservation scores
        if any(getattr(row, f, None) is not None for f in ('phylop_primate', 'phylop_mammal', 'phylop_vertebrate')):
            data["conservation"] = {
                "primate": row.phylop_primate,
                "mammal": row.phylop_mammal,
                "vertebrate": row.phylop_vertebrate,
            }

        # SpliceAI scores
        splice_fields = ('splice_ai_acc_gain', 'splice_ai_acc_loss', 'splice_ai_don_gain', 'splice_ai_don_loss')
        if any(getattr(row, f, None) is not None for f in splice_fields):
            data["splice_ai"] = {
                "acceptor_gain": row.splice_ai_acc_gain,
                "acceptor_loss": row.splice_ai_acc_loss,
                "donor_gain": row.splice_ai_don_gain,
                "donor_loss": row.splice_ai_don_loss,
                "max_score": max(
                    (v for v in (row.splice_ai_acc_gain, row.splice_ai_acc_loss,
                                 row.splice_ai_don_gain, row.splice_ai_don_loss) if v is not None),
                    default=None,
                ),
            }

        return data

    @staticmethod
    def _interpret_constraint(pli: Optional[float], loeuf: Optional[float]) -> Optional[str]:
        """Human-readable interpretation of gene constraint scores."""
        if pli is None and loeuf is None:
            return None

        parts = []
        if pli is not None:
            if pli >= 0.9:
                parts.append("highly intolerant to loss-of-function variants (pLI ≥ 0.9)")
            elif pli >= 0.5:
                parts.append("moderately constrained against loss-of-function (pLI ≥ 0.5)")
            else:
                parts.append("tolerant to loss-of-function variants")

        if loeuf is not None:
            if loeuf <= 0.35:
                parts.append("strongly constrained (LOEUF ≤ 0.35)")
            elif loeuf <= 0.6:
                parts.append("moderately constrained (LOEUF ≤ 0.6)")
            else:
                parts.append("less constrained")

        return "; ".join(parts) if parts else None


# Singleton
_instance: Optional[GnomadLocalService] = None


def get_gnomad_service() -> GnomadLocalService:
    global _instance
    if _instance is None:
        _instance = GnomadLocalService()
    return _instance


# ---------------------------------------------------------------------------
# GnomadTxService — transcript annotation + GTEx tissue expression
# (formerly gnomad_tx.py)
# ---------------------------------------------------------------------------

_TX_FILE = "all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz"

# Fields in the tx_annotation JSON that are NOT tissue names
_TX_STANDARD_FIELDS = frozenset({
    "ensg", "csq", "symbol", "lof", "lof_flag", "mean_proportion",
})


class GnomadTxService:
    """Lookup service for gnomAD transcript annotations with GTEx tissue expression.

    Uses pysam.TabixFile for O(log n) random-access lookups by genomic position.
    Data file: all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz
    """

    def __init__(self):
        self._data_dir = _GNOMAD_DATA_DIR
        self._tabix = None
        self._available: Optional[bool] = None

    @property
    def available(self) -> bool:
        if self._available is None:
            bgz = self._data_dir / _TX_FILE
            tbi = self._data_dir / f"{_TX_FILE}.tbi"
            self._available = bgz.exists() and tbi.exists()
            if self._available:
                logger.info("gnomAD tx_annotated data available at %s", self._data_dir)
            else:
                logger.info("gnomAD tx_annotated data not found at %s — disabled", self._data_dir)
        return self._available

    @property
    def is_loaded(self) -> bool:
        return self.available

    def _get_tabix(self):
        if self._tabix is None and self.available:
            import pysam
            self._tabix = pysam.TabixFile(str(self._data_dir / _TX_FILE))
        return self._tabix

    def close(self):
        if self._tabix is not None:
            self._tabix.close()
            self._tabix = None

    def _lookup_sync(
        self, chrom: str, pos: int, ref: str, alt: str,
    ) -> Optional[Dict[str, Any]]:
        tabix = self._get_tabix()
        if not tabix:
            return None

        chrom_clean = str(chrom).replace("chr", "")
        ref_upper = ref.upper()
        alt_upper = alt.upper()

        try:
            for row in tabix.fetch(chrom_clean, pos - 1, pos):
                fields = row.split("\t")
                if len(fields) < 5:
                    continue
                row_ref = fields[2].upper()
                row_alt = fields[3].upper()
                if row_ref == ref_upper and row_alt == alt_upper:
                    return self._parse_tx_annotation(
                        fields[4], chrom_clean, pos, ref_upper, alt_upper,
                    )
                if row_ref == alt_upper and row_alt == ref_upper:
                    return self._parse_tx_annotation(
                        fields[4], chrom_clean, pos, row_ref, row_alt,
                    )
        except ValueError:
            pass

        return None

    @staticmethod
    def _parse_tx_annotation(
        json_str: str, chrom: str, pos: int, ref: str, alt: str,
    ) -> Dict[str, Any]:
        try:
            annotations = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return {"found": False, "source": "gnomad_tx"}

        if not annotations or not isinstance(annotations, list):
            return {"found": False, "source": "gnomad_tx"}

        transcripts = []
        primary_gene = None
        primary_csq = None
        primary_lof = None
        best_expr = float('-inf')

        for ann in annotations:
            entry: Dict[str, Any] = {
                "ensg": ann.get("ensg"),
                "symbol": ann.get("symbol"),
                "csq": ann.get("csq"),
                "lof": ann.get("lof"),
                "lof_flag": ann.get("lof_flag"),
            }

            mean_raw = ann.get("mean_proportion", "NaN")
            mean_prop = None
            if mean_raw not in (None, "NaN", "nan", ""):
                try:
                    mean_prop = float(mean_raw)
                except (ValueError, TypeError):
                    pass
            entry["mean_expression"] = mean_prop

            tissues: Dict[str, float] = {}
            for key, val in ann.items():
                if key in _TX_STANDARD_FIELDS:
                    continue
                if val not in (None, "NaN", "nan", ""):
                    try:
                        tissues[key] = round(float(val), 6)
                    except (ValueError, TypeError):
                        pass
            if tissues:
                top = dict(sorted(tissues.items(), key=lambda x: x[1], reverse=True)[:10])
                entry["top_tissues"] = top
                entry["tissue_count"] = len(tissues)

            transcripts.append(entry)

            expr = mean_prop if mean_prop is not None else -1.0
            if primary_gene is None or expr > best_expr:
                best_expr = expr
                primary_gene = ann.get("symbol")
                primary_csq = ann.get("csq")
                primary_lof = ann.get("lof")

        result: Dict[str, Any] = {
            "found": True,
            "source": "gnomad_tx",
            "chrom": chrom,
            "pos": pos,
            "ref": ref,
            "alt": alt,
            "gene": primary_gene,
            "consequence": primary_csq,
            "lof": primary_lof,
            "transcript_count": len(transcripts),
            "transcripts": transcripts,
        }

        if best_expr >= 0:
            result["mean_expression"] = round(best_expr, 6)

        return result

    async def lookup(
        self, chrom: str, pos: int, ref: str, alt: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        return await asyncio.to_thread(self._lookup_sync, chrom, pos, ref, alt)

    async def lookup_batch(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup. variants: list of (rsid, chrom, pos, ref, alt_csv) tuples."""
        if not variants or not self.available:
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, variants)

    def _lookup_batch_sync(
        self, variants: List[Tuple[str, str, int, str, str]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Bulk batch lookup using chromosome-range scans to avoid 609K random seeks.

        Groups variants by chromosome, sorts by position within each chromosome,
        then fetches a single range [min_pos, max_pos] per chromosome.  This reads
        the bgz file sequentially — dramatically faster than one tabix.fetch() per
        variant for large inputs.
        """
        import time as _time
        tabix = self._get_tabix()
        if not tabix:
            return {}

        # Group variants by chromosome.
        # by_chrom: chrom -> sorted list of (pos, rsid, ref_upper, alts_list)
        by_chrom: Dict[str, list] = {}
        for rsid, chrom, pos, ref, alt_csv in variants:
            chrom_clean = str(chrom).replace("chr", "")
            by_chrom.setdefault(chrom_clean, []).append(
                (int(pos), rsid, str(ref).upper(),
                 [a.strip().upper() for a in str(alt_csv).split(",") if a.strip()])
            )

        # Pre-initialise all results to None (not found)
        results: Dict[str, Optional[Dict[str, Any]]] = {
            rsid: None
            for _, rsid, _, _ in (item for items in by_chrom.values() for item in items)
        }

        # Define natural chromosome sort order
        def _chrom_key(c: str):
            c = c.replace("chr", "")
            if c.isdigit():
                return (0, int(c))
            return (1, c)

        found_count = 0
        processed = 0
        total = len(variants)
        t0 = _time.monotonic()

        for chrom_key_val, chrom_variants in sorted(by_chrom.items(), key=lambda x: _chrom_key(x[0])):
            chrom_variants.sort(key=lambda x: x[0])  # sort by pos

            # Build position index: pos -> list of (rsid, ref, alts)
            pos_index: Dict[int, list] = {}
            for pos, rsid, ref, alts in chrom_variants:
                pos_index.setdefault(pos, []).append((rsid, ref, alts))

            min_pos = chrom_variants[0][0]
            max_pos = chrom_variants[-1][0]

            try:
                for row in tabix.fetch(chrom_key_val, min_pos - 1, max_pos + 1):
                    fields = row.split("\t")
                    if len(fields) < 5:
                        continue
                    try:
                        row_pos = int(fields[1])
                    except (ValueError, IndexError):
                        continue
                    if row_pos not in pos_index:
                        continue
                    row_ref = fields[2].upper()
                    row_alt = fields[3].upper()
                    for rsid, ref, alts in pos_index[row_pos]:
                        if results.get(rsid) is not None and results[rsid] and results[rsid].get('found'):
                            continue  # already found
                        matched = False
                        for alt in alts:
                            if (row_ref == ref and row_alt == alt) or (row_ref == alt and row_alt == ref):
                                matched = True
                                break
                        if matched:
                            hit = self._parse_tx_annotation(
                                fields[4], chrom_key_val, row_pos, row_ref, row_alt,
                            )
                            if hit and hit.get("found"):
                                hit["rsid"] = rsid
                                results[rsid] = hit
                                found_count += 1
            except ValueError:
                pass

            processed += len(chrom_variants)
            elapsed = _time.monotonic() - t0
            logger.debug(
                "  gnomAD-tx chr%s: %d/%d processed, %d found (%.1fs)",
                chrom_key_val, processed, total, found_count, elapsed,
            )

        elapsed = _time.monotonic() - t0
        logger.info(
            "  gnomAD-tx complete: %d/%d found in %.1fs",
            found_count, total, elapsed,
        )
        return results


_gnomad_tx_instance: Optional[GnomadTxService] = None


def get_gnomad_tx_service() -> GnomadTxService:
    global _gnomad_tx_instance
    if _gnomad_tx_instance is None:
        _gnomad_tx_instance = GnomadTxService()
    return _gnomad_tx_instance
