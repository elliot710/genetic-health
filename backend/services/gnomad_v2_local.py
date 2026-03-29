"""
gnomAD v2.1.1 local service — per-population allele frequency lookup.

Reads from bgzip-compressed VCF files (GRCh37) using pysam tabix.
Used exclusively for ancestry analysis (super-population + NFE sub-population AFs).
NOT used for variant annotation — use gnomad_local.py for CADD scores.

Data location: /app/data_sources/gnomad_v2/
Files:         gnomad.exomes.r2.1.1.sites.{chrom}.vcf.bgz + .tbi indexes

Population fields extracted per variant:
  Super-populations: AF_afr, AF_amr, AF_eas, AF_nfe, AF_sas (+ AC/AN)
  NFE sub-populations: AF_nfe_bgr, AF_nfe_est, AF_nfe_nwe, AF_nfe_seu, AF_nfe_swe,
                       AF_nfe_onf, AF_fin, AF_asj

Usage:
    svc = get_gnomad_v2_service()
    await svc.ensure_loaded()
    afs = await svc.get_population_afs("rs1234")
    batch = await svc.batch_get_population_afs(["rs1234", "rs5678"])
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_GNOMAD_V2_DIR = Path(os.environ.get(
    "GNOMAD_V2_DATA_DIR",
    "/app/data_sources/gnomad_v2",
))

# Super-populations and NFE sub-populations we extract
_SUPER_POPS = ["afr", "amr", "eas", "nfe", "sas"]
_NFE_SUBPOPS = ["nfe_bgr", "nfe_est", "nfe_nwe", "nfe_seu", "nfe_swe", "nfe_onf"]
_OTHER_SUBPOPS = ["fin", "asj"]  # technically not NFE but used in ancestry sub-pop model

_ALL_POPS = _SUPER_POPS + _NFE_SUBPOPS + _OTHER_SUBPOPS


class GnomadV2Service:
    """Per-population AF lookup from local gnomAD v2.1.1 bgz VCF files.

    VCF files are GRCh37 — no liftover needed for user variant data.
    rsID is stored in the VCF ID column.

    Lookup strategy:
    1. PG batch lookup (fast) — use gnomad_v2_variants table if populated
    2. Tabix position lookup (fallback) — per-variant tabix queries on VCF files
    3. Sequential VCF scan (bulk) — for ancestry panel refresh
    """

    def __init__(self):
        self._vcf_files: Dict[str, Path] = {}   # chrom → path (e.g. "1" → Path)
        self._loaded = False
        self._lock = asyncio.Lock()
        self._pg_count: int = 0  # rows in gnomad_v2_variants table

    @property
    def is_loaded(self) -> bool:
        return self._loaded and bool(self._vcf_files)

    @property
    def has_pg_data(self) -> bool:
        return self._pg_count > 0

    @property
    def file_count(self) -> int:
        return len(self._vcf_files)

    @property
    def indexed_count(self) -> int:
        return sum(1 for p in self._vcf_files.values() if Path(str(p) + ".tbi").exists())

    async def ensure_loaded(self) -> bool:
        if self._loaded:
            return self.is_loaded
        async with self._lock:
            if self._loaded:
                return self.is_loaded
            try:
                await asyncio.to_thread(self._discover_files)
            except Exception as e:
                logger.error("gnomAD v2: failed to discover VCF files: %s", e)
            # Check PG row count
            try:
                await self._check_pg_count()
            except Exception as e:
                logger.debug("gnomAD v2: PG count check failed: %s", e)
            self._loaded = True
        if self._vcf_files:
            indexed = self.indexed_count
            logger.info(
                "gnomAD v2: %d chromosome VCF files found, %d tabix-indexed, PG: %d rows",
                len(self._vcf_files), indexed, self._pg_count,
            )
            if indexed == 0 and self._pg_count == 0:
                logger.warning(
                    "gnomAD v2: no .tbi index files and no PG data — run ETL or index_all_files()"
                )
        else:
            logger.warning("gnomAD v2: no VCF files found in %s", _GNOMAD_V2_DIR)
        return self.is_loaded

    async def _check_pg_count(self):
        """Check how many rows are in gnomad_v2_variants table."""
        from ..db.database import async_session_factory
        from sqlalchemy import text as sa_text
        try:
            async with async_session_factory() as session:
                result = await session.execute(sa_text("SELECT COUNT(*) FROM gnomad_v2_variants"))
                self._pg_count = result.scalar() or 0
        except Exception:
            self._pg_count = 0

    def _discover_files(self):
        """Find per-chromosome bgz VCF files and build chrom → path mapping."""
        if not _GNOMAD_V2_DIR.exists():
            return
        pattern = re.compile(r"gnomad\.exomes\.r2\.1\.1\.sites\.(?:chr)?(\w+)\.vcf\.bgz$")
        seen: Dict[str, Path] = {}
        for p in sorted(_GNOMAD_V2_DIR.iterdir()):
            m = pattern.match(p.name)
            if m:
                chrom = m.group(1).replace("chr", "")
                # Prefer files without "chr" prefix in name; skip duplicate chr22
                if chrom not in seen:
                    seen[chrom] = p
        self._vcf_files = seen

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    async def index_all_files(self, *, force: bool = False) -> Dict[str, Any]:
        """Create tabix .tbi indexes for all bgz VCF files that lack one.

        Requires pysam. Run once after files are placed in gnomad_v2 dir.
        """
        import pysam
        if not self._loaded:
            await self.ensure_loaded()
        if not self._vcf_files:
            return {"indexed": 0, "skipped": 0, "errors": []}

        indexed = 0
        skipped = 0
        errors = []
        for chrom, vcf_path in sorted(self._vcf_files.items()):
            tbi_path = Path(str(vcf_path) + ".tbi")
            if tbi_path.exists() and not force:
                skipped += 1
                continue
            try:
                logger.info("gnomAD v2: indexing chr%s (%s)…", chrom, vcf_path.name)
                await asyncio.to_thread(pysam.tabix_index, str(vcf_path), preset="vcf", force=True)
                indexed += 1
                logger.info("gnomAD v2: chr%s indexed", chrom)
            except Exception as e:
                msg = f"chr{chrom}: {e}"
                errors.append(msg)
                logger.error("gnomAD v2: indexing failed for %s: %s", vcf_path.name, e)

        return {"indexed": indexed, "skipped": skipped, "errors": errors}

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    async def get_population_afs(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up population AFs for a single rsID."""
        results = await self.batch_get_population_afs([rsid])
        return results.get(rsid)

    async def batch_get_population_afs(
        self, rsids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Batch rsID → population AF lookup using per-chromosome tabix scans.

        Returns {rsid: {af_afr, af_amr, af_eas, af_nfe, af_sas, subpop_freqs, ...}}
        Only variants found in the VCF are included in the result.
        """
        if not rsids:
            return {}
        if not self._loaded:
            await self.ensure_loaded()
        if not self._vcf_files:
            return {}

        rsid_set = set(rsids)
        return await asyncio.to_thread(self._scan_vcfs_for_rsids, rsid_set)

    async def batch_lookup_by_position(
        self,
        tuples: List[tuple],
    ) -> Dict[str, Dict[str, Any]]:
        """Fast position-based tabix lookup for gnomAD v2 population AFs.

        Takes list of (rsid, chrom, pos, ref, alt) tuples with GRCh37 coords.
        Uses tabix index for O(log N) per-query access instead of full VCF scan.

        Returns {rsid: {af_afr, af_amr, af_eas, af_nfe, af_sas, subpop_freqs, ...}}
        """
        if not tuples:
            return {}
        if not self._loaded:
            await self.ensure_loaded()
        if not self._vcf_files:
            return {}

        return await asyncio.to_thread(self._tabix_batch_by_position, tuples)

    async def batch_lookup_pg(self, rsids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fast PG batch lookup — queries gnomad_v2_variants by rsid.

        Returns {rsid: {af_afr, af_amr, af_eas, af_nfe, af_sas, subpop_freqs, ...}}
        in the same format as tabix/VCF lookups.
        """
        if not rsids or self._pg_count == 0:
            return {}

        from ..db.database import async_session_factory
        from sqlalchemy import text as sa_text

        results: Dict[str, Dict[str, Any]] = {}
        BATCH = 10_000

        async with async_session_factory() as session:
            for i in range(0, len(rsids), BATCH):
                batch = [r for r in rsids[i:i + BATCH] if r and r.startswith("rs")]
                if not batch:
                    continue
                # Use parameterized ANY() query for safety
                rows = await session.execute(
                    sa_text(
                        "SELECT rsid, af, af_afr, af_amr, af_eas, af_nfe, af_sas, af_fin, af_asj "
                        "FROM gnomad_v2_variants WHERE rsid = ANY(:rsids)"
                    ),
                    {"rsids": batch},
                )
                for row in rows:
                    afs: Dict[str, Any] = {}
                    for pop in ("afr", "amr", "eas", "nfe", "sas"):
                        val = getattr(row, f"af_{pop}", None)
                        if val is not None:
                            afs[f"af_{pop}"] = val
                    if not afs:
                        continue
                    # Build subpop_freqs
                    subpop: Dict[str, Any] = {}
                    for sp in ("fin", "asj"):
                        val = getattr(row, f"af_{sp}", None)
                        if val is not None:
                            subpop[sp] = val
                    if subpop:
                        subpop["subpop_system"] = "gnomad"
                        afs["subpop_freqs"] = subpop
                    results[row.rsid] = afs

        return results

    async def bulk_refresh_ancestry_panel(
        self,
        *,
        fst_threshold: float = 0.70,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Refresh ancestry_aims_panel with gnomAD v2 population AFs.

        Replaces/supplements the data loaded from the gnomAD GraphQL API.
        Reads all rsids from ancestry_aims_panel, looks them up in gnomAD v2
        VCF files, and updates:
          - af_afr, af_amr, af_eas, af_eur (= AF_nfe), af_sas
          - subpop_freqs JSON (NFE sub-pops + fin + asj)

        Returns summary stats.
        """
        from ..db.database import async_session_factory
        from sqlalchemy import text

        if not self._loaded:
            await self.ensure_loaded()
        if not self.indexed_count:
            raise RuntimeError("No gnomAD v2 VCF files are tabix-indexed. Run index_all_files() first.")

        t0 = time.time()
        # Load all rsids from the panel
        async with async_session_factory() as session:
            result = await session.execute(text(
                "SELECT rsid FROM ancestry_aims_panel WHERE fst_delta >= :thresh ORDER BY rsid",
            ).bindparams(thresh=fst_threshold))
            panel_rsids = [row[0] for row in result.all()]

        if not panel_rsids:
            return {"updated": 0, "not_found": 0, "total": 0, "elapsed_s": 0}

        logger.info(
            "gnomAD v2 ancestry refresh: %d AIMs to look up (fst_delta >= %.2f)",
            len(panel_rsids), fst_threshold,
        )
        if progress_callback:
            progress_callback("loading", len(panel_rsids), 0)

        # Bulk lookup — one sequential pass per chromosome
        all_afs = await asyncio.to_thread(self._scan_vcfs_for_rsids, set(panel_rsids))

        found_count = len(all_afs)
        logger.info(
            "gnomAD v2 ancestry refresh: %d/%d rsids found in VCFs",
            found_count, len(panel_rsids),
        )
        if progress_callback:
            progress_callback("lookup_done", found_count, time.time() - t0)

        # Batch-update the database
        BATCH = 1000
        updated = 0
        async with async_session_factory() as session:
            rsid_list = list(all_afs.keys())
            for i in range(0, len(rsid_list), BATCH):
                chunk_rsids = rsid_list[i:i + BATCH]
                for rsid in chunk_rsids:
                    afs = all_afs[rsid]
                    await session.execute(text("""
                        UPDATE ancestry_aims_panel
                        SET af_afr = :af_afr,
                            af_amr = :af_amr,
                            af_eas = :af_eas,
                            af_eur = :af_eur,
                            af_sas = :af_sas,
                            subpop_freqs = :subpop_freqs
                        WHERE rsid = :rsid
                    """).bindparams(
                        rsid=rsid,
                        af_afr=afs.get("af_afr"),
                        af_amr=afs.get("af_amr"),
                        af_eas=afs.get("af_eas"),
                        af_eur=afs.get("af_nfe"),   # NFE = European proxy
                        af_sas=afs.get("af_sas"),
                        subpop_freqs=json.dumps(afs.get("subpop_freqs", {})),
                    ))
                    updated += 1
                await session.commit()
                if progress_callback:
                    progress_callback("updating", updated, time.time() - t0)
                await asyncio.sleep(0)

        elapsed = time.time() - t0
        result = {
            "updated": updated,
            "not_found": len(panel_rsids) - found_count,
            "total": len(panel_rsids),
            "elapsed_s": round(elapsed, 1),
        }
        logger.info("gnomAD v2 ancestry refresh complete: %s", result)
        return result

    # ------------------------------------------------------------------
    # Internal VCF scanning
    # ------------------------------------------------------------------

    def _tabix_batch_by_position(
        self, tuples: List[tuple],
    ) -> Dict[str, Dict[str, Any]]:
        """Position-based tabix lookup — O(log N) per query.

        Groups (rsid, chrom, pos, ref, alt) tuples by chromosome, then does
        targeted tabix.fetch(chrom, pos-1, pos) for each position.
        Much faster than full VCF scan for large variant sets.
        """
        import pysam

        # Group by chromosome
        by_chrom: Dict[str, List[tuple]] = {}
        for tup in tuples:
            rsid, chrom, pos, ref, alt = tup
            chrom_clean = str(chrom).replace("chr", "")
            by_chrom.setdefault(chrom_clean, []).append(tup)

        results: Dict[str, Dict[str, Any]] = {}
        total_queries = 0
        total_found = 0

        for chrom_key, chrom_tuples in sorted(by_chrom.items()):
            vcf_path = self._vcf_files.get(chrom_key)
            if not vcf_path:
                continue
            tbi_path = Path(str(vcf_path) + ".tbi")
            if not tbi_path.exists():
                continue

            try:
                tbx = pysam.TabixFile(str(vcf_path))
                found_this_chr = 0
                try:
                    for rsid, chrom, pos, ref, alt in chrom_tuples:
                        total_queries += 1
                        try:
                            # tabix uses 0-based half-open intervals
                            for row in tbx.fetch(chrom_key, int(pos) - 1, int(pos)):
                                fields = row.split("\t", 8)
                                if len(fields) < 8:
                                    continue
                                vcf_pos = fields[1]
                                vcf_ref = fields[3]
                                vcf_id = fields[2]
                                # Match by position + ref allele, or by rsid
                                if str(pos) == vcf_pos and (
                                    ref == vcf_ref or vcf_id == rsid
                                    or (
                                        ";" in vcf_id
                                        and rsid in vcf_id.split(";")
                                    )
                                ):
                                    info_str = fields[7]
                                    afs = _parse_info_afs(info_str)
                                    if afs:
                                        results[rsid] = afs
                                        found_this_chr += 1
                                        break
                        except ValueError:
                            continue  # position out of range for this contig
                finally:
                    tbx.close()
                if found_this_chr:
                    logger.debug(
                        "gnomAD v2 pos: chr%s — %d/%d found",
                        chrom_key, found_this_chr, len(chrom_tuples),
                    )
                total_found += found_this_chr
            except Exception as e:
                logger.warning("gnomAD v2 pos: failed to open chr%s: %s", chrom_key, e)

        logger.info(
            "gnomAD v2 pos: %d/%d found across %d chromosomes",
            total_found, total_queries, len(by_chrom),
        )
        return results

    def _scan_vcfs_for_rsids(
        self, rsid_set: set,
    ) -> Dict[str, Dict[str, Any]]:
        """Sequential per-chromosome VCF scan to find rsids.

        Returns {rsid: af_dict}. This is called in a threadpool executor.
        For large sets (100K+ rsids), scanning chromosomes sequentially once
        is faster than N random tabix seeks.
        """
        import pysam

        results: Dict[str, Dict[str, Any]] = {}
        remaining = set(rsid_set)

        for chrom, vcf_path in sorted(self._vcf_files.items()):
            if not remaining:
                break
            tbi_path = Path(str(vcf_path) + ".tbi")
            if not tbi_path.exists():
                logger.debug("gnomAD v2: chr%s has no tabix index — skipping", chrom)
                continue
            try:
                tbx = pysam.TabixFile(str(vcf_path))
                found_this_chr = 0
                try:
                    for row in tbx.fetch():
                        if not remaining:
                            break
                        fields = row.split("\t", 8)
                        if len(fields) < 8:
                            continue
                        vcf_id = fields[2]
                        if vcf_id not in remaining and not (
                            ";" in vcf_id and any(r in vcf_id.split(";") for r in remaining)
                        ):
                            continue
                        # Parse which rsid(s) match
                        id_parts = vcf_id.split(";") if ";" in vcf_id else [vcf_id]
                        for vid in id_parts:
                            if vid in remaining:
                                info_str = fields[7]
                                afs = _parse_info_afs(info_str)
                                if afs:
                                    results[vid] = afs
                                    remaining.discard(vid)
                                    found_this_chr += 1
                except Exception as e:
                    logger.debug("gnomAD v2: error scanning chr%s: %s", chrom, e)
                finally:
                    tbx.close()
                if found_this_chr:
                    logger.debug("gnomAD v2: chr%s — %d rsids found", chrom, found_this_chr)
            except Exception as e:
                logger.warning("gnomAD v2: failed to open chr%s VCF: %s", chrom, e)

        return results


def _parse_info_afs(info_str: str) -> Optional[Dict[str, Any]]:
    """Parse an INFO field string and extract population AFs.

    Returns None when no useful AF data is found.
    Result format:
    {
        "af_afr": 0.12, "af_amr": 0.05, "af_eas": 0.01, "af_nfe": 0.35, "af_sas": 0.08,
        "ac_afr": 1234, "an_afr": 10000, ...
        "subpop_freqs": {
            "nfe_bgr": 0.12, "nfe_est": 0.08, ..., "fin": 0.05, "asj": 0.07,
            "subpop_system": "gnomad"
        }
    }
    """
    # Build a key→value map from INFO field
    info: Dict[str, str] = {}
    for field in info_str.split(";"):
        if "=" in field:
            k, _, v = field.partition("=")
            info[k] = v

    def _af(key: str) -> Optional[float]:
        v = info.get(key)
        if v is None or v in (".", "NA"):
            return None
        # AF fields are comma-separated lists for multi-allelic sites; take first
        try:
            return float(v.split(",")[0])
        except (ValueError, TypeError):
            return None

    def _ac(key: str) -> Optional[int]:
        v = info.get(key)
        if v is None or v in (".", "NA"):
            return None
        try:
            return int(v.split(",")[0])
        except (ValueError, TypeError):
            return None

    result: Dict[str, Any] = {}

    # Super-populations
    for pop in _SUPER_POPS:
        af = _af(f"AF_{pop}")
        if af is not None:
            result[f"af_{pop}"] = af
        ac = _ac(f"AC_{pop}")
        an = _ac(f"AN_{pop}")
        if ac is not None:
            result[f"ac_{pop}"] = ac
        if an is not None:
            result[f"an_{pop}"] = an

    if not result:
        return None  # no population data found

    # NFE sub-populations + fin + asj → subpop_freqs JSON
    subpop: Dict[str, Any] = {}
    for subp in _NFE_SUBPOPS + _OTHER_SUBPOPS:
        # gnomAD v2 fields are e.g. AF_nfe_bgr, AF_fin, AF_asj
        field_key = f"AF_{subp}"
        af = _af(field_key)
        if af is not None:
            subpop[subp] = af
    if subpop:
        subpop["subpop_system"] = "gnomad"
        result["subpop_freqs"] = subpop

    return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service_instance: Optional[GnomadV2Service] = None


def get_gnomad_v2_service() -> GnomadV2Service:
    global _service_instance
    if _service_instance is None:
        _service_instance = GnomadV2Service()
    return _service_instance
