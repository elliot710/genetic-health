from __future__ import annotations

import asyncio
import asyncpg
import csv
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_CLINGEN_DATA_DIR = Path(os.environ.get(
    "CLINGEN_DATA_DIR",
    "/app/data_sources/clingen",
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


def _clean(v: str) -> Optional[str]:
    stripped = v.strip() if v else ""
    return None if stripped in ("", ".", "NA", "N/A", "Not Specified") else stripped


_COLUMNS = [
    "gene_symbol", "gene_hgnc_id", "disease_label", "disease_mondo_id",
    "moi", "classification", "classification_date", "gcep", "report_url",
]

# ClinGen gene-validity TSV header mapping (handles multiple known formats)
_HEADER_MAP = {
    "GENE SYMBOL": "gene_symbol",
    "Gene Symbol": "gene_symbol",
    "GENE ID (HGNC)": "gene_hgnc_id",
    "Gene ID (HGNC)": "gene_hgnc_id",
    "DISEASE LABEL": "disease_label",
    "Disease Label": "disease_label",
    "DISEASE ID (MONDO)": "disease_mondo_id",
    "Disease ID (MONDO)": "disease_mondo_id",
    "MOI": "moi",
    "CLASSIFICATION": "classification",
    "Classification": "classification",
    "CLASSIFICATION DATE": "classification_date",
    "Classification Date": "classification_date",
    "GCEP": "gcep",
    "ONLINE REPORT": "report_url",
    "Online Report": "report_url",
}


def _parse_row(header_idx: Dict[str, int], row: List[str]) -> Optional[Dict]:
    def get(col: str) -> str:
        idx = header_idx.get(col)
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    gene_symbol = _clean(get("gene_symbol"))
    if not gene_symbol:
        return None

    return {
        "gene_symbol": gene_symbol,
        "gene_hgnc_id": _clean(get("gene_hgnc_id")),
        "disease_label": _clean(get("disease_label")),
        "disease_mondo_id": _clean(get("disease_mondo_id")),
        "moi": _clean(get("moi")),
        "classification": _clean(get("classification")),
        "classification_date": _clean(get("classification_date")),
        "gcep": _clean(get("gcep")),
        "report_url": _clean(get("report_url")),
    }


def _build_header_idx(header_row: List[str]) -> Dict[str, int]:
    canonical: Dict[str, int] = {}
    for i, raw_col in enumerate(header_row):
        col = raw_col.strip()
        mapped = _HEADER_MAP.get(col)
        if mapped and mapped not in canonical:
            canonical[mapped] = i
    return canonical


async def run_clingen_etl(
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    if _etl_progress["running"]:
        return {"error": "ETL already running"}

    clingen_file = _clingen_file_path()
    if not clingen_file:
        return {"error": f"No ClinGen file found in {_CLINGEN_DATA_DIR}"}

    _etl_progress.update(
        running=True, step="start", rows=0, pct=0,
        started_at=time.time(), completed_at=None, error=None,
    )
    start = time.time()

    try:
        conn = await asyncpg.connect(_DB_DSN)
        await conn.execute("TRUNCATE TABLE clingen_gene_validity RESTART IDENTITY")
        await conn.execute("DROP INDEX IF EXISTS ix_clingen_gene_symbol")

        rows_inserted = 0
        skipped = 0
        chunk: List[Dict] = []

        with open(clingen_file, encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh, delimiter=",")
            header_row = None
            header_idx: Dict[str, int] = {}
            separator_count = 0

            for row in reader:
                if not row:
                    continue
                first_cell = row[0].strip().strip('"')

                if first_cell.startswith("++++++") or first_cell.startswith("FILE CREATED") \
                        or first_cell.startswith("WEBPAGE") or first_cell.startswith("CLINGEN GENE"):
                    if first_cell.startswith("++++++"):
                        separator_count += 1
                    continue

                if header_row is None and separator_count >= 1:
                    header_row = [c.strip().strip('"') for c in row]
                    header_idx = _build_header_idx(header_row)
                    if not header_idx:
                        return {"error": "Could not parse ClinGen CSV header. Check file format."}
                    continue

                if first_cell.startswith("++++++"):
                    continue

                if header_idx:
                    clean_row = [c.strip().strip('"') for c in row]
                    parsed = _parse_row(header_idx, clean_row)
                    if parsed:
                        chunk.append(parsed)
                    else:
                        skipped += 1

                if len(chunk) >= 5_000:
                    rows_inserted += await _flush(conn, chunk)
                    chunk = []
                    _update_clingen_progress(rows_inserted)
                    if progress_cb:
                        progress_cb("importing", rows_inserted, min(80, rows_inserted // 50))

            if chunk:
                rows_inserted += await _flush(conn, chunk)

        _update_clingen_progress(rows_inserted, pct=95)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_clingen_gene_symbol ON clingen_gene_validity (gene_symbol)"
        )
        await conn.execute("ANALYZE clingen_gene_validity")
        await conn.close()

        elapsed = time.time() - start
        _etl_progress.update(
            running=False, pct=100, step="done",
            total_elapsed=elapsed, completed_at=time.time(),
        )
        return {"rows_inserted": rows_inserted, "skipped": skipped, "elapsed_seconds": elapsed}

    except Exception as exc:
        _etl_progress.update(running=False, error=str(exc))
        raise


async def _flush(conn, chunk: List[Dict]) -> int:
    await conn.copy_records_to_table(
        "clingen_gene_validity",
        records=[
            (
                r["gene_symbol"], r["gene_hgnc_id"], r["disease_label"],
                r["disease_mondo_id"], r["moi"], r["classification"],
                r["classification_date"], r["gcep"], r["report_url"],
            )
            for r in chunk
        ],
        columns=_COLUMNS,
    )
    return len(chunk)


def _clingen_file_path() -> Optional[Path]:
    for name in ("clingen_gene_validity.tsv", "clingen_gene_validity.csv", "gene_validity.tsv", "gene_validity.csv"):
        candidate = _CLINGEN_DATA_DIR / name
        if candidate.exists() and candidate.stat().st_size > 1000:
            return candidate
    return None


def _update_clingen_progress(rows: int, pct: Optional[int] = None) -> None:
    computed_pct = pct if pct is not None else min(80, rows // 50)
    _etl_progress.update(step="importing", rows=rows, pct=computed_pct)
