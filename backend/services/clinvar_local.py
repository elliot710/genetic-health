"""
Local ClinVar service backed by PostgreSQL (clinvar_variants table).

Drop-in replacement for the old in-memory version.  All data is queried from
the clinvar_variants, clinvar_gene_conditions, and clinvar_gene_stats tables
populated by the ETL service (clinvar_etl.py).

Usage:
    svc = get_clinvar_local_service()
    result = await svc.lookup("rs1234")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.models import ClinVarVariant, ClinVarGeneCondition, ClinVarGeneStats

logger = logging.getLogger(__name__)


class ClinVarLocalService:
    """PostgreSQL-backed ClinVar lookup service."""

    def __init__(self):
        self._variant_count: Optional[int] = None
        self._available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Compat properties (match old interface)
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when get_import_status has been checked or assumed available."""
        return self._available if self._available is not None else True

    @property
    def is_loaded(self) -> bool:
        """Always True — data lives in PG, no in-memory loading required."""
        return self._variant_count is not None and self._variant_count > 0

    @property
    def variant_count(self) -> int:
        return self._variant_count or 0

    @property
    def vcf_variant_count(self) -> int:
        return 0  # Merged into same table

    @property
    def files_loaded(self) -> List[str]:
        return ["postgresql"]

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    async def ensure_loaded(self) -> bool:
        """Check that the clinvar_variants table has data."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(ClinVarVariant)
                )
                self._variant_count = result.scalar() or 0
            self._available = self._variant_count > 0
            if self._available:
                logger.info("ClinVar PG: %d rows available", self._variant_count)
            else:
                logger.warning("ClinVar PG: table empty — run ETL import first")
            return self._available
        except Exception as e:
            logger.warning("ClinVar PG check failed: %s", e)
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Core lookup
    # ------------------------------------------------------------------

    async def lookup(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Look up a single rsid. Returns same format as old in-memory version."""
        async with async_session_factory() as session:
            return await self._lookup_impl(session, rsid)

    async def lookup_batch(self, rsids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch lookup. Returns {rsid: result_or_none}."""
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        async with async_session_factory() as session:
            for rsid in rsids:
                results[rsid] = await self._lookup_impl(session, rsid)
        return results

    async def _lookup_impl(self, session: AsyncSession, rsid: str) -> Optional[Dict[str, Any]]:
        """Single rsid lookup within an existing session."""
        # Fetch all ClinVar rows for this rsid
        result = await session.execute(
            select(ClinVarVariant).where(ClinVarVariant.rsid == rsid)
        )
        rows = result.scalars().all()

        if not rows:
            return {"found": False, "source": "clinvar_local"}

        # Aggregate data across all rows
        clinical_sigs: List[str] = []
        conditions: List[str] = []
        genes: List[str] = []
        variation_ids: set = set()
        allele_ids: set = set()
        result_entries: List[Dict[str, Any]] = []

        allele_freqs: Dict[str, float] = {}
        mol_consequences: List[str] = []
        oncogenicity_list: List[str] = []
        somatic_impact_list: List[str] = []
        conflicting_list: List[str] = []

        for r in rows:
            # Clinical significance
            if r.clinical_significance and r.clinical_significance not in clinical_sigs:
                clinical_sigs.append(r.clinical_significance)

            # Conditions
            if r.conditions and r.conditions not in ("not provided", "not_provided"):
                cond = r.conditions.replace("_", " ")
                if cond not in conditions:
                    conditions.append(cond)

            # Gene
            if r.gene and r.gene not in genes:
                genes.append(r.gene)

            if r.variation_id:
                variation_ids.add(r.variation_id)
            if r.allele_id:
                allele_ids.add(r.allele_id)

            # Entries
            if r.data_source == "tsv":
                result_entries.append({
                    "uid": r.variation_id,
                    "allele_id": r.allele_id,
                    "title": f"{rsid} - {r.conditions}" if r.conditions else rsid,
                    "accession": r.rcv_accession,
                    "clinical_significance": [r.clinical_significance] if r.clinical_significance else [],
                    "conditions": [r.conditions] if r.conditions and r.conditions != "not provided" else [],
                    "variation_type": r.variation_type,
                    "gene": r.gene,
                    "review_status": r.review_status,
                    "origin": r.origin,
                    "chromosome": r.chromosome,
                    "start": str(r.start_pos) if r.start_pos else "",
                    "stop": str(r.stop_pos) if r.stop_pos else "",
                    "hgvs_nucleotide": r.hgvs_nucleotide or "",
                    "hgvs_protein": r.hgvs_protein or "",
                })

            # VCF-derived fields
            if r.data_source == "vcf":
                if r.af_exac is not None and "exac" not in allele_freqs:
                    allele_freqs["exac"] = r.af_exac
                if r.af_tgp is not None and "tgp" not in allele_freqs:
                    allele_freqs["tgp"] = r.af_tgp
                if r.af_esp is not None and "esp" not in allele_freqs:
                    allele_freqs["esp"] = r.af_esp
                if r.molecular_consequence and r.molecular_consequence not in mol_consequences:
                    mol_consequences.append(r.molecular_consequence)
                if r.oncogenicity and r.oncogenicity not in oncogenicity_list:
                    oncogenicity_list.append(r.oncogenicity)
                if r.somatic_clinical_impact and r.somatic_clinical_impact not in somatic_impact_list:
                    somatic_impact_list.append(r.somatic_clinical_impact)
                if r.conflicting_classifications and r.conflicting_classifications not in conflicting_list:
                    conflicting_list.append(r.conflicting_classifications)

        # Gene conditions
        gene_conditions: List[Dict[str, str]] = []
        if genes:
            gc_result = await session.execute(
                select(ClinVarGeneCondition).where(ClinVarGeneCondition.gene.in_(genes))
            )
            for gc in gc_result.scalars().all():
                gene_conditions.append({
                    "disease": gc.disease_name,
                    "source": gc.source_name or "",
                    "source_id": gc.source_id or "",
                    "disease_mim": gc.disease_mim or "",
                })
        gene_conditions = gene_conditions[:20]

        # Gene stats
        gene_stats_list: List[Dict[str, Any]] = []
        if genes:
            gs_result = await session.execute(
                select(ClinVarGeneStats).where(ClinVarGeneStats.gene.in_(genes))
            )
            for gs in gs_result.scalars().all():
                gene_stats_list.append({
                    "gene": gs.gene,
                    "gene_id": gs.gene_id or "",
                    "total_submissions": gs.total_submissions,
                    "total_alleles": gs.total_alleles,
                    "pathogenic_likely_pathogenic": gs.pathogenic_likely_pathogenic,
                    "gene_mim": gs.gene_mim or "",
                    "uncertain": gs.uncertain_significance,
                    "with_conflicts": gs.with_conflicts,
                })

        # Build VCF data sub-dict
        vcf_data: Optional[Dict[str, Any]] = None
        if allele_freqs or mol_consequences or oncogenicity_list or somatic_impact_list:
            vcf_data = {}
            if allele_freqs:
                vcf_data["allele_frequencies"] = allele_freqs
            if mol_consequences:
                vcf_data["molecular_consequences"] = mol_consequences[:10]
            if oncogenicity_list:
                vcf_data["oncogenicity"] = oncogenicity_list
            if somatic_impact_list:
                vcf_data["somatic_clinical_impact"] = somatic_impact_list
            if conflicting_list:
                vcf_data["conflicting_classifications"] = conflicting_list[:5]

        review_statuses = list({r.review_status for r in rows if r.review_status})

        output: Dict[str, Any] = {
            "found": True,
            "source": "clinvar_local",
            "count": len(rows),
            "ids": list(variation_ids)[:20],
            "allele_ids": list(allele_ids)[:20],
            "clinical_significances": clinical_sigs,
            "conditions": conditions,
            "genes": genes,
            "review_statuses": review_statuses,
            "has_conflicting_interpretations": bool(conflicting_list),
            "total_submissions": 0,
            "pubmed_ids": [],
            "cross_references": [],
            "gene_conditions": gene_conditions,
            "gene_stats": gene_stats_list,
            "disease_details": [],
            "entries": result_entries[:10],
        }

        if vcf_data:
            output["vcf_data"] = vcf_data

        return output


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_clinvar_local_instance: Optional[ClinVarLocalService] = None


def get_clinvar_local_service() -> ClinVarLocalService:
    """Return the singleton ClinVarLocalService instance."""
    global _clinvar_local_instance
    if _clinvar_local_instance is None:
        _clinvar_local_instance = ClinVarLocalService()
    return _clinvar_local_instance
