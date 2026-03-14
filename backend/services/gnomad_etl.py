"""
gnomAD ETL — fast import of CADD-annotated gnomAD TSV files into PostgreSQL.

Parses CADD v1.7 annotated gnomAD InDels files (153 columns) which contain
pathogenicity scores (CADD, SIFT, PolyPhen), conservation (PhyloP), and
splice impact (SpliceAI).  Population allele frequencies are NOT in these
files — those come from BigQuery on-demand lookups.

Uses csv.reader for fast parsing and asyncpg COPY protocol for bulk loading.
The file has multiple rows per variant (one per gene/transcript annotation),
so we deduplicate by (chrom, pos, ref, alt) keeping the row with the highest
CADD PHRED score.

Target tables:
  gnomad_variants         — main variant lookup (from CADD-annotated TSV)
  gnomad_gene_constraints — gene-level constraint scores

Run via admin endpoint: POST /api/admin/gnomad-etl/import
"""

from __future__ import annotations

import asyncio
import asyncpg
import csv
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

_GNOMAD_DATA_DIR = Path(os.environ.get(
    "GNOMAD_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "gnomad"),
))

# asyncpg needs the plain postgresql:// DSN (strip SQLAlchemy "+asyncpg")
_DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
).replace("postgresql+asyncpg://", "postgresql://")

# ── Column lists matching DB schema (excluding id, imported_at — auto) ──

VARIANT_COLUMNS = [
    "chrom", "pos", "ref", "alt", "variant_id", "variant_type",
    "cadd_raw", "cadd_phred",
    "sift_cat", "sift_val", "polyphen_cat", "polyphen_val",
    "phylop_primate", "phylop_mammal", "phylop_vertebrate",
    "splice_ai_acc_gain", "splice_ai_acc_loss",
    "splice_ai_don_gain", "splice_ai_don_loss",
    "gene", "consequence",
    "data_source",
]

CONSTRAINT_COLUMNS = [
    "gene", "transcript",
    "pli", "loeuf", "mis_z", "syn_z",
    "obs_lof", "exp_lof", "obs_mis", "exp_mis", "obs_syn", "exp_syn",
]


