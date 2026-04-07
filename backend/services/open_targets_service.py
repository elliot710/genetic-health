from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

_OT_API_URL = "https://api.platform.opentargets.org/api/v4/graphql"

_GENE_DISEASE_QUERY = """
query GeneDisease($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    associatedDiseases(page: {index: 0, size: 20}) {
      rows {
        disease { id name }
        score
        datatypeScores { id score }
      }
    }
  }
}
"""

_GENE_BY_SYMBOL_QUERY = """
query GeneBySymbol($symbol: String!) {
  search(queryString: $symbol, entityNames: ["target"], page: {index: 0, size: 1}) {
    hits {
      id
      object {
        ... on Target { id approvedSymbol }
      }
    }
  }
}
"""

_STRONG_EVIDENCE_TYPES = {"genetic_association", "genetic_literature"}
_SIGNIFICANT_SCORE_THRESHOLD = 0.3


class OpenTargetsService:
    """Open Targets Platform API — gene-disease association scores by gene symbol."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._gene_id_cache: Dict[str, Optional[str]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Content-Type": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def lookup_by_gene(self, gene_symbol: str) -> Dict[str, Any]:
        if not gene_symbol:
            return {"found": False, "source": "open_targets"}
        ensembl_id = await self._resolve_gene_id(gene_symbol)
        if not ensembl_id:
            return {"found": False, "source": "open_targets", "gene_symbol": gene_symbol}
        return await self._fetch_associations(gene_symbol, ensembl_id)

    async def _resolve_gene_id(self, gene_symbol: str) -> Optional[str]:
        if gene_symbol in self._gene_id_cache:
            return self._gene_id_cache[gene_symbol]
        try:
            session = await self._get_session()
            async with session.post(_OT_API_URL, json={
                "query": _GENE_BY_SYMBOL_QUERY,
                "variables": {"symbol": gene_symbol},
            }) as resp:
                if resp.status != 200:
                    self._gene_id_cache[gene_symbol] = None
                    return None
                data = await resp.json()
            hits = data.get("data", {}).get("search", {}).get("hits", [])
            for hit in hits:
                obj = hit.get("object", {})
                sym = obj.get("approvedSymbol", "")
                if sym.upper() == gene_symbol.upper():
                    ensembl_id = obj.get("id") or hit.get("id")
                    self._gene_id_cache[gene_symbol] = ensembl_id
                    return ensembl_id
        except Exception as exc:
            logger.debug("OpenTargets gene lookup failed for %s: %s", gene_symbol, exc)
        self._gene_id_cache[gene_symbol] = None
        return None

    async def _fetch_associations(self, gene_symbol: str, ensembl_id: str) -> Dict[str, Any]:
        try:
            session = await self._get_session()
            async with session.post(_OT_API_URL, json={
                "query": _GENE_DISEASE_QUERY,
                "variables": {"ensemblId": ensembl_id},
            }) as resp:
                if resp.status != 200:
                    return {"found": False, "source": "open_targets"}
                data = await resp.json()

            rows = (
                data.get("data", {})
                .get("target", {})
                .get("associatedDiseases", {})
                .get("rows", [])
            )
            if not rows:
                return {"found": False, "source": "open_targets", "gene_symbol": gene_symbol}

            associations = [_row_to_association(r) for r in rows]
            top = max(associations, key=lambda a: a["score"])

            return {
                "found": True,
                "source": "open_targets",
                "gene_symbol": gene_symbol,
                "ensembl_id": ensembl_id,
                "associations": associations,
                "top_disease": top["disease_name"],
                "max_score": top["score"],
                "has_strong_genetic_evidence": any(
                    a["genetic_association_score"] is not None
                    and a["genetic_association_score"] >= _SIGNIFICANT_SCORE_THRESHOLD
                    for a in associations
                ),
            }
        except Exception as exc:
            logger.debug("OpenTargets fetch failed for %s: %s", gene_symbol, exc)
            return {"found": False, "source": "open_targets", "gene_symbol": gene_symbol}

    async def lookup_genes_batch(
        self, gene_symbols: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        tasks = {gene: self.lookup_by_gene(gene) for gene in gene_symbols}
        results: Dict[str, Dict[str, Any]] = {}
        total = len(tasks)
        for idx, (gene, coro) in enumerate(tasks.items(), 1):
            results[gene] = await coro
            if idx % 100 == 0 or idx == total:
                found = sum(1 for d in results.values() if d and d.get('found'))
                logger.info(f"Open Targets batch: {idx}/{total} genes queried ({found} with data)")
            await asyncio.sleep(0.05)
        return results


def _row_to_association(row: Dict[str, Any]) -> Dict[str, Any]:
    genetic_score = None
    lit_score = None
    for dt in row.get("datatypeScores", []):
        if dt["id"] == "genetic_association":
            genetic_score = dt["score"]
        elif dt["id"] in ("genetic_literature", "literature"):
            lit_score = dt["score"]
    return {
        "disease_id": row["disease"]["id"],
        "disease_name": row["disease"]["name"],
        "score": row["score"],
        "genetic_association_score": genetic_score,
        "literature_score": lit_score,
        "datatype_scores": {d["id"]: d["score"] for d in row.get("datatypeScores", [])},
    }


_instance: Optional[OpenTargetsService] = None


def get_open_targets_service() -> OpenTargetsService:
    global _instance
    if _instance is None:
        _instance = OpenTargetsService()
    return _instance
