"""Gene-level constraint scores from gnomAD (pLI, LOEUF, missense Z)."""
import logging
from typing import Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_cache: Dict[str, Optional[dict]] = {}


async def get_gene_constraint(gene: str, session: AsyncSession) -> Optional[dict]:
    if gene in _cache:
        return _cache[gene]
    try:
        result = await session.execute(
            text(
                "SELECT pli, loeuf, mis_z, syn_z "
                "FROM gnomad_gene_constraints WHERE gene = :g LIMIT 1"
            ),
            {"g": gene},
        )
        row = result.first()
        if row:
            data = {
                "pli": row[0],
                "loeuf": row[1],
                "mis_z": row[2],
                "syn_z": row[3],
            }
            _cache[gene] = data
            return data
    except Exception:
        pass
    _cache[gene] = None
    return None


async def get_clinvar_gene_stats(gene: str, session: AsyncSession) -> Optional[dict]:
    if f"cgs_{gene}" in _cache:
        return _cache[f"cgs_{gene}"]
    try:
        result = await session.execute(
            text(
                "SELECT total_submissions, pathogenic_likely_pathogenic, "
                "uncertain_significance, with_conflicts "
                "FROM clinvar_gene_stats WHERE gene = :g LIMIT 1"
            ),
            {"g": gene},
        )
        row = result.first()
        if row:
            data = {
                "total_submissions": row[0],
                "pathogenic_count": row[1],
                "uncertain_count": row[2],
                "conflict_count": row[3],
            }
            _cache[f"cgs_{gene}"] = data
            return data
    except Exception:
        pass
    _cache[f"cgs_{gene}"] = None
    return None


def clear_cache():
    _cache.clear()
