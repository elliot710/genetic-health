"""Load European sub-population allele frequencies from the gnomAD GraphQL API.

Populates the ``subpop_freqs`` JSON column on ``ancestry_aims_panel`` with
per-sub-population allele frequencies.  These are used by the Phase 2 ancestry
model for European sub-population estimation.

gnomAD v2.1 exomes provide the richest European sub-population breakdown:
  nfe_bgr (Balkan), nfe_est (East European), nfe_nwe (Northwestern European),
  nfe_onf (Other Non-Finnish), nfe_seu (Southern European),
  nfe_swe (Swedish/Nordic), fin (Finnish), asj (Ashkenazi Jewish).

Genome data (from v2.1 or v4) is used as fallback when exome is unavailable.

Usage::

    # Inside the backend container on production:
    cd /app && python -m backend.scripts.load_ancestry_subpop_data

    # With options:
    python -m backend.scripts.load_ancestry_subpop_data --top-n 60000 --concurrency 10
"""
import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GNOMAD_API = "https://gnomad.broadinstitute.org/api"

# NFE sub-population IDs we want (from gnomAD v2.1)
NFE_SUBPOP_IDS = {"nfe_bgr", "nfe_est", "nfe_nwe", "nfe_onf", "nfe_seu", "nfe_swe", "fin", "asj"}

# GraphQL query: resolve rsid → variant_id, then fetch exome + genome pops
VARIANT_QUERY = """
query ($rsid: String!) {
  variant_search(query: $rsid, dataset: gnomad_r2_1) {
    variant_id
  }
}
"""

POP_QUERY = """
query ($variantId: String!) {
  variant(variantId: $variantId, dataset: gnomad_r2_1) {
    rsid
    exome {
      populations {
        id
        ac
        an
      }
    }
    genome {
      populations {
        id
        ac
        an
      }
    }
  }
}
"""

_executor = ThreadPoolExecutor(max_workers=20)


