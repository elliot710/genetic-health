"""Unified consequence resolver (U5).

Fills a variant's molecular consequence from the offline caches when the primary
annotation (Ensembl VEP local → ClinVar → gnomAD, in extract_gene_and_consequence)
did not supply one. Priority: pre-annotated VEP marker cache → dbSNP MC →
SnpEff. MANE canonical selection already happened when the VEP/SnpEff caches were
built, so the caches return one collapsed consequence per rsid.
"""
import os
from typing import Optional

from backend.services.annotation_sources.vep_offline_cache import VepConsequenceCache
from backend.services.annotation_sources.dbsnp_mc_cache import DbsnpMcCache
from backend.services.annotation_sources.snpeff_offline_cache import SnpEffConsequenceCache

_VEP_DB = ".vep_cache/vep_consequence.db"
_DBSNP_DB = ".dbsnp_cache/dbsnp_mc.db"
_SNPEFF_DB = ".snpeff_cache/snpeff_consequence.db"


class ConsequenceResolver:
    def __init__(self, vep=None, dbsnp=None, snpeff=None):
        self._vep = vep
        self._dbsnp = dbsnp
        self._snpeff = snpeff

    def resolve(self, rsid: Optional[str], existing_consequence: Optional[str] = None) -> Optional[str]:
        if existing_consequence:
            return existing_consequence
        if not rsid:
            return None
        if self._vep is not None:
            c = self._vep.consequence_for(rsid)
            if c:
                return c
        if self._dbsnp is not None:
            terms = self._dbsnp.consequence_for_rsid(rsid)
            if terms:
                return terms[0]  # leading term = most severe (cache is severity-ordered)
        if self._snpeff is not None:
            c = self._snpeff.consequence_for(rsid)
            if c:
                return c
        return None


_resolver: Optional[ConsequenceResolver] = None


def get_consequence_resolver() -> ConsequenceResolver:
    """Process-wide resolver, lazily wired to whichever caches exist on disk.
    A missing cache is simply not consulted (graceful degradation)."""
    global _resolver
    if _resolver is None:
        _resolver = ConsequenceResolver(
            vep=VepConsequenceCache(_VEP_DB) if os.path.exists(_VEP_DB) else None,
            dbsnp=DbsnpMcCache(_DBSNP_DB) if os.path.exists(_DBSNP_DB) else None,
            snpeff=SnpEffConsequenceCache(_SNPEFF_DB) if os.path.exists(_SNPEFF_DB) else None,
        )
    return _resolver
