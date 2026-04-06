from __future__ import annotations

import asyncio
import asyncpg
import csv
import io
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50_000

_GWAS_DATA_DIR = Path(os.environ.get(
    "GWAS_DATA_DIR",
    "/app/data_sources/gwas_catalog",
))

_DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
).replace("postgresql+asyncpg://", "postgresql://")

_etl_progress: Dict[str, Any] = {
    "running": False,
    "step": None,
    "rows": 0,
    "pct": 0,
    "total_elapsed": 0.0,
    "started_at": None,
    "completed_at": None,
    "error": None,
}


def get_etl_progress() -> Dict[str, Any]:
    return dict(_etl_progress)


def _update_progress(step: str, rows: int, pct: int) -> None:
    _etl_progress.update(step=step, rows=rows, pct=pct)


_GWAS_COLUMNS = [
    "rsid", "pubmed_id", "study_accession", "trait", "mapped_trait",
    "mapped_trait_uri", "reported_genes", "mapped_genes", "p_value",
    "p_value_mlog", "or_beta", "ci_text", "risk_allele_frequency",
    "strongest_snp_risk_allele", "chromosome", "chromosome_position", "context",
]

_HEADER_TO_COL = {
    "SNPS": "rsid",
    "PUBMEDID": "pubmed_id",
    "STUDY ACCESSION": "study_accession",
    "DISEASE/TRAIT": "trait",
    "MAPPED_TRAIT": "mapped_trait",
    "MAPPED_TRAIT_URI": "mapped_trait_uri",
    "REPORTED GENE(S)": "reported_genes",
    "MAPPED_GENE": "mapped_genes",
    "P-VALUE": "p_value",
    "PVALUE_MLOG": "p_value_mlog",
    "OR or BETA": "or_beta",
    "95% CI (TEXT)": "ci_text",
    "RISK ALLELE FREQUENCY": "risk_allele_frequency",
    "STRONGEST SNP-RISK ALLELE": "strongest_snp_risk_allele",
    "CHR_ID": "chromosome",
    "CHR_POS": "chromosome_position",
    "CONTEXT": "context",
}


def _safe_float(v: str) -> Optional[float]:
    if not v or v in (".", "NA", "NR", ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _safe_int(v: str) -> Optional[int]:
    if not v or v in (".", "NA", ""):
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _clean(v: str) -> Optional[str]:
    stripped = v.strip()
    return None if stripped in ("", ".", "NA", "NR", "N/A") else stripped


def _parse_row(header_idx: Dict[str, int], row: List[str]) -> Optional[Dict]:
    def get(col_name: str) -> str:
        idx = header_idx.get(col_name)
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    rsid = _clean(get("SNPS"))
    if not rsid:
        return None

    return {
        "rsid": rsid,
        "pubmed_id": _clean(get("PUBMEDID")),
        "study_accession": _clean(get("STUDY ACCESSION")),
        "trait": _clean(get("DISEASE/TRAIT")),
        "mapped_trait": _clean(get("MAPPED_TRAIT")),
        "mapped_trait_uri": _clean(get("MAPPED_TRAIT_URI")),
        "reported_genes": _clean(get("REPORTED GENE(S)")),
        "mapped_genes": _clean(get("MAPPED_GENE")),
        "p_value": _safe_float(get("P-VALUE")),
        "p_value_mlog": _safe_float(get("PVALUE_MLOG")),
        "or_beta": _safe_float(get("OR or BETA")),
        "ci_text": _clean(get("95% CI (TEXT)")),
        "risk_allele_frequency": _safe_float(get("RISK ALLELE FREQUENCY")),
        "strongest_snp_risk_allele": _clean(get("STRONGEST SNP-RISK ALLELE")),
        "chromosome": _clean(get("CHR_ID")),
        "chromosome_position": _safe_int(get("CHR_POS")),
        "context": _clean(get("CONTEXT")),
    }


async def run_gwas_etl(
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    if _etl_progress["running"]:
        return {"error": "ETL already running"}

    gwas_file = _find_gwas_file()
    if not gwas_file:
        return {"error": f"No GWAS Catalog file found in {_GWAS_DATA_DIR}. Expected gwas_associations.tsv or gwas_associations_full.zip"}

    _etl_progress.update(
        running=True, step="start", rows=0, pct=0,
        started_at=time.time(), completed_at=None, error=None,
    )
    start = time.time()

    try:
        conn = await asyncpg.connect(_DB_DSN)
        await conn.execute("TRUNCATE TABLE gwas_catalog_associations RESTART IDENTITY")
        await conn.execute("DROP INDEX IF EXISTS ix_gwas_catalog_rsid")

        rows_inserted = 0

        async def _flush(chunk: List[Dict]) -> None:
            nonlocal rows_inserted
            await conn.copy_records_to_table(
                "gwas_catalog_associations",
                records=[
                    (
                        r["rsid"], r["pubmed_id"], r["study_accession"],
                        r["trait"], r["mapped_trait"], r["mapped_trait_uri"],
                        r["reported_genes"], r["mapped_genes"],
                        r["p_value"], r["p_value_mlog"], r["or_beta"],
                        r["ci_text"], r["risk_allele_frequency"],
                        r["strongest_snp_risk_allele"], r["chromosome"],
                        r["chromosome_position"], r["context"],
                    )
                    for r in chunk
                ],
                columns=_GWAS_COLUMNS,
            )
            rows_inserted += len(chunk)
            pct = min(90, int(rows_inserted / 2_000_000 * 90))
            _update_progress("importing", rows_inserted, pct)
            if progress_cb:
                await asyncio.get_event_loop().run_in_executor(None, progress_cb, "importing", rows_inserted, pct)

        chunk: List[Dict] = []

        def _open_source():
            if str(gwas_file).endswith(".zip"):
                zf = zipfile.ZipFile(gwas_file)
                name = next(n for n in zf.namelist() if n.endswith(".tsv"))
                return io.TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace")
            return open(gwas_file, encoding="utf-8", errors="replace")

        with _open_source() as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader)
            header_idx = {col: i for i, col in enumerate(header)}

            for row in reader:
                parsed = _parse_row(header_idx, row)
                if parsed:
                    chunk.append(parsed)
                if len(chunk) >= CHUNK_SIZE:
                    await _flush(chunk)
                    chunk = []

            if chunk:
                await _flush(chunk)

        _update_progress("create_indexes", rows_inserted, 95)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_gwas_catalog_rsid ON gwas_catalog_associations (rsid)"
        )
        await conn.execute("ANALYZE gwas_catalog_associations")
        await conn.close()

        elapsed = time.time() - start
        _etl_progress.update(
            running=False, pct=100, step="done",
            total_elapsed=elapsed, completed_at=time.time(),
        )
        return {"rows_inserted": rows_inserted, "elapsed_seconds": elapsed}

    except Exception as exc:
        _etl_progress.update(running=False, error=str(exc))
        raise


def _find_gwas_file() -> Optional[Path]:
    for name in ("gwas_associations.tsv", "gwas_associations_full.zip",
                 "gwas-catalog-associations_ontology-annotated-full.zip",
                 "gwas-catalog-associations-full.zip"):
        candidate = _GWAS_DATA_DIR / name
        if candidate.exists() and candidate.stat().st_size > 10_000:
            return candidate
    return None
