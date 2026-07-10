from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from ..db.database import async_session_factory
from ..db.models import ClinGenGeneValidity

logger = logging.getLogger(__name__)

_DEFINITIVE_CLASSIFICATIONS = {"Definitive", "Strong", "Moderate"}
_DISPUTED_CLASSIFICATIONS = {"Disputed", "Refuted", "No Known Disease Relationship"}


class ClinGenService:
    """Gene symbol → disease validity classification lookup against clingen_gene_validity."""

    def __init__(self) -> None:
        self._row_count: int = 0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._gene_cache: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def ensure_loaded(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            async with async_session_factory() as session:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM clingen_gene_validity")
                )
                self._row_count = result.scalar() or 0
            self._loaded = self._row_count > 0

    async def lookup_by_gene(self, gene_symbol: str) -> Optional[Dict[str, Any]]:
        if not gene_symbol:
            return None
        results = await self.lookup_genes_batch([gene_symbol])
        return results.get(gene_symbol)

    async def lookup_genes_batch(self, gene_symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not gene_symbols:
            return {}
        uncached = [g for g in gene_symbols if g not in self._gene_cache]
        if uncached:
            await self._load_genes(uncached)

        output: Dict[str, Optional[Dict[str, Any]]] = {}
        for gene in gene_symbols:
            curations = self._gene_cache.get(gene)
            if curations:
                output[gene] = _build_gene_result(gene, curations)
            else:
                output[gene] = {"found": False, "source": "clingen", "gene_symbol": gene}
        return output

    async def _load_genes(self, gene_symbols: List[str]) -> None:
        async with async_session_factory() as session:
            rows = (await session.execute(
                select(ClinGenGeneValidity)
                .where(ClinGenGeneValidity.gene_symbol.in_(gene_symbols))
                .order_by(ClinGenGeneValidity.gene_symbol)
            )).scalars().all()

        for row in rows:
            self._gene_cache.setdefault(row.gene_symbol, []).append(_row_to_dict(row))

        for gene in gene_symbols:
            if gene not in self._gene_cache:
                self._gene_cache[gene] = []


def _build_gene_result(gene_symbol: str, curations: List[Dict]) -> Dict[str, Any]:
    strongest = _strongest_classification(curations)
    return {
        "found": True,
        "source": "clingen",
        "gene_symbol": gene_symbol,
        "curations": curations,
        "strongest_classification": strongest,
        "is_definitive": strongest in _DEFINITIVE_CLASSIFICATIONS,
        "is_disputed": strongest in _DISPUTED_CLASSIFICATIONS,
        "disease_count": len(curations),
    }


def _strongest_classification(curations: List[Dict]) -> Optional[str]:
    order = ["Definitive", "Strong", "Moderate", "Limited", "Animal Model Only",
             "Disputed", "Refuted", "No Known Disease Relationship"]
    for level in order:
        if any(c.get("classification") == level for c in curations):
            return level
    return curations[0].get("classification") if curations else None


def _row_to_dict(row: ClinGenGeneValidity) -> Dict[str, Any]:
    return {
        "disease_label": row.disease_label,
        "disease_mondo_id": row.disease_mondo_id,
        "moi": row.moi,
        "classification": row.classification,
        "classification_date": row.classification_date,
        "gcep": row.gcep,
        "report_url": row.report_url,
    }


_instance: Optional[ClinGenService] = None


def get_clingen_service() -> ClinGenService:
    global _instance
    if _instance is None:
        _instance = ClinGenService()
    return _instance
