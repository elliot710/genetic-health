"""
Shared utilities for data source services.

Centralizes:
  • VCF INFO field parsing
  • Type coercion (safe_float, safe_int, clean_str)
  • CADD PHRED score interpretation
  • SQLite cache infrastructure (fingerprinting, validation, DB lifecycle)
  • Common genetic_markers queries (known rsids, marker fingerprint)

Previously duplicated across 10+ files; canonical implementations now live here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func

from ..db.database import async_session_factory
from ..db.models import GeneticMarker

logger = logging.getLogger(__name__)


# ===========================================================================
# Type coercion helpers
# ===========================================================================

def safe_float(v: Any) -> Optional[float]:
    """Convert to float, returning None for null/NaN/invalid."""
    if v is None:
        return None
    try:
        import math
        f = float(v)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def safe_int(v: Any) -> Optional[int]:
    """Convert to int, returning None for null/invalid."""
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def clean_str(v: Optional[str]) -> Optional[str]:
    """Return None for empty / placeholder strings."""
    if v is None:
        return None
    v = v.strip()
    return None if v in (".", "NA", "nan", "", "-", "N/A") else v


# ===========================================================================
# VCF parsing
# ===========================================================================

def parse_vcf_info(info_str: str) -> Dict[str, str]:
    """Parse a VCF INFO field string into a key→value dict.

    Flag fields (no '=') get value "1" for truthy presence checks.
    """
    result: Dict[str, str] = {}
    for token in info_str.split(";"):
        if "=" in token:
            k, _, v = token.partition("=")
            result[k.strip()] = v.strip()
        elif token.strip():
            result[token.strip()] = "1"
    return result


# ===========================================================================
# CADD score interpretation
# ===========================================================================

def interpret_cadd(phred: Optional[float]) -> Optional[str]:
    """Human-readable interpretation of a CADD PHRED score."""
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


# ===========================================================================
# Common database queries
# ===========================================================================

async def load_known_rsids() -> Set[str]:
    """Load all non-null rsids from the genetic_markers table."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(GeneticMarker.rsid).where(GeneticMarker.rsid.isnot(None))
        )
        rsids = {r[0] for r in result.all()}
    logger.info("Loaded %d known rsids from genetic_markers", len(rsids))
    return rsids


async def get_marker_fingerprint() -> str:
    """Return a fingerprint string based on genetic_markers row count."""
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(GeneticMarker.id)))
        count = result.scalar() or 0
    return str(count)


# ===========================================================================
# SQLite cache infrastructure
# ===========================================================================

def get_file_fingerprint(path: Path) -> str:
    """Return a fingerprint string for a single file (name:size)."""
    try:
        return f"{path.name}:{path.stat().st_size}"
    except OSError:
        return path.name


def get_multi_file_fingerprint(paths: List[Path]) -> str:
    """Return an MD5 fingerprint for multiple files."""
    parts = []
    for p in sorted(paths):
        try:
            parts.append(f"{p.name}:{p.stat().st_size}")
        except OSError:
            parts.append(p.name)
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def is_cache_valid(
    sqlite_file: Path,
    meta_file: Path,
    marker_fp: str,
    file_fp: str,
    *,
    marker_key: str = "marker_fingerprint",
    file_key: str = "file_fingerprint",
) -> bool:
    """Check if an existing SQLite cache matches current fingerprints."""
    if not sqlite_file.exists() or not meta_file.exists():
        return False
    try:
        meta = json.loads(meta_file.read_text())
        return (
            meta.get(marker_key) == marker_fp
            and meta.get(file_key) == file_fp
        )
    except Exception:
        return False


def save_cache_meta(
    meta_file: Path,
    marker_fp: str,
    file_fp: str,
    count: int,
    *,
    marker_key: str = "marker_fingerprint",
    file_key: str = "file_fingerprint",
    extra: Optional[Dict[str, Any]] = None,
):
    """Save cache metadata for validation on next load."""
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        marker_key: marker_fp,
        file_key: file_fp,
        "variant_count": count,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if extra:
        meta.update(extra)
    meta_file.write_text(json.dumps(meta, indent=2))


def open_cache_db(path: Path, *, cache_size_mb: int = 16) -> sqlite3.Connection:
    """Open a SQLite cache DB in WAL mode with tuned pragmas."""
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA cache_size=-{cache_size_mb * 1024}")
    return conn


