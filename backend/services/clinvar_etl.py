"""
ClinVar ETL — fast import of ClinVar TSV + VCF into PostgreSQL.

Uses csv.reader (not DictReader) for fast parsing and asyncpg COPY
protocol for bulk loading.  A producer-consumer pattern streams chunks
from a parsing thread into the database so memory stays bounded.

Target tables:
  clinvar_variants        — main variant lookup (from variant_summary + VCF)
  clinvar_gene_conditions — gene→disease (from gene_condition_source_id.txt)
  clinvar_gene_stats      — per-gene stats (from gene_specific_summary.txt)

Run via admin endpoint: POST /api/admin/clinvar-etl/import
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

from .datasource_utils import parse_vcf_info, safe_float

from ..db.database import async_session_factory

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50_000

# ── Module-level progress state (shared across requests) ──────────────────────

_etl_progress: Dict[str, Any] = {
    "running": False,
    "step": None,
    "rows": 0,
    "pct": 0,
    "total_elapsed": 0.0,
    "started_at": None,
    "completed_at": None,
    "error": None,
    "steps": [],
}

# Rough percentage milestones per step (variant_summary is the bulk)
_STEP_PCT: Dict[str, int] = {
    "truncate": 2,
    "drop_indexes": 5,
    "variant_summary": 50,
    "clinvar_vcf": 85,
    "gene_conditions": 88,
    "gene_stats": 91,
    "create_indexes": 96,
    "analyze": 100,
}


def get_etl_progress() -> Dict[str, Any]:
    """Return a snapshot of the current ETL progress state."""
    return dict(_etl_progress)

_CLINVAR_DATA_DIR = Path(os.environ.get(
    "CLINVAR_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "clinvar"),
))

# asyncpg needs the plain postgresql:// DSN (strip SQLAlchemy "+asyncpg")
_DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
).replace("postgresql+asyncpg://", "postgresql://")

# ── Column lists matching DB schema (excluding id, imported_at — auto) ──

TSV_COLUMNS = [
    "rsid", "allele_id", "variation_id",
    "clinical_significance", "review_status", "conditions",
    "origin", "variation_type",
    "gene", "gene_id", "chromosome",
    "start_pos", "stop_pos", "assembly",
    "rcv_accession", "phenotype_ids",
    "data_source",
]

VCF_COLUMNS = [
    "rsid", "allele_id",
    "clinical_significance", "review_status", "conditions",
    "origin", "variation_type", "gene",
    "molecular_consequence",
    "af_exac", "af_tgp", "af_esp",
    "oncogenicity", "somatic_clinical_impact",
    "conflicting_classifications", "hgvs_nucleotide",
    "data_source",
]

GC_COLUMNS = ["gene", "disease_name", "source_name", "source_id", "disease_mim"]

GS_COLUMNS = [
    "gene", "gene_id", "total_submissions", "total_alleles",
    "pathogenic_likely_pathogenic", "uncertain_significance",
    "with_conflicts", "gene_mim",
]


class ClinVarETL:
    """Import ClinVar TSV + VCF data into PostgreSQL using streaming COPY."""

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else _CLINVAR_DATA_DIR
        self._tsv_dir = self._data_dir / "tsv"
        self._vcf_dir = self._data_dir / "vcf"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_full_import(self, *, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Run the full ETL pipeline.  Returns summary stats."""
        global _etl_progress
        total_start = time.time()
        stats: Dict[str, Any] = {"steps": []}

        _etl_progress.update({
            "running": True,
            "step": "starting",
            "rows": 0,
            "pct": 0,
            "total_elapsed": 0.0,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "completed_at": None,
            "error": None,
            "steps": [],
        })

        def _report(step: str, count: int, elapsed: float):
            entry = {"step": step, "count": count, "elapsed_s": round(elapsed, 1)}
            stats["steps"].append(entry)
            _etl_progress["step"] = step
            _etl_progress["rows"] = count
            _etl_progress["pct"] = _STEP_PCT.get(step, _etl_progress["pct"])
            _etl_progress["total_elapsed"] = round(time.time() - total_start, 1)
            _etl_progress["steps"] = list(stats["steps"])
            if progress_callback:
                progress_callback(step, count, elapsed)
            logger.info("ETL %s: %d rows in %.1fs", step, count, elapsed)

        def _row_progress(step: str, rows: int):
            """Called mid-step as rows accumulate."""
            _etl_progress["step"] = step
            _etl_progress["rows"] = rows
            _etl_progress["total_elapsed"] = round(time.time() - total_start, 1)

        try:
            # 1. Truncate
            t0 = time.time()
            await self._truncate_tables()
            _report("truncate", 0, time.time() - t0)

            # 2. Drop non-PK indexes for faster bulk loading
            t0 = time.time()
            await self._drop_indexes()
            _report("drop_indexes", 0, time.time() - t0)

            # 3. Stream-import variant_summary.txt.gz
            tsv_path = self._tsv_dir / "variant_summary.txt.gz"
            if tsv_path.exists():
                t0 = time.time()
                n = await self._stream_import(
                    tsv_path, self._parse_tsv_chunks, "clinvar_variants", TSV_COLUMNS,
                    row_callback=lambda rows: _row_progress("variant_summary", rows),
                )
                _report("variant_summary", n, time.time() - t0)
            else:
                logger.warning("variant_summary.txt.gz not found at %s", tsv_path)

            # 4. Stream-import clinvar.vcf.gz
            vcf_path = self._vcf_dir / "clinvar.vcf.gz"
            if vcf_path.exists():
                t0 = time.time()
                n = await self._stream_import(
                    vcf_path, self._parse_vcf_chunks, "clinvar_variants", VCF_COLUMNS,
                    row_callback=lambda rows: _row_progress("clinvar_vcf", rows),
                )
                _report("clinvar_vcf", n, time.time() - t0)
            else:
                logger.warning("clinvar.vcf.gz not found")

            # 5. Gene conditions (small file — parse and COPY in one shot)
            gc_path = self._tsv_dir / "gene_condition_source_id.txt"
            if gc_path.exists():
                t0 = time.time()
                rows = await asyncio.to_thread(self._parse_gene_conditions, gc_path)
                if rows:
                    await self._copy_records("clinvar_gene_conditions", GC_COLUMNS, rows)
                _report("gene_conditions", len(rows), time.time() - t0)

            # 6. Gene stats (small file)
            gs_path = self._tsv_dir / "gene_specific_summary.txt"
            if gs_path.exists():
                t0 = time.time()
                rows = await asyncio.to_thread(self._parse_gene_stats, gs_path)
                if rows:
                    await self._copy_records("clinvar_gene_stats", GS_COLUMNS, rows)
                _report("gene_stats", len(rows), time.time() - t0)

            # 7. Recreate indexes
            t0 = time.time()
            await self._create_indexes()
            _report("create_indexes", 0, time.time() - t0)

            # 8. ANALYZE for query planner
            t0 = time.time()
            await self._analyze_tables()
            _report("analyze", 0, time.time() - t0)

            # Final counts
            counts = await self.get_import_status()
            stats["final_counts"] = counts
            stats["total_elapsed_s"] = round(time.time() - total_start, 1)
            _etl_progress.update({
                "running": False,
                "step": "complete",
                "pct": 100,
                "total_elapsed": stats["total_elapsed_s"],
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            logger.info("ClinVar ETL complete in %.1fs — %s", stats["total_elapsed_s"], counts)
            return stats

        except Exception as exc:
            _etl_progress.update({
                "running": False,
                "step": "error",
                "error": str(exc),
                "total_elapsed": round(time.time() - total_start, 1),
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            logger.exception("ClinVar ETL failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Streaming producer-consumer import
    # ------------------------------------------------------------------

    async def _stream_import(self, fpath, parser_func, table_name, columns, *, row_callback=None):
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
                if total % 200_000 < CHUNK_SIZE:
                    logger.info("  %s: %d rows inserted", table_name, total)
                    if row_callback:
                        row_callback(total)
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
    # Parsers  (sync generators yielding chunks of tuples)
    # ------------------------------------------------------------------

    def _parse_tsv_chunks(self, fpath):
        """Yield chunks of tuples from variant_summary.txt.gz."""
        chunk: list = []

        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader)
            idx = {name: i for i, name in enumerate(header)}

            col = {name: idx[name] for name in (
                "RS# (dbSNP)", "#AlleleID", "VariationID",
                "ClinicalSignificance", "ReviewStatus", "PhenotypeList",
                "Origin", "Type", "GeneSymbol", "GeneID",
                "Chromosome", "Start", "Stop", "Assembly",
                "RCVaccession", "PhenotypeIDS",
            )}

            for row in reader:
                rs_raw = row[col["RS# (dbSNP)"]].strip()
                if not rs_raw or rs_raw in ("-1", "-"):
                    continue
                rsid = f"rs{rs_raw}" if not rs_raw.startswith("rs") else rs_raw

                sp = row[col["Start"]].strip()
                ep = row[col["Stop"]].strip()

                chunk.append((
                    rsid,
                    row[col["#AlleleID"]].strip() or None,
                    row[col["VariationID"]].strip() or None,
                    row[col["ClinicalSignificance"]].strip() or None,
                    row[col["ReviewStatus"]].strip() or None,
                    row[col["PhenotypeList"]].strip() or None,
                    row[col["Origin"]].strip() or None,
                    row[col["Type"]].strip() or None,
                    row[col["GeneSymbol"]].strip() or None,
                    row[col["GeneID"]].strip() or None,
                    row[col["Chromosome"]].strip() or None,
                    int(sp) if sp and sp not in ("-", "") else None,
                    int(ep) if ep and ep not in ("-", "") else None,
                    row[col["Assembly"]].strip() or None,
                    row[col["RCVaccession"]].strip() or None,
                    row[col["PhenotypeIDS"]].strip() or None,
                    "tsv",
                ))

                if len(chunk) >= CHUNK_SIZE:
                    yield chunk
                    chunk = []

        if chunk:
            yield chunk

    def _parse_vcf_chunks(self, fpath):
        """Yield chunks of tuples from clinvar.vcf.gz."""
        chunk: list = []

        with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line[0] == "#":
                    continue
                parts = line.split("\t", 8)
                if len(parts) < 8:
                    continue

                info = parse_vcf_info(parts[7])
                rs_raw = info.get("RS")
                if not rs_raw:
                    continue

                af_exac = safe_float(info.get("AF_EXAC"))
                af_tgp = safe_float(info.get("AF_TGP"))
                af_esp = safe_float(info.get("AF_ESP"))

                mc_raw = info.get("MC", "")
                mc_text = None
                if mc_raw:
                    labels = []
                    for mcp in mc_raw.split(","):
                        pipe = mcp.find("|")
                        labels.append(mcp[pipe + 1:] if pipe >= 0 else mcp)
                    mc_text = ", ".join(labels)

                gene_info = info.get("GENEINFO", "")
                gene = None
                if gene_info:
                    first = gene_info.split("|")[0]
                    gene = first.split(":")[0] if ":" in first else first
                    gene = gene.strip() or None

                conditions = (info.get("CLNDN") or "").replace("_", " ") or None

                rs_list = rs_raw.split(",") if "," in rs_raw else (rs_raw,)
                for rs_val in rs_list:
                    rs_val = rs_val.strip()
                    if not rs_val:
                        continue
                    chunk.append((
                        f"rs{rs_val}",
                        info.get("ALLELEID") or None,
                        info.get("CLNSIG") or None,
                        info.get("CLNREVSTAT") or None,
                        conditions,
                        info.get("ORIGIN") or None,
                        info.get("CLNVC") or None,
                        gene,
                        mc_text,
                        af_exac, af_tgp, af_esp,
                        info.get("ONC") or None,
                        info.get("SCI") or None,
                        info.get("CLNSIGCONF") or None,
                        info.get("CLNHGVS") or None,
                        "vcf",
                    ))

                    if len(chunk) >= CHUNK_SIZE:
                        yield chunk
                        chunk = []

        if chunk:
            yield chunk

    def _parse_gene_conditions(self, fpath) -> List[tuple]:
        """Parse gene_condition_source_id.txt → list of tuples."""
        rows: List[tuple] = []

        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(
                (line for line in fh if not line.startswith("##")),
                delimiter="\t",
            )
            header = next(reader)
            idx = {name: i for i, name in enumerate(header)}

            I_GENE = idx.get("AssociatedGenes")
            I_DIS = idx.get("DiseaseName")
            I_SRC = idx.get("SourceName")
            I_SID = idx.get("SourceID")
            I_MIM = idx.get("DiseaseMIM")

            if I_GENE is None or I_DIS is None:
                logger.warning("gene_condition_source_id.txt: unexpected header: %s", header)
                return rows

            for row in reader:
                if len(row) <= max(I_GENE, I_DIS):
                    continue
                genes_str = row[I_GENE].strip()
                disease = row[I_DIS].strip()
                if not genes_str or not disease:
                    continue
                for gene in genes_str.split(","):
                    gene = gene.strip()
                    if gene:
                        rows.append((
                            gene,
                            disease,
                            (row[I_SRC].strip() if I_SRC is not None and I_SRC < len(row) else None) or None,
                            (row[I_SID].strip() if I_SID is not None and I_SID < len(row) else None) or None,
                            (row[I_MIM].strip() if I_MIM is not None and I_MIM < len(row) else None) or None,
                        ))

        logger.info("Parsed %d gene-condition rows from %s", len(rows), fpath.name)
        return rows

    def _parse_gene_stats(self, fpath) -> List[tuple]:
        """Parse gene_specific_summary.txt → list of tuples (deduped by gene)."""
        rows: List[tuple] = []
        seen_genes: set = set()

        def _int(v):
            v = (v or "").strip()
            return int(v) if v and v != "-" else 0

        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(
                (line for line in fh if not line.startswith("#Overview") and not line.startswith("##")),
                delimiter="\t",
            )
            header = next(reader)
            idx = {name: i for i, name in enumerate(header)}

            I_SYM = idx.get("#Symbol", idx.get("Symbol"))
            I_GID = idx.get("GeneID")
            I_TS = idx.get("Total_submissions")
            I_TA = idx.get("Total_alleles")
            I_PLP = idx.get("Alleles_reported_Pathogenic_Likely_pathogenic")
            I_US = idx.get("Number_uncertain")
            I_WC = idx.get("Number_with_conflicts")
            I_MIM = idx.get("Gene_MIM_number")

            if I_SYM is None:
                logger.warning("gene_specific_summary.txt: unexpected header: %s", header)
                return rows

            def _safe(i, row):
                return row[i].strip() if i is not None and i < len(row) else ""

            for row in reader:
                symbol = _safe(I_SYM, row)
                if not symbol or symbol in seen_genes:
                    continue
                seen_genes.add(symbol)
                rows.append((
                    symbol,
                    _safe(I_GID, row) or None,
                    _int(_safe(I_TS, row)),
                    _int(_safe(I_TA, row)),
                    _int(_safe(I_PLP, row)),
                    _int(_safe(I_US, row)),
                    _int(_safe(I_WC, row)),
                    _safe(I_MIM, row) or None,
                ))

        logger.info("Parsed %d gene-stat rows from %s", len(rows), fpath.name)
        return rows

    # ------------------------------------------------------------------
    # Index management (drop before bulk load, recreate after)
    # ------------------------------------------------------------------

    _CUSTOM_INDEXES = [
        ("ix_clinvar_variants_rsid", "clinvar_variants", "(rsid)"),
        ("ix_clinvar_variants_gene", "clinvar_variants", "(gene)"),
        ("ix_clinvar_variants_significance", "clinvar_variants", "(clinical_significance)"),
        ("ix_clinvar_variants_rsid_allele", "clinvar_variants", "(rsid, allele_id)"),
        ("ix_clinvar_gene_conditions_gene", "clinvar_gene_conditions", "(gene)"),
    ]

    async def _drop_indexes(self):
        async with async_session_factory() as session:
            for name, _, _ in self._CUSTOM_INDEXES:
                await session.execute(text(f"DROP INDEX IF EXISTS {name}"))
            await session.commit()
        logger.info("Dropped ClinVar indexes for bulk load")

    async def _create_indexes(self):
        async with async_session_factory() as session:
            for name, table, cols in self._CUSTOM_INDEXES:
                await session.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}"
                ))
            await session.commit()
        logger.info("Recreated ClinVar indexes")

    # ------------------------------------------------------------------
    # Table management
    # ------------------------------------------------------------------

    async def _truncate_tables(self):
        async with async_session_factory() as session:
            await session.execute(text("TRUNCATE clinvar_variants RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE clinvar_gene_conditions RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE clinvar_gene_stats RESTART IDENTITY CASCADE"))
            await session.commit()
        logger.info("Truncated ClinVar tables")

    async def _analyze_tables(self):
        async with async_session_factory() as session:
            await session.execute(text("ANALYZE clinvar_variants"))
            await session.execute(text("ANALYZE clinvar_gene_conditions"))
            await session.execute(text("ANALYZE clinvar_gene_stats"))
            await session.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Status / counts
    # ------------------------------------------------------------------

    async def get_import_status(self) -> Dict[str, Any]:
        """Return counts from ClinVar tables."""
        async with async_session_factory() as session:
            cv = (await session.execute(text("SELECT count(*) FROM clinvar_variants"))).scalar()
            gc = (await session.execute(text("SELECT count(*) FROM clinvar_gene_conditions"))).scalar()
            gs = (await session.execute(text("SELECT count(*) FROM clinvar_gene_stats"))).scalar()
        return {
            "clinvar_variants": cv,
            "clinvar_gene_conditions": gc,
            "clinvar_gene_stats": gs,
            "tsv_file_exists": (self._tsv_dir / "variant_summary.txt.gz").exists(),
            "vcf_file_exists": (self._vcf_dir / "clinvar.vcf.gz").exists(),
        }
