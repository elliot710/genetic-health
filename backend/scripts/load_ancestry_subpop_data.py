"""Load European sub-population allele frequencies from the Ensembl REST API.

Populates the ``subpop_freqs`` JSON column on ``ancestry_aims_panel`` with
per-sub-population allele frequencies from the Ensembl Variation API. These
are used by the Phase 2 ancestry model for European sub-population estimation.

Sources fetched (in priority order):
  - gnomAD NFE sub-populations: nfe_bgr, nfe_est, nfe_nwe, nfe_seu, nfe_swe,
    fin, asj  (preferred — gives ~7 European sub-populations)
  - 1000G Phase 3 sub-populations: CEU, FIN, GBR, IBS, TSI
    (fallback — gives 5 European sub-populations)

Usage::

    # Inside the backend container on production:
    cd /app && python -m backend.scripts.load_ancestry_subpop_data

    # With options:
    python -m backend.scripts.load_ancestry_subpop_data --top-n 10000 --batch-size 200

This is a one-time data loading operation (~5-15 minutes depending on marker
count and API rate limits).
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Set

import httpx
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ENSEMBL_BASE = "https://rest.ensembl.org"
ENSEMBL_POST_URL = f"{ENSEMBL_BASE}/variation/homo_sapiens"

# gnomAD population codes we care about (European sub-populations)
GNOMAD_POPS = {
    "gnomADg:nfe_bgr",  # Bulgarian → Balkan
    "gnomADg:nfe_est",  # Estonian  → East European
    "gnomADg:nfe_nwe",  # Northwest European → Germanic
    "gnomADg:nfe_seu",  # Southern European → Greek/Mediterranean
    "gnomADg:nfe_swe",  # Swedish → Nordic
    "gnomADg:fin",      # Finnish
    "gnomADg:asj",      # Ashkenazi Jewish
    "gnomADe:nfe_bgr",
    "gnomADe:nfe_est",
    "gnomADe:nfe_nwe",
    "gnomADe:nfe_seu",
    "gnomADe:nfe_swe",
    "gnomADe:fin",
    "gnomADe:asj",
}

# 1000G Phase 3 EUR sub-population codes
TKG_EUR_POPS = {
    "1000GENOMES:phase_3:CEU",
    "1000GENOMES:phase_3:FIN",
    "1000GENOMES:phase_3:GBR",
    "1000GENOMES:phase_3:IBS",
    "1000GENOMES:phase_3:TSI",
}

# Map Ensembl population names to our short codes
POP_CODE_MAP = {
    # gnomAD genome
    "gnomADg:nfe_bgr": "nfe_bgr",
    "gnomADg:nfe_est": "nfe_est",
    "gnomADg:nfe_nwe": "nfe_nwe",
    "gnomADg:nfe_seu": "nfe_seu",
    "gnomADg:nfe_swe": "nfe_swe",
    "gnomADg:fin": "fin",
    "gnomADg:asj": "asj",
    # gnomAD exome (fallback if genome not available)
    "gnomADe:nfe_bgr": "nfe_bgr",
    "gnomADe:nfe_est": "nfe_est",
    "gnomADe:nfe_nwe": "nfe_nwe",
    "gnomADe:nfe_seu": "nfe_seu",
    "gnomADe:nfe_swe": "nfe_swe",
    "gnomADe:fin": "fin",
    "gnomADe:asj": "asj",
    # 1000G
    "1000GENOMES:phase_3:CEU": "ceu",
    "1000GENOMES:phase_3:FIN": "fin",
    "1000GENOMES:phase_3:GBR": "gbr",
    "1000GENOMES:phase_3:IBS": "ibs",
    "1000GENOMES:phase_3:TSI": "tsi",
}


def _extract_subpop_freqs(
    variant_data: Dict[str, Any],
) -> Optional[Dict[str, float]]:
    """Extract sub-population allele frequencies from Ensembl variation response."""
    populations = variant_data.get("populations", [])
    if not populations:
        return None

    # First try gnomAD (higher priority — more European sub-populations)
    gnomad_freqs: Dict[str, float] = {}
    tkg_freqs: Dict[str, float] = {}

    for pop_entry in populations:
        pop_name = pop_entry.get("population", "")
        freq = pop_entry.get("frequency")
        if freq is None:
            continue

        short_code = POP_CODE_MAP.get(pop_name)
        if not short_code:
            continue

        # Prefer gnomAD genome over exome (genome has "gnomADg:" prefix)
        if pop_name.startswith("gnomADg:"):
            gnomad_freqs[short_code] = freq
        elif pop_name.startswith("gnomADe:") and short_code not in gnomad_freqs:
            gnomad_freqs[short_code] = freq
        elif pop_name.startswith("1000GENOMES:"):
            tkg_freqs[short_code] = freq

    # Use gnomAD if we got at least 4 sub-populations, else fall back to 1000G
    if len(gnomad_freqs) >= 4:
        return gnomad_freqs
    if len(tkg_freqs) >= 3:
        return tkg_freqs
    # Merge whatever we have
    merged = {**tkg_freqs, **gnomad_freqs}
    return merged if len(merged) >= 3 else None


async def _fetch_batch(
    client: httpx.AsyncClient,
    rsids: List[str],
    retry: int = 3,
) -> Dict[str, Dict[str, Any]]:
    """POST a batch of rsids to Ensembl and return parsed responses."""
    for attempt in range(retry):
        try:
            resp = await client.post(
                ENSEMBL_POST_URL,
                json={"ids": rsids},
                params={"pops": "1"},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=60.0,
            )
            if resp.status_code == 429:
                # Rate limited — wait and retry
                wait = float(resp.headers.get("Retry-After", "2"))
                logger.warning(f"Rate limited, waiting {wait}s")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.warning(f"Batch attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2 ** attempt)
    return {}


async def load_subpop_data(
    top_n: int = 10_000,
    batch_size: int = 200,
) -> Dict[str, Any]:
    """Fetch sub-population AFs from Ensembl and store them in the DB.

    Args:
        top_n: Number of top-FST markers to process. More = better accuracy
               but slower. 10K provides excellent results in ~5 minutes.
        batch_size: Ensembl API batch size (max 200).

    Returns:
        Stats dict with counts.
    """
    from backend.db.database import async_session_factory

    stats = {
        "total_markers": 0,
        "fetched": 0,
        "gnomad_hits": 0,
        "tkg_hits": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Load top-N markers by FST from the AIMs panel
    async with async_session_factory() as session:
        result = await session.execute(text(
            "SELECT rsid FROM ancestry_aims_panel "
            "ORDER BY fst_delta DESC LIMIT :n"
        ), {"n": top_n})
        rsids = [r[0] for r in result.fetchall()]

    stats["total_markers"] = len(rsids)
    if not rsids:
        logger.error("No markers in ancestry_aims_panel — populate it first!")
        return stats

    logger.info(f"Loading sub-pop frequencies for {len(rsids)} markers...")

    # Batch-fetch from Ensembl
    updates: Dict[str, Dict[str, float]] = {}
    t0 = time.monotonic()

    async with httpx.AsyncClient() as client:
        for bi in range(0, len(rsids), batch_size):
            batch = rsids[bi : bi + batch_size]
            batch_num = (bi // batch_size) + 1
            total_batches = (len(rsids) + batch_size - 1) // batch_size

            data = await _fetch_batch(client, batch)

            for rsid in batch:
                variant_data = data.get(rsid, {})
                if not variant_data:
                    stats["skipped"] += 1
                    continue

                freqs = _extract_subpop_freqs(variant_data)
                if freqs:
                    updates[rsid] = freqs
                    stats["fetched"] += 1
                    if any(k.startswith("nfe_") for k in freqs):
                        stats["gnomad_hits"] += 1
                    else:
                        stats["tkg_hits"] += 1
                else:
                    stats["skipped"] += 1

            # Rate limit: ~15 requests/second for Ensembl
            await asyncio.sleep(0.1)

            if batch_num % 10 == 0 or batch_num == total_batches:
                elapsed = time.monotonic() - t0
                logger.info(
                    f"  Batch {batch_num}/{total_batches} | "
                    f"{stats['fetched']} fetched | "
                    f"{elapsed:.0f}s elapsed"
                )

    # Bulk update the database
    if updates:
        logger.info(f"Writing {len(updates)} sub-pop frequency records to DB...")
        async with async_session_factory() as session:
            for rsid, freqs in updates.items():
                await session.execute(
                    text(
                        "UPDATE ancestry_aims_panel "
                        "SET subpop_freqs = :freqs "
                        "WHERE rsid = :rsid"
                    ),
                    {"rsid": rsid, "freqs": json.dumps(freqs)},
                )
            await session.commit()
        logger.info("Database updated successfully")
    else:
        logger.warning("No sub-population data fetched!")

    elapsed = time.monotonic() - t0
    logger.info(
        f"Done in {elapsed:.0f}s: {stats['fetched']} fetched "
        f"({stats['gnomad_hits']} gnomAD, {stats['tkg_hits']} 1KG), "
        f"{stats['skipped']} skipped"
    )
    return stats


# Also invalidate the in-memory cache so the ancestry generator picks up new data
async def load_and_invalidate(top_n: int = 10_000, batch_size: int = 200):
    """Load data and invalidate the ancestry generator's AIMs cache."""
    stats = await load_subpop_data(top_n=top_n, batch_size=batch_size)
    try:
        from backend.services.insight_generators.ancestry import invalidate_aims_cache
        invalidate_aims_cache()
        logger.info("AIMs cache invalidated — next ancestry run will use new data")
    except ImportError:
        pass
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Load European sub-population allele frequencies from Ensembl API"
    )
    parser.add_argument(
        "--top-n", type=int, default=10_000,
        help="Number of top-FST markers to process (default: 10000)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=200,
        help="Ensembl API batch size (default: 200, max: 200)",
    )
    args = parser.parse_args()

    stats = asyncio.run(load_and_invalidate(
        top_n=args.top_n,
        batch_size=args.batch_size,
    ))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