class GnomadETL:
    """Import gnomAD TSV data into PostgreSQL using streaming COPY."""

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else _GNOMAD_DATA_DIR

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
            logger.info("gnomAD ETL %s: %d rows in %.1fs", step, count, elapsed)

        # 1. Truncate
        t0 = time.time()
        await self._truncate_tables()
        _report("truncate", 0, time.time() - t0)

        # 2. Drop non-PK indexes for faster bulk loading
        t0 = time.time()
        await self._drop_indexes()
        _report("drop_indexes", 0, time.time() - t0)

        # 3. Import variant TSV files (may be multiple)
        variant_files = self._find_variant_files()
        total_variants = 0
        for vf in variant_files:
            t0 = time.time()
            n = await self._stream_import(
                vf, self._parse_variant_chunks, "gnomad_variants", VARIANT_COLUMNS,
            )
            total_variants += n
            _report(f"variants:{vf.name}", n, time.time() - t0)

        if not variant_files:
            logger.warning("No gnomAD variant files found in %s", self._data_dir)

        # 4. Import constraint file (if present)
        constraint_file = self._data_dir / "gnomad.v4.0.constraint_metrics.tsv"
        if not constraint_file.exists():
            constraint_file = self._data_dir / "gnomad.v4.0.constraint_metrics.tsv.gz"
        if not constraint_file.exists():
            # Try any constraint file
            for p in self._data_dir.glob("*constraint*"):
                constraint_file = p
                break

        if constraint_file.exists():
            t0 = time.time()
            rows = await asyncio.to_thread(self._parse_constraints, constraint_file)
            if rows:
                await self._copy_records("gnomad_gene_constraints", CONSTRAINT_COLUMNS, rows)
            _report("constraints", len(rows), time.time() - t0)
        else:
            logger.info("No gnomAD constraint file found — skipping")

        # 5. Recreate indexes
        t0 = time.time()
        await self._create_indexes()
        _report("create_indexes", 0, time.time() - t0)

        # 6. ANALYZE for query planner
        t0 = time.time()
        await self._analyze_tables()
        _report("analyze", 0, time.time() - t0)

        # Final counts
        counts = await self.get_import_status()
        stats["final_counts"] = counts
        stats["total_elapsed_s"] = round(time.time() - total_start, 1)
        logger.info("gnomAD ETL complete in %.1fs — %s", stats["total_elapsed_s"], counts)
        return stats

    def _find_variant_files(self) -> List[Path]:
        """Find all gnomAD variant TSV files in the data directory."""
        patterns = [
            "gnomad.genomes.*.tsv.gz",
            "gnomad.exomes.*.tsv.gz",
            "gnomad*.tsv.gz",
        ]
        found: List[Path] = []
        seen: set = set()
        for pat in patterns:
            for p in sorted(self._data_dir.glob(pat)):
                # Skip constraint files
                if "constraint" in p.name.lower():
                    continue
                if p.name not in seen:
                    seen.add(p.name)
                    found.append(p)
        return found

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

    async def _copy_records(self, table_name, columns, records):
        """COPY a full list of records in one shot (for small tables)."""
        conn = await asyncpg.connect(_DB_DSN)
        try:
            await conn.copy_records_to_table(
                table_name, records=records, columns=columns,
            )
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # Parsers (sync generators yielding chunks of tuples)
    # ------------------------------------------------------------------

    def _parse_variant_chunks(self, fpath: Path):
        """Yield chunks of tuples from a CADD-annotated gnomAD TSV file.

        The CADD v1.7 format has 153 columns and multiple rows per variant
        (one per gene/transcript annotation).  We deduplicate by
        (chrom, pos, ref, alt) keeping the row with the highest CADD PHRED.
        Adjacent rows in the file share the same variant, so we buffer by key."""
        chunk: list = []

        open_fn = gzip.open if str(fpath).endswith('.gz') else open

        with open_fn(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh, delimiter="\t")

            # Find header — skip comment lines (##)
            header = None
            for row in reader:
                if row and not row[0].startswith("##"):
                    header = row
                    break
            if not header:
                logger.warning("No header found in %s", fpath)
                return

            idx = {name.strip().lstrip('#').lower(): i for i, name in enumerate(header)}
            logger.info("CADD TSV header (%d cols): %s…", len(header), list(idx.keys())[:15])

            col_map = self._build_column_map(idx)

            # Deduplication state: buffer rows by variant key, emit best on key change
            prev_key: Optional[tuple] = None
            best_row: Optional[tuple] = None
            best_phred: float = -999.0

            for row in reader:
                if not row or row[0].startswith("#"):
                    continue

                try:
                    parsed = self._parse_variant_row(row, col_map)
                    if parsed is None:
                        continue
                except Exception:
                    continue

                # Extract key (chrom, pos, ref, alt) — indices 0..3
                cur_key = (parsed[0], parsed[1], parsed[2], parsed[3])
                cur_phred = parsed[7] if parsed[7] is not None else -999.0  # cadd_phred at index 7

                if cur_key == prev_key:
                    # Same variant — keep row with higher CADD PHRED
                    if cur_phred > best_phred:
                        best_row = parsed
                        best_phred = cur_phred
                else:
                    # New variant — emit previous best
                    if best_row is not None:
                        chunk.append(best_row)
                        if len(chunk) >= CHUNK_SIZE:
                            yield chunk
                            chunk = []
                    prev_key = cur_key
                    best_row = parsed
                    best_phred = cur_phred

            # Emit last buffered variant
            if best_row is not None:
                chunk.append(best_row)

        if chunk:
            yield chunk

    def _build_column_map(self, idx: Dict[str, int]) -> Dict[str, Optional[int]]:
        """Build a mapping from our schema fields to CADD TSV column indices.

        CADD v1.7 annotated gnomAD InDels TSV columns (153 total).
        Column names are case-sensitive in the file but we lowercase them."""
        def _find(*names):
            for n in names:
                n_lower = n.lower().lstrip('#')
                if n_lower in idx:
                    return idx[n_lower]
            return None

        return {
            'chrom': _find('chrom', 'chr', '#chrom'),
            'pos': _find('pos', 'position'),
            'ref': _find('ref', 'reference'),
            'alt': _find('alt', 'alternate'),
            'type': _find('type'),
            'consequence': _find('consequence'),
            'gene': _find('genename', 'gene', 'gene_symbol'),
            'sift_cat': _find('siftcat'),
            'sift_val': _find('siftval'),
            'polyphen_cat': _find('polyphencat'),
            'polyphen_val': _find('polyphenval'),
            'phylop_pri': _find('priphylop'),
            'phylop_mam': _find('mamphylop'),
            'phylop_ver': _find('verphylop'),
            'splice_acc_gain': _find('spliceai-acc-gain'),
            'splice_acc_loss': _find('spliceai-acc-loss'),
            'splice_don_gain': _find('spliceai-don-gain'),
            'splice_don_loss': _find('spliceai-don-loss'),
            'raw_score': _find('rawscore'),
            'phred': _find('phred'),
        }

    def _parse_variant_row(
        self, row: List[str], col_map: Dict[str, Optional[int]]
    ) -> Optional[tuple]:
        """Parse a single CADD TSV row into a tuple matching VARIANT_COLUMNS."""

        def _get(field: str) -> Optional[str]:
            ci = col_map.get(field)
            if ci is None or ci >= len(row):
                return None
            val = row[ci].strip()
            return val if val and val not in (".", "NA", "nan", "") else None

        def _float(field: str) -> Optional[float]:
            v = _get(field)
            if not v:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        chrom = _get('chrom')
        if not chrom:
            return None
        chrom = chrom.replace('chr', '')

        pos_str = _get('pos')
        if not pos_str:
            return None
        try:
            pos = int(pos_str)
        except (ValueError, TypeError):
            return None

        ref = _get('ref')
        alt = _get('alt')
        if not ref or not alt:
            return None

        variant_id = f"{chrom}-{pos}-{ref}-{alt}"
        variant_type = _get('type')  # INS, DEL, SNV

        return (
            chrom, pos, ref, alt, variant_id, variant_type,
            _float('raw_score'),       # cadd_raw
            _float('phred'),           # cadd_phred
            _get('sift_cat'),          # sift_cat
            _float('sift_val'),        # sift_val
            _get('polyphen_cat'),      # polyphen_cat
            _float('polyphen_val'),    # polyphen_val
            _float('phylop_pri'),      # phylop_primate
            _float('phylop_mam'),      # phylop_mammal
            _float('phylop_ver'),      # phylop_vertebrate
            _float('splice_acc_gain'), # splice_ai_acc_gain
            _float('splice_acc_loss'), # splice_ai_acc_loss
            _float('splice_don_gain'), # splice_ai_don_gain
            _float('splice_don_loss'), # splice_ai_don_loss
            _get('gene'),              # gene
            _get('consequence'),       # consequence
            "tsv",                     # data_source
        )

    def _parse_constraints(self, fpath: Path) -> List[tuple]:
        """Parse gnomAD constraint metrics file → list of tuples."""
        rows: List[tuple] = []
        seen_genes: set = set()

        open_fn = gzip.open if str(fpath).endswith('.gz') else open

        with open_fn(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(
                (line for line in fh if not line.startswith("##")),
                delimiter="\t",
            )
            header = next(reader)
            idx = {name.strip().lower(): i for i, name in enumerate(header)}

            def _find(*names):
                for n in names:
                    if n.lower() in idx:
                        return idx[n.lower()]
                return None

            I_GENE = _find('gene', 'gene_symbol', 'symbol')
            I_TX = _find('transcript', 'canonical_transcript')
            I_PLI = _find('pli', 'pLI')
            I_LOEUF = _find('loeuf', 'oe_lof_upper', 'LOEUF')
            I_MIS_Z = _find('mis_z', 'missense_z', 'mis_z_score')
            I_SYN_Z = _find('syn_z', 'synonymous_z', 'syn_z_score')
            I_OBS_LOF = _find('obs_lof', 'n_lof', 'observed_lof')
            I_EXP_LOF = _find('exp_lof', 'expected_lof')
            I_OBS_MIS = _find('obs_mis', 'n_mis', 'observed_mis')
            I_EXP_MIS = _find('exp_mis', 'expected_mis')
            I_OBS_SYN = _find('obs_syn', 'n_syn', 'observed_syn')
            I_EXP_SYN = _find('exp_syn', 'expected_syn')

            if I_GENE is None:
                logger.warning("gnomAD constraint file: no gene column found in: %s", header[:10])
                return rows

            def _safe_str(i, row):
                return row[i].strip() if i is not None and i < len(row) else None

            def _safe_float(i, row):
                v = _safe_str(i, row)
                if not v or v in (".", "NA", "nan"):
                    return None
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None

            def _safe_int(i, row):
                v = _safe_str(i, row)
                if not v or v in (".", "NA", "nan"):
                    return None
                try:
                    return int(float(v))
                except (ValueError, TypeError):
                    return None

            for row in reader:
                gene = _safe_str(I_GENE, row)
                if not gene or gene in seen_genes:
                    continue
                seen_genes.add(gene)
                rows.append((
                    gene,
                    _safe_str(I_TX, row),
                    _safe_float(I_PLI, row),
                    _safe_float(I_LOEUF, row),
                    _safe_float(I_MIS_Z, row),
                    _safe_float(I_SYN_Z, row),
                    _safe_int(I_OBS_LOF, row),
                    _safe_float(I_EXP_LOF, row),
                    _safe_int(I_OBS_MIS, row),
                    _safe_float(I_EXP_MIS, row),
                    _safe_int(I_OBS_SYN, row),
                    _safe_float(I_EXP_SYN, row),
                ))

        logger.info("Parsed %d gene constraint rows from %s", len(rows), fpath.name)
        return rows

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    _CUSTOM_INDEXES = [
        ("ix_gnomad_variants_rsid", "gnomad_variants", "(rsid)"),
        ("ix_gnomad_variants_chrom_pos", "gnomad_variants", "(chrom, pos)"),
        ("ix_gnomad_variants_chrom_pos_ref_alt", "gnomad_variants", "(chrom, pos, ref, alt)"),
        ("ix_gnomad_variants_gene", "gnomad_variants", "(gene)"),
        ("ix_gnomad_variants_variant_id", "gnomad_variants", "(variant_id)"),
        ("ix_gnomad_variants_cadd_phred", "gnomad_variants", "(cadd_phred)"),
        ("ix_gnomad_gene_constraints_gene", "gnomad_gene_constraints", "(gene)"),
    ]

    async def _drop_indexes(self):
        async with async_session_factory() as session:
            for name, _, _ in self._CUSTOM_INDEXES:
                await session.execute(text(f"DROP INDEX IF EXISTS {name}"))
            await session.commit()
        logger.info("Dropped gnomAD indexes for bulk load")

    async def _create_indexes(self):
        async with async_session_factory() as session:
            for name, table, cols in self._CUSTOM_INDEXES:
                await session.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}"
                ))
            await session.commit()
        logger.info("Recreated gnomAD indexes")

    # ------------------------------------------------------------------
    # Table management
    # ------------------------------------------------------------------

    async def _truncate_tables(self):
        async with async_session_factory() as session:
            await session.execute(text("TRUNCATE gnomad_variants RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE gnomad_gene_constraints RESTART IDENTITY CASCADE"))
            await session.commit()
        logger.info("Truncated gnomAD tables")

    async def _analyze_tables(self):
        async with async_session_factory() as session:
            await session.execute(text("ANALYZE gnomad_variants"))
            await session.execute(text("ANALYZE gnomad_gene_constraints"))
            await session.commit()

    # ------------------------------------------------------------------
    # Status / counts
    # ------------------------------------------------------------------

    async def get_import_status(self) -> Dict[str, Any]:
        """Return counts from gnomAD tables + file availability."""
        async with async_session_factory() as session:
            gv = (await session.execute(text("SELECT count(*) FROM gnomad_variants"))).scalar()
            gc = (await session.execute(text("SELECT count(*) FROM gnomad_gene_constraints"))).scalar()

        variant_files = self._find_variant_files()
        return {
            "gnomad_variants": gv,
            "gnomad_gene_constraints": gc,
            "variant_files": [f.name for f in variant_files],
            "data_dir": str(self._data_dir),
        }
