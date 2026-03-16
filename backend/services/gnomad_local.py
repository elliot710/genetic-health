"""
Unified gnomAD lookup service — SQLite cache → PG → BigQuery fallback.

Primary lookup path: SQLite cache (built from tabix-indexed CADD TSV files).
Falls back to PostgreSQL gnomad_variants table, then BigQuery on-demand.
Gene constraint lookups always use PG (small table, rarely changes).

Usage:
    svc = get_gnomad_service()
    result = await svc.lookup("rs1234")
    result = await svc.lookup_by_position("1", 12345, "A", "G")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.models import GnomadVariant, GnomadGeneConstraint
from .gnomad_cache import get_gnomad_cache_service

logger = logging.getLogger(__name__)

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
        """Look up a variant by rsID. Tries cache → PG → BigQuery."""
        # Try SQLite cache first (fastest)
        if self._cache.is_loaded:
            cached = await self._cache.lookup(rsid)
            if cached and cached.get('found'):
                return cached

        # Try local PG
        async with async_session_factory() as session:
            result = await self._lookup_by_rsid(session, rsid)
            if result and result.get('found'):
                return result

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
        """Look up by genomic coordinates. Tries local PG first, then BigQuery."""
        chrom = chrom.replace("chr", "")

        async with async_session_factory() as session:
            result = await self._lookup_by_pos(session, chrom, pos, ref, alt)
            if result and result.get('found'):
                return result

        # Fall back to BigQuery
        bq_result = await self._try_bigquery_pos(chrom, pos, ref, alt)
        if bq_result:
            return bq_result

        return {"found": False, "source": "gnomad", "chrom": chrom, "pos": pos}

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by rsIDs. Tries cache → PG (for remaining). Returns {rsid: result_or_none}."""
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
        return results

    async def lookup_batch_by_position(
        self, variants: List[tuple]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup by genomic coordinates using the (chrom,pos,ref,alt) unique index.

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
                "interpretation": self._interpret_cadd(row.cadd_phred),
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
    def _interpret_cadd(phred: Optional[float]) -> Optional[str]:
        """Interpret CADD PHRED score."""
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
