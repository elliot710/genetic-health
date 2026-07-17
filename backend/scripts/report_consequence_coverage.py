"""Report molecular-consequence coverage over the marker set (U7).

Read-only. For every genetic_markers rsid, ask the unified resolver for a
consequence and report how many resolve — the before/after signal for the
offline-source integration. Run on the worker box (needs the DB + the caches).

Usage:
  uv run python -m backend.scripts.report_consequence_coverage
  uv run python -m backend.scripts.report_consequence_coverage --limit 50000
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select, func

from backend.db.database import async_session_factory
from backend.db.models import GeneticMarker
from backend.services.annotation_sources.consequence_resolver import get_consequence_resolver


async def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    resolver = get_consequence_resolver()
    async with async_session_factory() as session:
        total = (await session.execute(select(func.count(GeneticMarker.id)))).scalar() or 0
        q = select(GeneticMarker.rsid)
        if limit:
            q = q.limit(limit)
        rsids = [r[0] for r in (await session.execute(q)).all()]

    resolved = sum(1 for rsid in rsids if resolver.resolve(rsid))
    scanned = len(rsids)
    pct = (100.0 * resolved / scanned) if scanned else 0.0
    print("Consequence coverage report")
    print(f"  total markers:      {total}")
    print(f"  scanned:            {scanned}")
    print(f"  resolved consequence: {resolved} ({pct:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