def create_cache_db(
    path: Path,
    table_ddl: str,
) -> sqlite3.Connection:
    """Create a new SQLite cache DB with the given table DDL.

    Returns a connection to a .tmp file.  Call finalize_cache_db() when done.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")  # faster during bulk insert
    conn.execute(table_ddl)
    return conn


def finalize_cache_db(conn: sqlite3.Connection, tmp: Path, final: Path):
    """Checkpoint WAL, close, and rename tmp → final."""
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    if final.exists():
        final.unlink()
    for suffix in ["-wal", "-shm"]:
        f = tmp.with_name(tmp.name + suffix)
        if f.exists():
            f.unlink()
    tmp.rename(final)


# ===========================================================================
# Data source file availability scan
# ===========================================================================

def scan_data_source_availability(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Scan data_sources directories and report what files are present with indexes.

    Returns a dict keyed by source name, each with:
      - exists (bool): directory is present
      - file_count (int): number of data files
      - indexed_count (int): files with .tbi or .csi index
      - total_size_mb (float): sum of all file sizes
      - files (list[dict]): per-file name, size_mb, indexed
    """
    import os as _os

    if base_dir is None:
        base_dir = Path(_os.environ.get("DATA_SOURCES_DIR", "/app/data_sources"))

    source_dirs: Dict[str, Path] = {
        "clinvar": base_dir / "clinvar",
        "1000G": base_dir / "1000G",
        "ensembl_vep": base_dir / "ensembl" / "homo_sapiens" / "variation" / "vcf_vep",
        "gnomad": base_dir / "gnomad",
        "gnomad_v2": base_dir / "gnomad_v2",
        "alpha_missense": base_dir / "alpha_missense",
    }

    # Sources whose data lives in subdirectories — scan recursively one level
    _RECURSE: set[str] = {"clinvar"}

    result: Dict[str, Any] = {}
    for name, path in source_dirs.items():
        info: Dict[str, Any] = {
            "dir": str(path),
            "exists": path.exists(),
            "file_count": 0,
            "indexed_count": 0,
            "total_size_mb": 0.0,
            "files": [],
        }
        if path.exists():
            try:
                # For sources with subdirectories, collect files one level deep
                if name in _RECURSE:
                    candidates = [
                        f
                        for d in [path, *[sub for sub in path.iterdir() if sub.is_dir()]]
                        for f in d.iterdir()
                        if f.is_file()
                    ]
                else:
                    candidates = [f for f in path.iterdir() if f.is_file()]

                for f in sorted(candidates):
                    # Skip index files themselves in the count
                    if f.name.endswith(('.tbi', '.csi', '.bai')):
                        continue
                    has_index = (
                        Path(str(f) + '.tbi').exists()
                        or Path(str(f) + '.csi').exists()
                    )
                    size_mb = round(f.stat().st_size / 1_000_000, 1)
                    info['file_count'] += 1
                    info['total_size_mb'] += size_mb
                    if has_index:
                        info['indexed_count'] += 1
                    info['files'].append({
                        'name': f.name,
                        'size_mb': size_mb,
                        'indexed': has_index,
                    })
                info['total_size_mb'] = round(info['total_size_mb'], 1)
            except Exception as e:
                info['error'] = str(e)
        result[name] = info
    return result


def log_data_source_availability(base_dir: Optional[Path] = None) -> None:
    """Log a human-readable summary of available data sources at startup."""
    sources = scan_data_source_availability(base_dir)
    for name, info in sources.items():
        if not info['exists']:
            logger.warning("📂 %-20s NOT FOUND (%s)", name, info['dir'])
        elif info['file_count'] == 0:
            logger.warning("📂 %-20s empty directory", name)
        else:
            vcf_indexed = info['indexed_count']
            # Distinguish "indexed" (has .tbi) from total — TSV files don't use tabix
            vcf_files = sum(1 for f in info['files'] if f['name'].endswith(('.vcf.gz', '.bcf.gz')))
            tsv_files = info['file_count'] - vcf_files
            if vcf_files and tsv_files:
                status = f"{info['file_count']} files ({tsv_files} TSV/text, {vcf_files} VCF), {vcf_indexed}/{vcf_files} VCF indexed, {info['total_size_mb']} MB"
            else:
                status = f"{info['file_count']} files, {info['indexed_count']} indexed, {info['total_size_mb']} MB"
            logger.info("📂 %-20s %s", name, status)

