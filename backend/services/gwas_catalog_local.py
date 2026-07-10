from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from ..db.database import async_session_factory
from ..db.models import GwasCatalogAssociation

logger = logging.getLogger(__name__)

_SIGNIFICANCE_THRESHOLD = 5e-8
_BATCH_SIZE = 500


class GwasCatalogService:
    """Batch rsID→trait lookup against the local gwas_catalog_associations table."""

    def __init__(self) -> None:
        self._row_count: int = 0
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def ensure_loaded(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            async with async_session_factory() as session:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM gwas_catalog_associations")
                )
                self._row_count = result.scalar() or 0
            self._loaded = self._row_count > 0

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not rsids:
            return {}
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for i in range(0, len(rsids), _BATCH_SIZE):
            chunk = rsids[i:i + _BATCH_SIZE]
            chunk_results = await self._query_chunk(chunk)
            results.update(chunk_results)
        return results

    async def _query_chunk(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        async with async_session_factory() as session:
            rows = (await session.execute(
                select(GwasCatalogAssociation)
                .where(GwasCatalogAssociation.rsid.in_(rsids))
                .order_by(GwasCatalogAssociation.p_value_mlog.desc().nullslast())
            )).scalars().all()

        rsid_to_associations: Dict[str, List[Dict]] = {}
        for row in rows:
            entry = _row_to_dict(row)
            rsid_to_associations.setdefault(row.rsid, []).append(entry)

        output: Dict[str, Optional[Dict[str, Any]]] = {}
        for rsid in rsids:
            associations = rsid_to_associations.get(rsid)
            if associations:
                output[rsid] = {
                    "found": True,
                    "source": "gwas_catalog",
                    "associations": associations,
                    "top_trait": associations[0].get("trait"),
                    "top_p_value": associations[0].get("p_value"),
                    "genome_wide_significant": any(
                        (a.get("p_value") or 1.0) <= _SIGNIFICANCE_THRESHOLD
                        for a in associations
                    ),
                }
            else:
                output[rsid] = {"found": False, "source": "gwas_catalog"}
        return output


def _row_to_dict(row: GwasCatalogAssociation) -> Dict[str, Any]:
    return {
        "rsid": row.rsid,
        "pubmed_id": row.pubmed_id,
        "study_accession": row.study_accession,
        "trait": row.trait,
        "mapped_trait": row.mapped_trait,
        "mapped_trait_uri": row.mapped_trait_uri,
        "reported_genes": row.reported_genes,
        "mapped_genes": row.mapped_genes,
        "p_value": row.p_value,
        "p_value_mlog": row.p_value_mlog,
        "or_beta": row.or_beta,
        "ci_text": row.ci_text,
        "risk_allele_frequency": row.risk_allele_frequency,
        "strongest_snp_risk_allele": row.strongest_snp_risk_allele,
        "chromosome": row.chromosome,
        "chromosome_position": row.chromosome_position,
        "context": row.context,
    }


_instance: Optional[GwasCatalogService] = None


def get_gwas_catalog_service() -> GwasCatalogService:
    global _instance
    if _instance is None:
        _instance = GwasCatalogService()
    return _instance
