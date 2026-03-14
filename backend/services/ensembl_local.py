"""
Local Ensembl gene service backed by PostgreSQL (ensembl_genes table).

Provides position-based variant→gene mapping using gene coordinate ranges
parsed from Ensembl cDNA/ncRNA FASTA headers.

Usage:
    svc = get_ensembl_local_service()
    result = await svc.lookup_gene_by_position("1", 11856378)
    genes = await svc.batch_position_to_gene([(chr, pos), ...])
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text

from ..db.database import async_session_factory
from ..db.models import EnsemblGene

logger = logging.getLogger(__name__)


class EnsemblLocalService:
    """PostgreSQL-backed Ensembl gene lookup service."""

    def __init__(self):
        self._gene_count: Optional[int] = None

    @property
    def is_loaded(self) -> bool:
        return self._gene_count is not None and self._gene_count > 0

    @property
    def gene_count(self) -> int:
        return self._gene_count or 0

    async def ensure_loaded(self) -> bool:
        """Check if ensembl_genes table has data."""
        if self._gene_count is not None:
            return self._gene_count > 0
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(EnsemblGene.id).limit(1)
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    count_result = await session.execute(
                        text("SELECT COUNT(*) FROM ensembl_genes")
                    )
                    self._gene_count = count_result.scalar()
                    logger.info(f"Ensembl local: {self._gene_count} genes available")
                else:
                    self._gene_count = 0
                    logger.info("Ensembl local: no genes loaded (run ETL first)")
        except Exception as e:
            self._gene_count = 0
            logger.debug(f"Ensembl local: table not available: {e}")
        return self._gene_count > 0

    async def lookup_gene(self, gene_symbol: str) -> Dict[str, Any]:
        """Look up a gene by symbol."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(EnsemblGene).where(EnsemblGene.gene_symbol == gene_symbol)
            )
            gene = result.scalar_one_or_none()
            if not gene:
                return {"found": False, "gene_symbol": gene_symbol}
            return {
                "found": True,
                "source": "ensembl_local",
                "gene_id": gene.gene_id,
                "gene_symbol": gene.gene_symbol,
                "chromosome": gene.chromosome,
                "start": gene.start_pos,
                "end": gene.end_pos,
                "strand": gene.strand,
                "biotype": gene.biotype,
                "description": gene.description,
                "transcript_count": gene.transcript_count,
            }

    async def lookup_gene_by_position(
        self, chromosome: str, position: int
    ) -> Dict[str, Any]:
        """Find the gene(s) overlapping a chromosomal position.

        Prefers protein-coding genes if multiple genes overlap.
        """
        chrom = str(chromosome).replace('chr', '')
        async with async_session_factory() as session:
            result = await session.execute(
                select(EnsemblGene)
                .where(
                    EnsemblGene.chromosome == chrom,
                    EnsemblGene.start_pos <= position,
                    EnsemblGene.end_pos >= position,
                )
                .order_by(
                    # Prefer protein_coding, then by smallest gene (most specific)
                    (EnsemblGene.biotype != 'protein_coding').asc(),
                    (EnsemblGene.end_pos - EnsemblGene.start_pos).asc(),
                )
                .limit(5)
            )
            genes = result.scalars().all()
            if not genes:
                return {"found": False, "chromosome": chrom, "position": position}

            best = genes[0]
            return {
                "found": True,
                "source": "ensembl_local",
                "gene_symbol": best.gene_symbol,
                "gene_id": best.gene_id,
                "biotype": best.biotype,
                "description": best.description,
                "overlapping_genes": len(genes),
            }

    async def batch_position_to_gene(
        self, positions: List[Tuple[str, int, str]]
    ) -> Dict[str, str]:
        """Map a batch of (chromosome, position, rsid) to gene symbols.

        Uses a single efficient query with lateral join to find the best gene
        for each position.

        Returns {rsid: gene_symbol} for positions that map to a gene.
        """
        if not positions:
            return {}

        if not await self.ensure_loaded():
            return {}

        gene_map: Dict[str, str] = {}

        # Process in batches to avoid overly large queries
        batch_size = 500
        async with async_session_factory() as session:
            for i in range(0, len(positions), batch_size):
                batch = positions[i:i + batch_size]

                # Group by chromosome for efficient querying
                by_chrom: Dict[str, List[Tuple[int, str]]] = {}
                for chrom, pos, rsid in batch:
                    c = str(chrom).replace('chr', '')
                    by_chrom.setdefault(c, []).append((pos, rsid))

                for chrom, pos_rsids in by_chrom.items():
                    pos_list = [p for p, _ in pos_rsids]
                    rsid_by_pos: Dict[int, List[str]] = {}
                    for pos, rsid in pos_rsids:
                        rsid_by_pos.setdefault(pos, []).append(rsid)

                    # Get all genes on this chromosome that overlap any of our positions
                    min_pos = min(pos_list)
                    max_pos = max(pos_list)

                    result = await session.execute(
                        select(EnsemblGene)
                        .where(
                            EnsemblGene.chromosome == chrom,
                            EnsemblGene.start_pos <= max_pos,
                            EnsemblGene.end_pos >= min_pos,
                        )
                        .order_by(
                            (EnsemblGene.biotype != 'protein_coding').asc(),
                            (EnsemblGene.end_pos - EnsemblGene.start_pos).asc(),
                        )
                    )
                    chrom_genes = result.scalars().all()

                    # For each position, find the best overlapping gene
                    for pos in set(pos_list):
                        for gene in chrom_genes:
                            if gene.start_pos <= pos <= gene.end_pos:
                                for rsid in rsid_by_pos.get(pos, []):
                                    if rsid not in gene_map:
                                        gene_map[rsid] = gene.gene_symbol
                                break  # Best gene found (protein_coding preferred)

        return gene_map


# Singleton
_instance: Optional[EnsemblLocalService] = None

def get_ensembl_local_service() -> EnsemblLocalService:
    global _instance
    if _instance is None:
        _instance = EnsemblLocalService()
    return _instance