def _sync_graphql(query: str, variables: Dict[str, str]) -> Dict[str, Any]:
    """Synchronous GraphQL call to gnomAD API."""
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GNOMAD_API,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _graphql(query: str, variables: Dict[str, str]) -> Dict[str, Any]:
    """Async wrapper around sync GraphQL call."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _sync_graphql, query, variables)


def _extract_nfe_freqs(populations: List[Dict]) -> Dict[str, float]:
    """Extract NFE sub-population allele frequencies from gnomAD populations list.

    We compute af = ac / an for each NFE sub-population.
    """
    result = {}
    for p in populations:
        pop_id = p["id"]
        if pop_id in NFE_SUBPOP_IDS:
            an = p.get("an", 0)
            ac = p.get("ac", 0)
            if an > 0:
                result[pop_id] = round(ac / an, 6)
    return result


async def _fetch_variant_subpops(rsid: str, semaphore: asyncio.Semaphore) -> Tuple[str, Optional[Dict[str, float]]]:
    """Resolve an rsid via gnomAD and extract NFE sub-population frequencies.

    Strategy:
    1. variant_search to get variant_id(s) for this rsid
    2. For each variant_id, query exome + genome populations
    3. Prefer exome (has nfe_bgr), fall back to genome
    4. Pick the variant_id that gives the most sub-population data
    """
    async with semaphore:
        try:
            # Step 1: Resolve rsid → variant_id(s)
            search_result = await _graphql(VARIANT_QUERY, {"rsid": rsid})
            variants = search_result.get("data", {}).get("variant_search", [])
            if not variants:
                return rsid, None

            best_freqs: Optional[Dict[str, float]] = None
            best_count = 0

            # Step 2: Query each variant_id (usually 1-3 per rsid)
            for v in variants[:3]:  # Limit to first 3 to avoid excessive queries
                vid = v.get("variant_id")
                if not vid:
                    continue

                pop_result = await _graphql(POP_QUERY, {"variantId": vid})
                vdata = pop_result.get("data", {}).get("variant")
                if not vdata:
                    continue

                # Try exome first (has nfe_bgr)
                for src in ["exome", "genome"]:
                    src_data = vdata.get(src)
                    if not src_data or not src_data.get("populations"):
                        continue
                    freqs = _extract_nfe_freqs(src_data["populations"])
                    if len(freqs) > best_count:
                        best_count = len(freqs)
                        best_freqs = freqs
                    if best_count >= 6:  # Got all main NFE sub-pops
                        break
                if best_count >= 6:
                    break

            if best_freqs and len(best_freqs) >= 3:
                return rsid, best_freqs
            return rsid, None

        except Exception as e:
            logger.debug(f"Error fetching {rsid}: {e}")
            return rsid, None


async def load_subpop_data(
    top_n: int = 60_000,
    concurrency: int = 10,
) -> Dict[str, Any]:
    """Fetch NFE sub-population AFs from gnomAD v2.1 and store in DB.

    Args:
        top_n: Number of top-FST markers to process.
        concurrency: Number of concurrent gnomAD API requests.

    Returns:
        Stats dict with counts.
    """
    from backend.db.database import async_session_factory

    stats = {
        "total_markers": 0,
        "fetched": 0,
        "skipped": 0,
        "errors": 0,
        "already_loaded": 0,
    }

    # Load top-N markers by FST, excluding those already with gnomAD data
    async with async_session_factory() as session:
        result = await session.execute(text(
            "SELECT rsid FROM ancestry_aims_panel "
            "WHERE fst_delta >= 0.70 "
            "AND (subpop_freqs IS NULL "
            "     OR NOT (subpop_freqs::text LIKE :gnomad_check)) "
            "ORDER BY fst_delta DESC LIMIT :n"
        ), {"n": top_n, "gnomad_check": "%nfe_%"})
        rsids = [r[0] for r in result.fetchall()]

        # Count already loaded
        cnt = await session.execute(text(
            "SELECT COUNT(*) FROM ancestry_aims_panel "
            "WHERE subpop_freqs IS NOT NULL "
            "AND subpop_freqs::text LIKE :gnomad_check"
        ), {"gnomad_check": "%nfe_%"})
        stats["already_loaded"] = cnt.scalar() or 0

    stats["total_markers"] = len(rsids)
    if not rsids:
        logger.info(f"No new markers to load (already have {stats['already_loaded']} with gnomAD data)")
        return stats

    logger.info(
        f"Loading gnomAD NFE sub-pop frequencies for {len(rsids)} markers "
        f"(concurrency={concurrency}, already loaded={stats['already_loaded']})..."
    )

    semaphore = asyncio.Semaphore(concurrency)
    updates: Dict[str, Dict[str, float]] = {}
    t0 = time.monotonic()

    # Process in chunks to show progress and do incremental DB writes
    CHUNK = 500
    for ci in range(0, len(rsids), CHUNK):
        chunk = rsids[ci:ci + CHUNK]
        chunk_num = (ci // CHUNK) + 1
        total_chunks = (len(rsids) + CHUNK - 1) // CHUNK

        # Concurrent fetch for this chunk
        tasks = [_fetch_variant_subpops(rsid, semaphore) for rsid in chunk]
        results = await asyncio.gather(*tasks)

        chunk_updates = {}
        for rsid, freqs in results:
            if freqs:
                chunk_updates[rsid] = freqs
                stats["fetched"] += 1
            else:
                stats["skipped"] += 1

        # Write chunk results to DB immediately
        if chunk_updates:
            async with async_session_factory() as session:
                for rsid, freqs in chunk_updates.items():
                    await session.execute(
                        text(
                            "UPDATE ancestry_aims_panel "
                            "SET subpop_freqs = :freqs "
                            "WHERE rsid = :rsid"
                        ),
                        {"rsid": rsid, "freqs": json.dumps(freqs)},
                    )
                await session.commit()
            updates.update(chunk_updates)

        elapsed = time.monotonic() - t0
        rate = (ci + len(chunk)) / elapsed if elapsed > 0 else 0
        eta = (len(rsids) - ci - len(chunk)) / rate if rate > 0 else 0
        logger.info(
            f"  Chunk {chunk_num}/{total_chunks} | "
            f"{stats['fetched']} fetched, {stats['skipped']} skipped | "
            f"{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining"
        )

    elapsed = time.monotonic() - t0
    logger.info(
        f"Done in {elapsed:.0f}s: {stats['fetched']} fetched, "
        f"{stats['skipped']} skipped, {stats['already_loaded']} previously loaded"
    )
    return stats


async def load_and_invalidate(top_n: int = 60_000, concurrency: int = 10):
    """Load data and invalidate the ancestry generator's AIMs cache."""
    stats = await load_subpop_data(top_n=top_n, concurrency=concurrency)
    try:
        from backend.services.insight_generators.ancestry import invalidate_aims_cache
        invalidate_aims_cache()
        logger.info("AIMs cache invalidated — next ancestry run will use new data")
    except ImportError:
        pass
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Load European NFE sub-population allele frequencies from gnomAD v2.1"
    )
    parser.add_argument(
        "--top-n", type=int, default=60_000,
        help="Number of top-FST markers to process (default: 60000)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=10,
        help="Number of concurrent API requests (default: 10)",
    )
    args = parser.parse_args()

    stats = asyncio.run(load_and_invalidate(
        top_n=args.top_n,
        concurrency=args.concurrency,
    ))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
