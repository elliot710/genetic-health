"""
ClinVar service — PostgreSQL-backed lookup (clinvar_variants table) with
direct-file fallback (SQLite cache from variant_summary.txt.gz) when the
PG table is empty (ETL not run).

Usage:
    svc = get_clinvar_local_service()
    result = await svc.lookup("rs1234")
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
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.datasource_models import ClinVarSummaryRecord, ClinVarVcfRecord
from ..db.models import ClinVarVariant, ClinVarGeneCondition, ClinVarGeneStats, GeneticMarker
from .datasource_utils import (
    get_file_fingerprint,
    save_cache_meta,
    open_cache_db,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ClinVar direct-file cache constants
# ---------------------------------------------------------------------------

_CLINVAR_DATA_DIR = Path(os.environ.get(
    "CLINVAR_DATA_DIR",
    "/app/data_sources/clinvar",
))
_CACHE_DIR = _CLINVAR_DATA_DIR / ".clinvar_cache"
_SQLITE_FILE = _CACHE_DIR / "clinvar_direct.db"
_META_FILE = _CACHE_DIR / "clinvar_direct_meta.json"
_DIRECT_BATCH_SIZE = 5_000
# Increment when the SQLite schema or stored data shape changes.
# Old caches with a different version will be rebuilt automatically.
_CACHE_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# ClinVarDirectService — SQLite cache built from local variant_summary.txt.gz
# ---------------------------------------------------------------------------

class ClinVarDirectService:
    """SQLite-backed ClinVar lookup built from variant_summary.txt.gz.

    Activated automatically when the clinvar_variants PG table is empty.
    Also provides gene-condition and gene-stats lookups from local TSV files.
    """

    def __init__(self):
        self._db: Optional[sqlite3.Connection] = None
        self._variant_count: int = 0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._gene_conditions: Optional[Dict[str, List[Dict[str, str]]]] = None
        self._gene_stats: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._gene_data_lock = asyncio.Lock()

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
                logger.error("ClinVar direct cache failed: %s", e, exc_info=True)
            self._loaded = True
        return self._db is not None

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not await self.ensure_loaded():
            return None
        return await asyncio.to_thread(self._lookup_one, rsid)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not rsids:
            return {}
        if not await self.ensure_loaded():
            return {}
        return await asyncio.to_thread(self._lookup_batch_sync, rsids)

    async def lookup_by_position(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[Dict[str, Any]]:
        vcf_path = self._find_vcf()
        tbi_path = Path(str(vcf_path) + ".tbi") if vcf_path else None
        if not vcf_path or not vcf_path.exists() or not (tbi_path and tbi_path.exists()):
            return None
        return await asyncio.to_thread(self._tabix_lookup, vcf_path, chrom, pos, ref, alt)

    # Gene enrichment from local TSV files

    async def get_gene_conditions(self, genes: List[str]) -> Dict[str, List[Dict[str, str]]]:
        await self._ensure_gene_data()
        if not self._gene_conditions:
            return {}
        return {g: self._gene_conditions[g] for g in genes if g in self._gene_conditions}

    async def get_gene_stats(self, genes: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        await self._ensure_gene_data()
        if not self._gene_stats:
            return {}
        return {g: self._gene_stats[g] for g in genes if g in self._gene_stats}

    async def _ensure_gene_data(self):
        if self._gene_conditions is not None:
            return
        async with self._gene_data_lock:
            if self._gene_conditions is not None:
                return
            self._gene_conditions = await asyncio.to_thread(self._parse_gene_conditions)
            self._gene_stats = await asyncio.to_thread(self._parse_gene_stats)

    def _parse_gene_conditions(self) -> Dict[str, List[Dict[str, str]]]:
        fpath = self._find_gene_conditions_file()
        if not fpath:
            return {}
        result: Dict[str, List[Dict[str, str]]] = {}
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(
                (line for line in fh if not line.startswith("##")), delimiter="\t"
            )
            header = next(reader)
            idx = {name: i for i, name in enumerate(header)}
            I_GENE, I_DIS = idx.get("AssociatedGenes"), idx.get("DiseaseName")
            I_SRC, I_SID, I_MIM = idx.get("SourceName"), idx.get("SourceID"), idx.get("DiseaseMIM")
            if I_GENE is None or I_DIS is None:
                return {}
            for row in reader:
                if len(row) <= max(I_GENE, I_DIS):
                    continue
                genes_str, disease = row[I_GENE].strip(), row[I_DIS].strip()
                if not genes_str or not disease:
                    continue
                entry = {
                    "disease": disease,
                    "source": (row[I_SRC].strip() if I_SRC is not None and I_SRC < len(row) else "") or "",
                    "source_id": (row[I_SID].strip() if I_SID is not None and I_SID < len(row) else "") or "",
                    "disease_mim": (row[I_MIM].strip() if I_MIM is not None and I_MIM < len(row) else "") or "",
                }
                for gene in genes_str.split(","):
                    gene = gene.strip()
                    if gene:
                        result.setdefault(gene, []).append(entry)
        logger.info("ClinVar: parsed %d genes from gene_condition_source_id.txt", len(result))
        return result

    def _parse_gene_stats(self) -> Dict[str, List[Dict[str, Any]]]:
        fpath = self._find_gene_stats_file()
        if not fpath:
            return {}

        def _int(v):
            v = (v or "").strip()
            return int(v) if v and v != "-" else 0

        result: Dict[str, List[Dict[str, Any]]] = {}
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(
                (line for line in fh if not line.startswith("#Overview") and not line.startswith("##")),
                delimiter="\t",
            )
            header = next(reader)
            idx = {name: i for i, name in enumerate(header)}
            I_SYM = idx.get("#Symbol", idx.get("Symbol"))
            I_GID, I_TS, I_TA = idx.get("GeneID"), idx.get("Total_submissions"), idx.get("Total_alleles")
            I_PLP = idx.get("Alleles_reported_Pathogenic_Likely_pathogenic")
            I_US, I_WC, I_MIM = idx.get("Number_uncertain"), idx.get("Number_with_conflicts"), idx.get("Gene_MIM_number")
            if I_SYM is None:
                return {}

            def _safe(i, row):
                return row[i].strip() if i is not None and i < len(row) else ""

            for row in reader:
                symbol = _safe(I_SYM, row)
                if not symbol or symbol in result:
                    continue
                result[symbol] = [{"gene": symbol, "gene_id": _safe(I_GID, row) or "",
                    "total_submissions": _int(_safe(I_TS, row)),
                    "total_alleles": _int(_safe(I_TA, row)),
                    "pathogenic_likely_pathogenic": _int(_safe(I_PLP, row)),
                    "gene_mim": _safe(I_MIM, row) or "",
                    "uncertain": _int(_safe(I_US, row)),
                    "with_conflicts": _int(_safe(I_WC, row)),
                }]
        logger.info("ClinVar: parsed %d genes from gene_specific_summary.txt", len(result))
        return result

    # SQLite operations

    def _lookup_one(self, rsid: str) -> Optional[Dict[str, Any]]:
        if not self._db:
            return None
        row = self._db.execute("SELECT data FROM clinvar_data WHERE rsid = ?", (rsid,)).fetchone()
        return json.loads(zlib.decompress(row[0])) if row else None

    def _lookup_batch_sync(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not self._db:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for start in range(0, len(rsids), 500):
            chunk = rsids[start:start + 500]
            placeholders = ",".join("?" * len(chunk))
            rows = self._db.execute(
                f"SELECT rsid, data FROM clinvar_data WHERE rsid IN ({placeholders})", chunk
            ).fetchall()
            for rsid, blob in rows:
                results[rsid] = json.loads(zlib.decompress(blob))
        return results

    # Cache build

    async def _load_cache(self):
        tsv_path = self._find_tsv()
        if not tsv_path:
            logger.warning("ClinVar direct: variant_summary.txt.gz not found in %s", _CLINVAR_DATA_DIR)
            return
        file_fp = get_file_fingerprint(tsv_path)

        # Use existing cache if source file is unchanged (marker_fp not required —
        # allows pre-built caches to load on a fresh server with no uploaded data).
        if _SQLITE_FILE.exists() and _META_FILE.exists():
            try:
                meta = json.loads(_META_FILE.read_text())
                if (
                    meta.get("file_fingerprint") == file_fp
                    and meta.get("schema_version") == _CACHE_SCHEMA_VERSION
                    and meta.get("variant_count", 0) > 0
                ):
                    self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE)
                    row = self._db.execute("SELECT COUNT(*) FROM clinvar_data").fetchone()
                    self._variant_count = row[0] if row else 0
                    logger.info("ClinVar direct: opened cache with %d variants", self._variant_count)
                    return
            except Exception:
                pass

        logger.info(
            "ClinVar direct: building full cache from %s (schema v%d) — all clinical variants...",
            tsv_path.name, _CACHE_SCHEMA_VERSION,
        )
        count = await asyncio.to_thread(self._scan_tsv_to_sqlite, tsv_path)
        save_cache_meta(_META_FILE, "all_variants", file_fp, count,
                        extra={"schema_version": _CACHE_SCHEMA_VERSION})
        self._db = await asyncio.to_thread(open_cache_db, _SQLITE_FILE)
        self._variant_count = count
        logger.info("ClinVar direct cache built: %d variants", count)

    def _scan_tsv_to_sqlite(self, tsv_path: Path) -> int:
        tmp = _SQLITE_FILE.with_suffix(".tmp")
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            tmp.unlink()
        conn = sqlite3.connect(str(tmp), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("CREATE TABLE clinvar_data (rsid TEXT PRIMARY KEY, data BLOB NOT NULL)")

        assembly_pref = "GRCh37"
        aggregated: Dict[str, Dict] = {}
        t0 = time.time()

        with gzip.open(str(tsv_path), "rt", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    rec = ClinVarSummaryRecord.from_row(row)
                except Exception:
                    continue
                if not rec.rsid:
                    continue
                ann = rec.to_annotation()
                if rec.rsid not in aggregated:
                    aggregated[rec.rsid] = ann
                else:
                    existing = aggregated[rec.rsid]
                    if rec.assembly == assembly_pref:
                        aggregated[rec.rsid] = ann
                    elif rec.clinical_significance:
                        sigs = existing.get("clinical_significances", [])
                        if rec.clinical_significance not in sigs:
                            sigs.append(rec.clinical_significance)
                        existing["clinical_significances"] = sigs
                    for cond in ann.get("conditions", []):
                        if cond not in existing.get("conditions", []):
                            existing.setdefault("conditions", []).append(cond)

        count = 0
        batch: list = []
        for rsid, ann in aggregated.items():
            batch.append((rsid, zlib.compress(json.dumps(ann).encode("utf-8"), level=1)))
            count += 1
            if len(batch) >= _DIRECT_BATCH_SIZE:
                conn.executemany("INSERT OR REPLACE INTO clinvar_data (rsid, data) VALUES (?, ?)", batch)
                conn.commit()
                batch.clear()
        if batch:
            conn.executemany("INSERT OR REPLACE INTO clinvar_data (rsid, data) VALUES (?, ?)", batch)
            conn.commit()

        elapsed = time.time() - t0
        logger.info("[ClinVar direct] Scanned %s: %d rsids cached in %.1fs", tsv_path.name, count, elapsed)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        for suffix in ["-wal", "-shm"]:
            f = tmp.with_name(tmp.name + suffix)
            if f.exists():
                f.unlink()
        if _SQLITE_FILE.exists():
            _SQLITE_FILE.unlink()
        tmp.rename(_SQLITE_FILE)
        return count

    def _tabix_lookup(self, vcf_path: Path, chrom: str, pos: int, ref: str, alt: str) -> Optional[Dict[str, Any]]:
        try:
            import pysam
        except ImportError:
            return None
        chrom_clean = chrom.replace("chr", "")
        ref_upper, alt_upper = ref.upper(), alt.upper()
        try:
            tabix = pysam.TabixFile(str(vcf_path))
        except Exception as e:
            logger.debug("ClinVar tabix open failed: %s", e)
            return None
        try:
            for row_str in tabix.fetch(chrom_clean, pos - 1, pos):
                parts = row_str.split("\t", 9)
                if len(parts) < 8:
                    continue
                if parts[3].upper() != ref_upper or parts[4].upper() != alt_upper:
                    continue
                try:
                    rec = ClinVarVcfRecord.from_vcf_fields(
                        parts[0], int(parts[1]), parts[2], parts[3], parts[4], parts[7]
                    )
                    return rec.to_annotation()
                except Exception:
                    continue
        except ValueError:
            pass
        except Exception as e:
            logger.debug("ClinVar tabix fetch error: %s", e)
        finally:
            tabix.close()
        return None

    def _find_tsv(self) -> Optional[Path]:
        for p in [_CLINVAR_DATA_DIR / "tsv" / "variant_summary.txt.gz", _CLINVAR_DATA_DIR / "variant_summary.txt.gz"]:
            if p.exists():
                return p
        return None

    def _find_vcf(self) -> Optional[Path]:
        for p in [_CLINVAR_DATA_DIR / "vcf" / "clinvar.vcf.gz", _CLINVAR_DATA_DIR / "clinvar.vcf.gz"]:
            if p.exists() and Path(str(p) + ".tbi").exists():
                return p
        return None

    def _find_gene_conditions_file(self) -> Optional[Path]:
        for p in [_CLINVAR_DATA_DIR / "tsv" / "gene_condition_source_id.txt", _CLINVAR_DATA_DIR / "gene_condition_source_id.txt"]:
            if p.exists():
                return p
        return None

    def _find_gene_stats_file(self) -> Optional[Path]:
        for p in [_CLINVAR_DATA_DIR / "tsv" / "gene_specific_summary.txt", _CLINVAR_DATA_DIR / "gene_specific_summary.txt"]:
            if p.exists():
                return p
        return None


_direct_instance: Optional[ClinVarDirectService] = None


def get_clinvar_direct_service() -> ClinVarDirectService:
    global _direct_instance
    if _direct_instance is None:
        _direct_instance = ClinVarDirectService()
    return _direct_instance


# ---------------------------------------------------------------------------
# ClinVarLocalService — PostgreSQL-backed with direct-file fallback
# ---------------------------------------------------------------------------


class ClinVarLocalService:
    """PostgreSQL-backed ClinVar lookup service."""

    def __init__(self):
        self._variant_count: Optional[int] = None
        self._available: Optional[bool] = None
        self._direct = None  # ClinVarDirectService fallback when PG is empty

    # ------------------------------------------------------------------
    # Compat properties (match old interface)
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when get_import_status has been checked or assumed available."""
        return self._available if self._available is not None else True

    @property
    def is_loaded(self) -> bool:
        """Always True — data lives in PG, no in-memory loading required."""
        return self._variant_count is not None and self._variant_count > 0

    @property
    def variant_count(self) -> int:
        return self._variant_count or 0

    @property
    def vcf_variant_count(self) -> int:
        return 0  # Merged into same table

    @property
    def files_loaded(self) -> List[str]:
        return ["postgresql"]

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    async def ensure_loaded(self) -> bool:
        """Check that the clinvar_variants table has data.
        Falls back to the direct-file SQLite cache when PG is empty.
        """
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(ClinVarVariant)
                )
                self._variant_count = result.scalar() or 0
            self._available = self._variant_count > 0
            if self._available:
                logger.info("ClinVar PG: %d rows available", self._variant_count)
            else:
                logger.warning(
                    "ClinVar PG: table empty — trying direct file cache"
                )
                direct = get_clinvar_direct_service()
                ok = await direct.ensure_loaded()
                if ok:
                    self._direct = direct
                    self._variant_count = direct.variant_count
                    self._available = True
                    logger.info(
                        "ClinVar direct cache: %d variants available",
                        direct.variant_count,
                    )
            return self._available
        except Exception as e:
            logger.warning("ClinVar PG check failed: %s", e)
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Core lookup (PG primary, direct-file fallback)
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a single rsid. Tries PG first, then direct cache."""
        # Try PG
        direct = getattr(self, "_direct", None)
        if self._variant_count and (not direct or self._variant_count > (direct.variant_count or 0)):
            async with async_session_factory() as session:
                result = await self._lookup_impl(session, rsid)
                if result and result.get("found"):
                    return result
        # Fallback to direct-file cache
        if direct:
            result = await direct.lookup(rsid)
            if result and result.get("found"):
                await self._enrich_direct_result(direct, result)
            return result
        async with async_session_factory() as session:
            return await self._lookup_impl(session, rsid)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup using IN-clause. Falls back to direct cache for misses."""
        if not rsids:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        batch_size = 2000
        total = len(rsids)
        total_batches = (total + batch_size - 1) // batch_size
        found_count = 0
        import time as _time
        t0 = _time.monotonic()
        async with async_session_factory() as session:
            for i in range(0, len(rsids), batch_size):
                chunk = rsids[i:i + batch_size]
                batch_num = i // batch_size + 1
                # Yield to event loop between chunks so HTTP handlers can run
                if i > 0:
                    await asyncio.sleep(0.01)
                # Batch fetch all ClinVar rows for this chunk
                result = await session.execute(
                    select(ClinVarVariant).where(ClinVarVariant.rsid.in_(chunk))
                )
                all_rows = result.scalars().all()

                # Group rows by rsid
                by_rsid: Dict[str, list] = {}
                for row in all_rows:
                    by_rsid.setdefault(row.rsid, []).append(row)

                # Collect all unique genes for batch gene lookups
                all_genes: set = set()
                for rows in by_rsid.values():
                    for r in rows:
                        if r.gene:
                            all_genes.add(r.gene)

                # Batch gene conditions + stats
                gene_cond_map: Dict[str, list] = {}
                gene_stats_map: Dict[str, list] = {}
                if all_genes:
                    gene_list = list(all_genes)
                    gc_result = await session.execute(
                        select(ClinVarGeneCondition).where(ClinVarGeneCondition.gene.in_(gene_list))
                    )
                    for gc in gc_result.scalars().all():
                        gene_cond_map.setdefault(gc.gene, []).append({
                            "disease": gc.disease_name,
                            "source": gc.source_name or "",
                            "source_id": gc.source_id or "",
                            "disease_mim": gc.disease_mim or "",
                        })
                    gs_result = await session.execute(
                        select(ClinVarGeneStats).where(ClinVarGeneStats.gene.in_(gene_list))
                    )
                    for gs in gs_result.scalars().all():
                        gene_stats_map.setdefault(gs.gene, []).append({
                            "gene": gs.gene,
                            "gene_id": gs.gene_id or "",
                            "total_submissions": gs.total_submissions,
                            "total_alleles": gs.total_alleles,
                            "pathogenic_likely_pathogenic": gs.pathogenic_likely_pathogenic,
                            "gene_mim": gs.gene_mim or "",
                            "uncertain": gs.uncertain_significance,
                            "with_conflicts": gs.with_conflicts,
                        })

                # Aggregate per rsid
                for rsid_key in chunk:
                    rows = by_rsid.get(rsid_key)
                    if not rows:
                        results[rsid_key] = {"found": False, "source": "clinvar_local"}
                        continue
                    results[rsid_key] = self._aggregate_rows(rsid_key, rows, gene_cond_map, gene_stats_map)
                    found_count += 1

                if batch_num % 10 == 0 or batch_num == total_batches:
                    elapsed = _time.monotonic() - t0
                    rate = (i + len(chunk)) / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"  ClinVar Local batch {batch_num}/{total_batches}: "
                        f"{i + len(chunk)}/{total} queried, {found_count} found "
                        f"({rate:.0f} rsids/s, {elapsed:.1f}s elapsed)"
                    )

        elapsed = _time.monotonic() - t0
        logger.info(f"  ClinVar Local complete: {found_count}/{total} found in {elapsed:.1f}s")

        # If PG returned nothing and we have a direct-file cache, fill in misses
        direct = getattr(self, "_direct", None)
        if direct and found_count == 0:
            missed = [r for r, v in results.items() if not v or not v.get("found")]
            if missed:
                direct_results = await direct.lookup_batch(missed)
                # Collect all unique genes to enrich with gene conditions/stats
                all_direct_genes: set = set()
                for rsid_key, val in direct_results.items():
                    if val and val.get("found"):
                        results[rsid_key] = val
                        found_count += 1
                        for g in val.get("genes", []):
                            all_direct_genes.add(g)

                # Enrich with gene conditions + stats from local files
                if all_direct_genes:
                    gene_list = list(all_direct_genes)
                    gc_map = await direct.get_gene_conditions(gene_list)
                    gs_map = await direct.get_gene_stats(gene_list)
                    for rsid_key, val in results.items():
                        if not val or not val.get("found"):
                            continue
                        genes = val.get("genes", [])
                        if not genes:
                            continue
                        if not val.get("gene_conditions"):
                            gc_list: list = []
                            for g in genes:
                                gc_list.extend(gc_map.get(g, []))
                            if gc_list:
                                val["gene_conditions"] = gc_list[:20]
                        if not val.get("gene_stats"):
                            gs_list: list = []
                            for g in genes:
                                gs_list.extend(gs_map.get(g, []))
                            if gs_list:
                                val["gene_stats"] = gs_list

                logger.info(
                    "  ClinVar direct fallback: %d/%d found", found_count, len(missed)
                )

        return results

    def _aggregate_rows(
        self,
        rsid: str,
        rows: list,
        gene_cond_map: Dict[str, list] = None,
        gene_stats_map: Dict[str, list] = None,
    ) -> Dict[str, Any]:
        """Aggregate multiple ClinVar rows for a single rsid into a result dict."""
        clinical_sigs: List[str] = []
        conditions: List[str] = []
        genes: List[str] = []
        variation_ids: set = set()
        allele_ids: set = set()
        result_entries: List[Dict[str, Any]] = []
        allele_freqs: Dict[str, float] = {}
        mol_consequences: List[str] = []
        oncogenicity_list: List[str] = []
        somatic_impact_list: List[str] = []
        conflicting_list: List[str] = []

        for r in rows:
            if r.clinical_significance and r.clinical_significance not in clinical_sigs:
                clinical_sigs.append(r.clinical_significance)
            if r.conditions and r.conditions not in ("not provided", "not_provided"):
                cond = r.conditions.replace("_", " ")
                if cond not in conditions:
                    conditions.append(cond)
            if r.gene and r.gene not in genes:
                genes.append(r.gene)
            if r.variation_id:
                variation_ids.add(r.variation_id)
            if r.allele_id:
                allele_ids.add(r.allele_id)
            if r.data_source == "tsv":
                result_entries.append({
                    "uid": r.variation_id,
                    "allele_id": r.allele_id,
                    "title": f"{rsid} - {r.conditions}" if r.conditions else rsid,
                    "accession": r.rcv_accession,
                    "clinical_significance": [r.clinical_significance] if r.clinical_significance else [],
                    "conditions": [r.conditions] if r.conditions and r.conditions != "not provided" else [],
                    "variation_type": r.variation_type,
                    "gene": r.gene,
                    "review_status": r.review_status,
                    "origin": r.origin,
                    "chromosome": r.chromosome,
                    "start": str(r.start_pos) if r.start_pos else "",
                    "stop": str(r.stop_pos) if r.stop_pos else "",
                    "hgvs_nucleotide": r.hgvs_nucleotide or "",
                    "hgvs_protein": r.hgvs_protein or "",
                })
            if r.data_source == "vcf":
                if r.af_exac is not None and "exac" not in allele_freqs:
                    allele_freqs["exac"] = r.af_exac
                if r.af_tgp is not None and "tgp" not in allele_freqs:
                    allele_freqs["tgp"] = r.af_tgp
                if r.af_esp is not None and "esp" not in allele_freqs:
                    allele_freqs["esp"] = r.af_esp
                if r.molecular_consequence and r.molecular_consequence not in mol_consequences:
                    mol_consequences.append(r.molecular_consequence)
                if r.oncogenicity and r.oncogenicity not in oncogenicity_list:
                    oncogenicity_list.append(r.oncogenicity)
                if r.somatic_clinical_impact and r.somatic_clinical_impact not in somatic_impact_list:
                    somatic_impact_list.append(r.somatic_clinical_impact)
                if r.conflicting_classifications and r.conflicting_classifications not in conflicting_list:
                    conflicting_list.append(r.conflicting_classifications)

        # Gene conditions + stats from pre-fetched maps
        gene_conditions: List[Dict[str, str]] = []
        gene_stats_list: List[Dict[str, Any]] = []
        if genes and gene_cond_map:
            for g in genes:
                gene_conditions.extend(gene_cond_map.get(g, []))
            gene_conditions = gene_conditions[:20]
        if genes and gene_stats_map:
            for g in genes:
                gene_stats_list.extend(gene_stats_map.get(g, []))

        vcf_data: Optional[Dict[str, Any]] = None
        if allele_freqs or mol_consequences or oncogenicity_list or somatic_impact_list:
            vcf_data = {}
            if allele_freqs:
                vcf_data["allele_frequencies"] = allele_freqs
            if mol_consequences:
                vcf_data["molecular_consequences"] = mol_consequences[:10]
            if oncogenicity_list:
                vcf_data["oncogenicity"] = oncogenicity_list
            if somatic_impact_list:
                vcf_data["somatic_clinical_impact"] = somatic_impact_list
            if conflicting_list:
                vcf_data["conflicting_classifications"] = conflicting_list[:5]

        review_statuses = list({r.review_status for r in rows if r.review_status})

        output: Dict[str, Any] = {
            "found": True,
            "source": "clinvar_local",
            "count": len(rows),
            "ids": list(variation_ids)[:20],
            "allele_ids": list(allele_ids)[:20],
            "clinical_significances": clinical_sigs,
            "conditions": conditions,
            "genes": genes,
            "review_statuses": review_statuses,
            "has_conflicting_interpretations": bool(conflicting_list),
            "total_submissions": 0,
            "pubmed_ids": [],
            "cross_references": [],
            "gene_conditions": gene_conditions,
            "gene_stats": gene_stats_list,
            "disease_details": [],
            "entries": result_entries[:10],
        }
        if vcf_data:
            output["vcf_data"] = vcf_data
        return output

    async def _enrich_direct_result(self, direct, result: Dict[str, Any]):
        """Enrich a direct-cache result with gene conditions/stats from local files."""
        genes = result.get("genes", [])
        if not genes:
            return
        if not result.get("gene_conditions"):
            gc_map = await direct.get_gene_conditions(genes)
            gc_list: list = []
            for g in genes:
                gc_list.extend(gc_map.get(g, []))
            if gc_list:
                result["gene_conditions"] = gc_list[:20]
        if not result.get("gene_stats"):
            gs_map = await direct.get_gene_stats(genes)
            gs_list: list = []
            for g in genes:
                gs_list.extend(gs_map.get(g, []))
            if gs_list:
                result["gene_stats"] = gs_list

    async def _lookup_impl(self, session: AsyncSession, rsid: str) -> Optional[Dict[str, Any]]:
        """Single rsid lookup within an existing session."""
        # Fetch all ClinVar rows for this rsid
        result = await session.execute(
            select(ClinVarVariant).where(ClinVarVariant.rsid == rsid)
        )
        rows = result.scalars().all()

        if not rows:
            return {"found": False, "source": "clinvar_local"}

        # Aggregate data across all rows
        clinical_sigs: List[str] = []
        conditions: List[str] = []
        genes: List[str] = []
        variation_ids: set = set()
        allele_ids: set = set()
        result_entries: List[Dict[str, Any]] = []

        allele_freqs: Dict[str, float] = {}
        mol_consequences: List[str] = []
        oncogenicity_list: List[str] = []
        somatic_impact_list: List[str] = []
        conflicting_list: List[str] = []

        for r in rows:
            # Clinical significance
            if r.clinical_significance and r.clinical_significance not in clinical_sigs:
                clinical_sigs.append(r.clinical_significance)

            # Conditions
            if r.conditions and r.conditions not in ("not provided", "not_provided"):
                cond = r.conditions.replace("_", " ")
                if cond not in conditions:
                    conditions.append(cond)

            # Gene
            if r.gene and r.gene not in genes:
                genes.append(r.gene)

            if r.variation_id:
                variation_ids.add(r.variation_id)
            if r.allele_id:
                allele_ids.add(r.allele_id)

            # Entries
            if r.data_source == "tsv":
                result_entries.append({
                    "uid": r.variation_id,
                    "allele_id": r.allele_id,
                    "title": f"{rsid} - {r.conditions}" if r.conditions else rsid,
                    "accession": r.rcv_accession,
                    "clinical_significance": [r.clinical_significance] if r.clinical_significance else [],
                    "conditions": [r.conditions] if r.conditions and r.conditions != "not provided" else [],
                    "variation_type": r.variation_type,
                    "gene": r.gene,
                    "review_status": r.review_status,
                    "origin": r.origin,
                    "chromosome": r.chromosome,
                    "start": str(r.start_pos) if r.start_pos else "",
                    "stop": str(r.stop_pos) if r.stop_pos else "",
                    "hgvs_nucleotide": r.hgvs_nucleotide or "",
                    "hgvs_protein": r.hgvs_protein or "",
                })

            # VCF-derived fields
            if r.data_source == "vcf":
                if r.af_exac is not None and "exac" not in allele_freqs:
                    allele_freqs["exac"] = r.af_exac
                if r.af_tgp is not None and "tgp" not in allele_freqs:
                    allele_freqs["tgp"] = r.af_tgp
                if r.af_esp is not None and "esp" not in allele_freqs:
                    allele_freqs["esp"] = r.af_esp
                if r.molecular_consequence and r.molecular_consequence not in mol_consequences:
                    mol_consequences.append(r.molecular_consequence)
                if r.oncogenicity and r.oncogenicity not in oncogenicity_list:
                    oncogenicity_list.append(r.oncogenicity)
                if r.somatic_clinical_impact and r.somatic_clinical_impact not in somatic_impact_list:
                    somatic_impact_list.append(r.somatic_clinical_impact)
                if r.conflicting_classifications and r.conflicting_classifications not in conflicting_list:
                    conflicting_list.append(r.conflicting_classifications)

        # Gene conditions
        gene_conditions: List[Dict[str, str]] = []
        if genes:
            gc_result = await session.execute(
                select(ClinVarGeneCondition).where(ClinVarGeneCondition.gene.in_(genes))
            )
            for gc in gc_result.scalars().all():
                gene_conditions.append({
                    "disease": gc.disease_name,
                    "source": gc.source_name or "",
                    "source_id": gc.source_id or "",
                    "disease_mim": gc.disease_mim or "",
                })
        gene_conditions = gene_conditions[:20]

        # Gene stats
        gene_stats_list: List[Dict[str, Any]] = []
        if genes:
            gs_result = await session.execute(
                select(ClinVarGeneStats).where(ClinVarGeneStats.gene.in_(genes))
            )
            for gs in gs_result.scalars().all():
                gene_stats_list.append({
                    "gene": gs.gene,
                    "gene_id": gs.gene_id or "",
                    "total_submissions": gs.total_submissions,
                    "total_alleles": gs.total_alleles,
                    "pathogenic_likely_pathogenic": gs.pathogenic_likely_pathogenic,
                    "gene_mim": gs.gene_mim or "",
                    "uncertain": gs.uncertain_significance,
                    "with_conflicts": gs.with_conflicts,
                })

        # Build VCF data sub-dict
        vcf_data: Optional[Dict[str, Any]] = None
        if allele_freqs or mol_consequences or oncogenicity_list or somatic_impact_list:
            vcf_data = {}
            if allele_freqs:
                vcf_data["allele_frequencies"] = allele_freqs
            if mol_consequences:
                vcf_data["molecular_consequences"] = mol_consequences[:10]
            if oncogenicity_list:
                vcf_data["oncogenicity"] = oncogenicity_list
            if somatic_impact_list:
                vcf_data["somatic_clinical_impact"] = somatic_impact_list
            if conflicting_list:
                vcf_data["conflicting_classifications"] = conflicting_list[:5]

        review_statuses = list({r.review_status for r in rows if r.review_status})

        output: Dict[str, Any] = {
            "found": True,
            "source": "clinvar_local",
            "count": len(rows),
            "ids": list(variation_ids)[:20],
            "allele_ids": list(allele_ids)[:20],
            "clinical_significances": clinical_sigs,
            "conditions": conditions,
            "genes": genes,
            "review_statuses": review_statuses,
            "has_conflicting_interpretations": bool(conflicting_list),
            "total_submissions": 0,
            "pubmed_ids": [],
            "cross_references": [],
            "gene_conditions": gene_conditions,
            "gene_stats": gene_stats_list,
            "disease_details": [],
            "entries": result_entries[:10],
        }

        if vcf_data:
            output["vcf_data"] = vcf_data

        return output


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_clinvar_local_instance: Optional[ClinVarLocalService] = None


def get_clinvar_local_service() -> ClinVarLocalService:
    """Return the singleton ClinVarLocalService instance."""
    global _clinvar_local_instance
    if _clinvar_local_instance is None:
        _clinvar_local_instance = ClinVarLocalService()
    return _clinvar_local_instance
